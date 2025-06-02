"""Media processing router for document upload and processing."""

import logging
import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field, HttpUrl

from app.exceptions import (
    DocumentNotFoundError,
    DocumentParsingError,
    OCRError,
)
from app.models.database import DocumentStatus, DocumentType, Invoice
from app.models.responses import (
    DocumentFlags,
    MediaUploadResponse,
    ProcessingStatusResponse,
)
from app.services.database_flag_service import database_flag_service
from app.services.document_parsers import (
    AgreementParser,
    CDLParser,
    COIParser,
    InvoiceParser,
    PODParser,
    RateConfirmationParser,
)
from app.services.document_service import document_service
from app.services.document_storage import document_storage_service
from app.services.ocr_clients import UnifiedOCRClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


class MediaUploadRequest(BaseModel):
    """Request model for media upload and processing."""

    driver_id: UUID = Field(..., description="Driver UUID")
    load_id: UUID | None = Field(None, description="Load UUID (optional)")
    doc_type: DocumentType = Field(..., description="Document type")
    media_url: HttpUrl = Field(..., description="URL of the media file to process")

    class Config:
        json_encoders = {UUID: str}


def get_parser_for_type(doc_type: DocumentType):
    """Get the appropriate parser for a document type."""
    if doc_type == DocumentType.CDL:
        return CDLParser()
    elif doc_type == DocumentType.COI:
        return COIParser()
    elif doc_type == DocumentType.AGREEMENT:
        return AgreementParser()
    elif doc_type == DocumentType.RATE_CON:
        return RateConfirmationParser()
    elif doc_type == DocumentType.POD:
        return PODParser()
    elif doc_type == DocumentType.INVOICE:
        return InvoiceParser()
    else:
        return None


def get_document_flags(
    doc_type: DocumentType, parsed_data: dict[str, Any], confidence: float
) -> DocumentFlags:
    """Generate document flags based on type, parsed data, and confidence."""
    flags = DocumentFlags()

    # High confidence threshold for verification
    high_confidence = confidence >= 0.85

    if doc_type == DocumentType.CDL and high_confidence:
        # Check for required CDL fields
        if parsed_data and all(
            key in parsed_data for key in ["license_number", "expiration_date"]
        ):
            flags.cdl_verified = True

    elif doc_type == DocumentType.COI and high_confidence:
        # Check for required insurance fields
        if parsed_data and all(
            key in parsed_data for key in ["policy_number", "coverage_amount"]
        ):
            flags.insurance_verified = True

    elif doc_type == DocumentType.AGREEMENT and high_confidence:
        # Check for signature or signed indicator
        if parsed_data and parsed_data.get("signed", False):
            flags.agreement_signed = True

    elif doc_type == DocumentType.RATE_CON and high_confidence:
        # Check for required rate confirmation fields
        if parsed_data and all(
            key in parsed_data for key in ["rate", "pickup_date", "delivery_date"]
        ):
            flags.ratecon_parsed = True

    elif doc_type == DocumentType.POD and high_confidence:
        # Check for completion indicators
        if parsed_data and parsed_data.get("delivered", False):
            flags.pod_ok = True

    elif doc_type == DocumentType.INVOICE and high_confidence:
        # Check for required invoice fields
        if parsed_data and all(
            key in parsed_data for key in ["invoice_number", "total_amount"]
        ):
            flags.invoice_processed = True

    return flags


async def process_document_pipeline(
    document_id: UUID,
    driver_id: UUID,
    load_id: UUID | None,
    doc_type: DocumentType,
    media_url: str,
    request_id: str | None = None,
):
    """
    Background task to process a document through the full pipeline.

    This function handles:
    1. File download from URL
    2. Storage upload
    3. Database record creation
    4. OCR processing (Datalab -> Marker fallback)
    5. Document parsing by type
    6. Database flag updates
    7. Event emission
    """
    pipeline_start = time.time()

    try:
        logger.info(
            f"Starting document processing pipeline for document {document_id} - Request ID: {request_id}"
        )

        # Step 1: Download file from URL and upload to storage
        logger.info(f"Step 1: Downloading and storing file from {media_url}")
        try:
            storage_result = await document_storage_service.process_upload(
                media_url=media_url, driver_id=driver_id, doc_type=doc_type.value
            )

            public_url = storage_result["public_url"]
            original_filename = storage_result["original_filename"]
            file_size = storage_result["file_size"]
            content_type = storage_result["content_type"]

            logger.info(f"File stored successfully: {public_url}")

        except Exception as e:
            logger.error(f"File download/storage failed for {document_id}: {e}")
            await document_service.update_document_status(
                document_id=document_id,
                status=DocumentStatus.FAILED,
                error_message=f"File download/storage failed: {str(e)}",
            )
            return

        # Step 2: Create database record
        logger.info("Step 2: Creating database record")
        try:
            document = await document_service.create_document(
                document_id=document_id,
                driver_id=driver_id,
                load_id=load_id,
                doc_type=doc_type,
                url=public_url,
                original_filename=original_filename,
                file_size=file_size,
                content_type=content_type,
            )
            logger.info(f"Database record created: {document_id}")

        except Exception as e:
            logger.error(f"Database record creation failed for {document_id}: {e}")
            # Document creation failed, but file is stored - update status if possible
            try:
                await document_service.update_document_status(
                    document_id=document_id,
                    status=DocumentStatus.FAILED,
                    error_message=f"Database record creation failed: {str(e)}",
                )
            except:
                pass  # If this fails too, we can't do much more
            return

        # Step 3: OCR processing
        logger.info("Step 3: Starting OCR processing")
        try:
            ocr_client = UnifiedOCRClient()

            # Download file content for OCR processing
            (
                file_content,
                filename,
                content_type_local,
            ) = await document_storage_service.download_file_from_url(media_url)

            # Process with OCR
            ocr_result = await ocr_client.process_file_content(
                file_content=file_content,
                filename=filename,
                mime_type=content_type_local,
            )

            if not ocr_result or not ocr_result.get("full_text"):
                raise OCRError(
                    "OCR processing returned no text", retry_recommended=True
                )

            extracted_text = ocr_result["full_text"]
            confidence = ocr_result.get("confidence", 0.0)

            logger.info(f"OCR completed with confidence {confidence}")

        except Exception as e:
            logger.error(f"OCR processing failed for {document_id}: {e}")
            await document_service.update_document_status(
                document_id=document_id,
                status=DocumentStatus.FAILED,
                error_message=f"OCR processing failed: {str(e)}",
            )
            return

        # Step 4: Document parsing based on type
        logger.info(f"Step 4: Starting document parsing for type {doc_type}")
        try:
            parser = get_parser_for_type(doc_type)
            if not parser:
                raise DocumentParsingError(
                    f"No parser available for document type: {doc_type}"
                )

            # Parse the extracted text
            parsing_result = parser.parse(extracted_text)

            if not parsing_result or not parsing_result.data:
                raise DocumentParsingError(
                    "Document parsing returned no data", retry_recommended=True
                )

            parsed_data = (
                parsing_result.data.model_dump(mode="json")
                if hasattr(parsing_result.data, "model_dump")
                else parsing_result.data
            )
            parsing_confidence = (
                parsing_result.confidence
                if hasattr(parsing_result, "confidence")
                else 0.8
            )

            logger.info(
                f"Document parsing completed with confidence {parsing_confidence}"
            )

        except Exception as e:
            logger.error(f"Document parsing failed for {document_id}: {e}")
            await document_service.update_document_status(
                document_id=document_id,
                status=DocumentStatus.FAILED,
                error_message=f"Document parsing failed: {str(e)}",
            )
            return

        # Step 5: Update document with parsed data
        logger.info("Step 5: Updating document with parsed data")
        try:
            await document_service.update_document_status(
                document_id=document_id,
                status=DocumentStatus.PARSED,
                parsed_data=parsed_data,
                confidence=parsing_confidence,
            )
            logger.info("Document status updated to PARSED")

            # If this is an invoice document, also save the parsed data to the invoices table
            if doc_type == DocumentType.INVOICE and parsed_data:
                try:
                    # Convert parsed data to Invoice model
                    invoice_data = Invoice(**parsed_data)
                    
                    # Save to invoices table
                    success = await document_service.save_invoice_data(
                        document_id=document_id,
                        invoice_data=invoice_data,
                        request_id=request_id
                    )
                    
                    if success:
                        logger.info(f"Invoice data saved successfully for document {document_id}")
                    else:
                        logger.warning(f"Failed to save invoice data for document {document_id}")
                        
                except Exception as e:
                    logger.error(f"Error saving invoice data for document {document_id}: {e}")
                    # Don't fail the entire pipeline for invoice save failures

        except Exception as e:
            logger.error(f"Failed to update document status for {document_id}: {e}")
            return

        # Step 6: Update database flags and emit events
        logger.info("Step 6: Updating database flags and emitting events")
        try:
            # Get the document instance for flag processing
            document = await document_service.get_document_by_id(document_id)

            # Process document flags based on parsed data and confidence
            flag_result = await database_flag_service.process_document_flags(
                document=document, parsed_data=parsed_data, confidence=confidence
            )

            logger.info(f"Database flags updated successfully: {flag_result}")

        except Exception as e:
            logger.error(f"Failed to update database flags for {document_id}: {e}")
            # Don't fail the entire pipeline for flag update failures

        # Calculate processing time
        processing_time_ms = int((time.time() - pipeline_start) * 1000)
        logger.info(
            f"Document processing pipeline completed successfully for {document_id} in {processing_time_ms}ms"
        )

    except Exception as e:
        logger.error(
            f"Unexpected error in document processing pipeline for {document_id}: {e}"
        )
        try:
            await document_service.update_document_status(
                document_id=document_id,
                status=DocumentStatus.FAILED,
                error_message=f"Pipeline error: {str(e)}",
            )
        except:
            pass  # If this fails, we can't do much more


@router.post("/", response_model=MediaUploadResponse, status_code=202)
async def upload_media(
    request: MediaUploadRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
) -> MediaUploadResponse:
    """
    Upload and process media file from URL.

    This endpoint:
    1. Validates the request parameters
    2. Generates a document ID for tracking
    3. Initiates background processing
    4. Returns 202 Accepted with tracking information

    The actual processing happens asynchronously in the background.
    """
    request_id = getattr(http_request.state, "request_id", None)

    try:
        logger.info(
            f"Media upload request: driver_id={request.driver_id}, "
            f"doc_type={request.doc_type}, url={request.media_url} - Request ID: {request_id}"
        )

        # Generate document ID for tracking
        document_id = uuid4()

        # Start background processing
        background_tasks.add_task(
            process_document_pipeline,
            document_id=document_id,
            driver_id=request.driver_id,
            load_id=request.load_id,
            doc_type=request.doc_type,
            media_url=str(request.media_url),
            request_id=request_id,
        )

        # Return 202 Accepted response with standardized format
        return MediaUploadResponse(
            success=True,
            doc_id=document_id,
            needs_retry=False,
            confidence=0.0,  # No confidence yet, processing not started
            flags=DocumentFlags(),  # Empty flags initially
            message="Document upload accepted and processing started",
            request_id=request_id,
            processing_url=f"/api/media/{document_id}/status",
        )

    except Exception as e:
        logger.error(
            f"Unexpected error in media upload: {e} - Request ID: {request_id}"
        )
        raise HTTPException(
            status_code=500, detail="Internal server error during media upload"
        )


@router.get("/{document_id}/status", response_model=ProcessingStatusResponse)
async def get_processing_status(
    document_id: UUID, http_request: Request
) -> ProcessingStatusResponse:
    """
    Get the processing status of a document.

    Returns the current status and progress of document processing.
    """
    request_id = getattr(http_request.state, "request_id", None)

    try:
        # Get status from document service
        status_info = await document_service.get_processing_status(document_id)

        if not status_info:
            raise DocumentNotFoundError(str(document_id))

        # Extract fields for standardized response
        doc_status = status_info.get("status", "unknown")
        progress = status_info.get("progress", {})
        result = status_info.get("result")
        error = status_info.get("error")
        metadata = status_info.get("metadata", {})
        confidence = status_info.get("confidence", 0.0)

        # Determine success and retry flags
        success = doc_status == "parsed"
        needs_retry = doc_status == "failed" and error and "retry" in error.lower()

        # Generate flags based on result and confidence
        flags = DocumentFlags()
        if result and confidence > 0.0:
            # Try to determine document type from metadata or result
            doc_type_str = metadata.get("doc_type")
            if doc_type_str:
                try:
                    doc_type = DocumentType(doc_type_str)
                    flags = get_document_flags(doc_type, result, confidence)
                except ValueError:
                    pass  # Invalid doc_type, use empty flags

        return ProcessingStatusResponse(
            success=success,
            doc_id=document_id,
            needs_retry=needs_retry,
            confidence=confidence,
            flags=flags,
            message=progress.get("message", f"Document status: {doc_status}"),
            request_id=request_id,
            status=doc_status,
            progress=progress,
            result=result,
            error=error,
            metadata=metadata,
        )

    except DocumentNotFoundError:
        # Re-raise to be handled by exception handler
        raise
    except Exception as e:
        logger.error(
            f"Error getting processing status for {document_id}: {e} - Request ID: {request_id}"
        )
        raise HTTPException(
            status_code=500, detail="Error retrieving processing status"
        )

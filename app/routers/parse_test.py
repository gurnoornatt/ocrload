"""Parse test router for local file processing during development and testing."""

import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.models.database import DocumentType, Document, DocumentStatus
from app.models.responses import ParseTestResponse, DocumentFlags
from app.config.settings import settings
from app.exceptions import (
    FileNotFoundError, FileValidationError, SecurityError,
    DocumentNotFoundError, StorageError, DatabaseError,
    OCRError, DocumentParsingError, to_http_exception
)
from app.services.document_storage import document_storage_service
from app.services.document_service import document_service
from app.services.ocr_clients import UnifiedOCRClient
from app.services.document_parsers import (
    CDLParser, COIParser, AgreementParser, 
    RateConfirmationParser, PODParser
)
from app.services.database_flag_service import database_flag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parse-test", tags=["parse-test"])


class ParseTestRequest(BaseModel):
    """Request model for parse test endpoint."""
    path: str = Field(..., description="Local file path (absolute or relative)")
    doc_type: DocumentType = Field(..., description="Document type")
    driver_id: Optional[UUID] = Field(None, description="Driver UUID (optional for testing)")
    load_id: Optional[UUID] = Field(None, description="Load UUID (optional for testing)")

    @field_validator('path')
    @classmethod
    def validate_path_security(cls, v):
        """Validate file path for security (prevent directory traversal)."""
        # Check for empty or invalid input
        if not v or not v.strip():
            raise ValueError("Path cannot be empty")
        
        # Convert to Path object for validation
        path = Path(v)
        
        # Security check: prevent directory traversal
        try:
            # Check for obvious directory traversal patterns
            if '..' in str(path):
                raise ValueError("Directory traversal not allowed")
            
            resolved_path = path.resolve()
            
            # Allow absolute paths that don't contain '..'
            if path.is_absolute():
                return str(resolved_path)
            
            # For relative paths, resolve relative to current working directory
            # and ensure they don't escape
            return str(resolved_path)
            
        except ValueError:
            # Re-raise ValueError as is
            raise
        except Exception:
            # Convert other exceptions to ValueError with string message
            raise ValueError("Invalid file path")

    model_config = {
        "json_encoders": {
            UUID: str
        }
    }


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
    else:
        return None


def get_document_flags(doc_type: DocumentType, parsed_data: Dict[str, Any], confidence: float) -> DocumentFlags:
    """Generate document flags based on type, parsed data, and confidence."""
    flags = DocumentFlags()
    
    # High confidence threshold for verification
    high_confidence = confidence >= 0.85
    
    if doc_type == DocumentType.CDL and high_confidence:
        # Check for required CDL fields
        if parsed_data and all(key in parsed_data for key in ['license_number', 'expiration_date']):
            flags.cdl_verified = True
    
    elif doc_type == DocumentType.COI and high_confidence:
        # Check for required insurance fields
        if parsed_data and all(key in parsed_data for key in ['policy_number', 'coverage_amount']):
            flags.insurance_verified = True
    
    elif doc_type == DocumentType.AGREEMENT and high_confidence:
        # Check for signature or signed indicator
        if parsed_data and parsed_data.get('signed', False):
            flags.agreement_signed = True
    
    elif doc_type == DocumentType.RATE_CON and high_confidence:
        # Check for required rate confirmation fields
        if parsed_data and all(key in parsed_data for key in ['rate', 'pickup_date', 'delivery_date']):
            flags.ratecon_parsed = True
    
    elif doc_type == DocumentType.POD and high_confidence:
        # Check for completion indicators
        if parsed_data and parsed_data.get('delivered', False):
            flags.pod_ok = True
    
    return flags


async def process_local_document_pipeline(
    document_id: UUID,
    driver_id: Optional[UUID],
    load_id: Optional[UUID],
    doc_type: DocumentType,
    file_path: str,
    request_id: Optional[str] = None
):
    """
    Background task to process a local document through the full pipeline.
    
    This function handles:
    1. Local file reading and validation
    2. Storage upload
    3. Database record creation
    4. OCR processing (Datalab -> Marker fallback)
    5. Document parsing by type
    6. Database flag updates
    7. Event emission
    """
    pipeline_start = time.time()
    
    try:
        logger.info(f"Starting local document processing pipeline for document {document_id} - Request ID: {request_id}")
        
        # Step 1: Read local file and upload to storage
        logger.info(f"Step 1: Reading and storing local file {file_path}")
        try:
            # Read local file
            file_content, filename, content_type = await document_storage_service.read_local_file(file_path)
            
            # Upload to storage
            storage_result = await document_storage_service.upload_file_content(
                file_content=file_content,
                filename=filename,
                content_type=content_type,
                driver_id=driver_id,
                doc_type=doc_type.value
            )
            
            public_url = storage_result["public_url"]
            original_filename = storage_result["original_filename"]
            file_size = storage_result["file_size"]
            
            logger.info(f"Local file stored successfully: {public_url}")
            
        except FileNotFoundError:
            raise  # Re-raise to be handled by outer exception handler
        except Exception as e:
            logger.error(f"Local file processing/storage failed for {document_id}: {e}")
            await document_service.update_document_status(
                document_id=document_id,
                status=DocumentStatus.FAILED,
                error_message=f"Local file processing/storage failed: {str(e)}"
            )
            return
        
        # Step 2: Create database record
        logger.info(f"Step 2: Creating database record")
        try:
            document = await document_service.create_document(
                document_id=document_id,
                driver_id=driver_id,
                load_id=load_id,
                doc_type=doc_type,
                url=public_url,
                original_filename=original_filename,
                file_size=file_size,
                content_type=content_type
            )
            logger.info(f"Database record created: {document_id}")
            
        except Exception as e:
            logger.error(f"Database record creation failed for {document_id}: {e}")
            # Document creation failed, but file is stored - update status if possible
            try:
                await document_service.update_document_status(
                    document_id=document_id,
                    status=DocumentStatus.FAILED,
                    error_message=f"Database record creation failed: {str(e)}"
                )
            except:
                pass  # If this fails too, we can't do much more
            return
        
        # Step 3: OCR processing
        logger.info(f"Step 3: Starting OCR processing")
        try:
            ocr_client = UnifiedOCRClient()
            
            # Process with OCR using local file content
            ocr_result = await ocr_client.process_file_content(
                file_content=file_content,
                filename=filename,
                mime_type=content_type
            )
            
            if not ocr_result or not ocr_result.get("full_text"):
                raise OCRError("OCR processing returned no text", retry_recommended=True)
            
            extracted_text = ocr_result["full_text"]
            confidence = ocr_result.get("confidence", 0.0)
            
            logger.info(f"OCR completed with confidence {confidence}")
            
        except Exception as e:
            logger.error(f"OCR processing failed for {document_id}: {e}")
            await document_service.update_document_status(
                document_id=document_id,
                status=DocumentStatus.FAILED,
                error_message=f"OCR processing failed: {str(e)}"
            )
            return
        
        # Step 4: Document parsing based on type
        logger.info(f"Step 4: Starting document parsing for type {doc_type}")
        try:
            parser = get_parser_for_type(doc_type)
            if not parser:
                raise DocumentParsingError(f"No parser available for document type: {doc_type}")
            
            # Parse the extracted text
            parsing_result = parser.parse(extracted_text)
            
            if not parsing_result or not parsing_result.data:
                raise DocumentParsingError("Document parsing returned no data", retry_recommended=True)
            
            parsed_data = parsing_result.data.model_dump(mode='json') if hasattr(parsing_result.data, 'model_dump') else parsing_result.data
            parsing_confidence = parsing_result.confidence if hasattr(parsing_result, 'confidence') else 0.8
            
            logger.info(f"Document parsing completed with confidence {parsing_confidence}")
            
        except Exception as e:
            logger.error(f"Document parsing failed for {document_id}: {e}")
            await document_service.update_document_status(
                document_id=document_id,
                status=DocumentStatus.FAILED,
                error_message=f"Document parsing failed: {str(e)}"
            )
            return
        
        # Step 5: Update document with parsed data
        logger.info(f"Step 5: Updating document with parsed data")
        try:
            await document_service.update_document_status(
                document_id=document_id,
                status=DocumentStatus.PARSED,
                parsed_data=parsed_data,
                confidence=parsing_confidence
            )
            logger.info(f"Document status updated to PARSED")
            
        except Exception as e:
            logger.error(f"Failed to update document status for {document_id}: {e}")
            return
        
        # Step 6: Update database flags and emit events
        logger.info(f"Step 6: Updating database flags and emitting events")
        try:
            # Get the document instance for flag processing (if driver_id is provided)
            if driver_id:
                document = await document_service.get_document_by_id(document_id)
                
                # Process document flags based on parsed data and confidence
                flag_result = await database_flag_service.process_document_flags(
                    document=document,
                    parsed_data=parsed_data,
                    confidence=confidence
                )
                
                logger.info(f"Database flags updated successfully: {flag_result}")
            else:
                logger.info("Skipping database flag updates (no driver_id provided)")
            
        except Exception as e:
            logger.error(f"Failed to update database flags for {document_id}: {e}")
            # Don't fail the entire pipeline for flag update failures
        
        # Calculate processing time
        processing_time_ms = int((time.time() - pipeline_start) * 1000)
        logger.info(f"Local document processing pipeline completed successfully for {document_id} in {processing_time_ms}ms")
        
    except Exception as e:
        logger.error(f"Unexpected error in local document processing pipeline for {document_id}: {e}")
        try:
            await document_service.update_document_status(
                document_id=document_id,
                status=DocumentStatus.FAILED,
                error_message=f"Pipeline error: {str(e)}"
            )
        except:
            pass  # If this fails, we can't do much more


@router.post("/", response_model=ParseTestResponse, status_code=202)
async def parse_test_file(
    request: ParseTestRequest,
    background_tasks: BackgroundTasks,
    http_request: Request
) -> ParseTestResponse:
    """
    Parse and process a local file for development and testing.
    
    This endpoint:
    1. Validates the local file path and security
    2. Generates a document ID for tracking
    3. Initiates background processing using the same pipeline as /api/media
    4. Returns 202 Accepted with tracking information
    
    The actual processing happens asynchronously in the background.
    This endpoint is useful for development and testing without requiring
    WhatsApp integration or external file URLs.
    """
    request_id = getattr(http_request.state, 'request_id', None)
    
    try:
        logger.info(f"Parse test request: path={request.path}, "
                   f"doc_type={request.doc_type}, driver_id={request.driver_id} - Request ID: {request_id}")
        
        # Validate file exists and is accessible
        file_path = Path(request.path)
        if not file_path.exists():
            raise FileNotFoundError(request.path, {"reason": "File does not exist"})
        
        if not file_path.is_file():
            raise FileValidationError(
                f"Path is not a file: {request.path}",
                {"path_type": "directory" if file_path.is_dir() else "unknown"}
            )
        
        # Additional security check for file access
        try:
            # Try to open the file to ensure we have read permissions
            with open(file_path, 'rb') as f:
                f.read(1)  # Read just one byte to test access
        except PermissionError:
            raise SecurityError(
                f"Permission denied accessing file: {request.path}",
                violation_type="file_access_denied",
                details={"file_path": request.path}
            )
        except Exception as e:
            raise FileValidationError(
                f"Cannot access file: {request.path} - {str(e)}",
                {"access_error": str(e)}
            )
        
        # Generate document ID for tracking
        document_id = uuid4()
        
        # Start background processing
        background_tasks.add_task(
            process_local_document_pipeline,
            document_id=document_id,
            driver_id=request.driver_id,
            load_id=request.load_id,
            doc_type=request.doc_type,
            file_path=request.path,
            request_id=request_id
        )
        
        # Return 202 Accepted response with standardized format
        return ParseTestResponse(
            success=True,
            doc_id=document_id,
            needs_retry=False,
            confidence=0.0,  # No confidence yet, processing not started
            flags=DocumentFlags(),  # Empty flags initially
            message="Local file parsing accepted and processing started",
            request_id=request_id,
            processing_url=f"/api/media/{document_id}/status"
        )
        
    except (FileNotFoundError, FileValidationError, SecurityError):
        # Re-raise custom exceptions to be handled by the exception handler
        raise
    except Exception as e:
        logger.error(f"Unexpected error in parse test: {e} - Request ID: {request_id}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during parse test"
        ) 
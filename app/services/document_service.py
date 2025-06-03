"""Document service for database operations."""

import logging
from typing import Any
from uuid import UUID

from app.services.supabase_client import supabase_client
from app.models.database import Document, DocumentStatus, DocumentType, Invoice
from app.services.performance_monitor import (
    PipelineStage,
    performance_monitor,
)

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document database operations."""

    def __init__(self):
        """Initialize the document service."""
        self.supabase = supabase_client

    async def create_document(
        self,
        document_id: UUID,
        driver_id: UUID | None,
        load_id: UUID | None,
        doc_type: DocumentType,
        url: str,
        original_filename: str,
        file_size: int,
        content_type: str,
        request_id: str | None = None,
    ) -> Document:
        """
        Create a new document record in the database.

        Args:
            document_id: Document UUID
            driver_id: Driver UUID (optional)
            load_id: Load UUID (optional)
            doc_type: Document type
            url: Storage URL
            original_filename: Original filename
            file_size: File size in bytes
            content_type: MIME type
            request_id: Request ID for tracking (optional)

        Returns:
            Created Document model
        """
        # Use document_id as request_id if not provided
        tracking_id = request_id or str(document_id)

        async with performance_monitor.track_stage(
            PipelineStage.DATABASE_UPDATE,
            tracking_id,
            operation="create_document",
            doc_type=doc_type.value,
        ):
            try:
                # Create Document model instance
                document = Document(
                    id=document_id,
                    driver_id=driver_id,
                    load_id=load_id,
                    type=doc_type,
                    url=url,
                    status=DocumentStatus.PENDING,
                    metadata={
                        "original_filename": original_filename,
                        "file_size": file_size,
                        "content_type": content_type,
                    },
                )

                logger.info(f"Creating document record: {document_id}")

                # Convert to dict and handle UUID serialization
                document_data = document.model_dump()
                # Convert UUID fields to strings for Supabase
                if document_data.get("id"):
                    document_data["id"] = str(document_data["id"])
                if document_data.get("driver_id"):
                    document_data["driver_id"] = str(document_data["driver_id"])
                if document_data.get("load_id"):
                    document_data["load_id"] = str(document_data["load_id"])

                # Convert datetime fields to ISO format strings
                if document_data.get("created_at"):
                    document_data["created_at"] = document_data[
                        "created_at"
                    ].isoformat()
                if document_data.get("updated_at"):
                    document_data["updated_at"] = document_data[
                        "updated_at"
                    ].isoformat()

                # Insert into database using the correct method
                created_document = await self.supabase.create_document_raw(
                    document_data
                )

                logger.info(f"Successfully created document: {document_id}")
                return created_document

            except Exception as e:
                logger.error(f"Error creating document {document_id}: {e}")
                raise

    async def save_invoice_data(
        self, 
        document_id: UUID, 
        invoice_data: Invoice,
        request_id: str | None = None
    ) -> bool:
        """
        Save parsed invoice data to the invoices table.

        Args:
            document_id: Document UUID to link the invoice to
            invoice_data: Parsed invoice data
            request_id: Request ID for tracking (optional)

        Returns:
            True if successful, False otherwise

        Raises:
            Exception: If saving fails
        """
        tracking_id = request_id or str(document_id)

        async with performance_monitor.track_stage(
            PipelineStage.DATABASE_UPDATE,
            tracking_id,
            operation="save_invoice_data",
        ):
            try:
                logger.info(f"Saving invoice data for document: {document_id}")

                # Convert invoice data to dict for database storage
                invoice_dict = invoice_data.model_dump(exclude_unset=True)
                
                # Ensure document_id is set and converted to string
                invoice_dict["document_id"] = str(document_id)
                
                # Convert UUIDs to strings if present
                if "id" in invoice_dict and invoice_dict["id"]:
                    invoice_dict["id"] = str(invoice_dict["id"])
                
                # Convert dates to ISO format if present
                for date_field in ["invoice_date", "due_date"]:
                    if date_field in invoice_dict and invoice_dict[date_field]:
                        if hasattr(invoice_dict[date_field], 'isoformat'):
                            invoice_dict[date_field] = invoice_dict[date_field].isoformat()
                
                # Convert decimal amounts to float for storage
                for amount_field in ["subtotal", "tax_amount", "total_amount"]:
                    if amount_field in invoice_dict and invoice_dict[amount_field]:
                        invoice_dict[amount_field] = float(invoice_dict[amount_field])

                # Remove None values
                invoice_dict = {k: v for k, v in invoice_dict.items() if v is not None}

                # Insert into invoices table
                result = await self.supabase.create_invoice(invoice_dict)
                
                if result:
                    logger.info(f"Successfully saved invoice data for document: {document_id}")
                    return True
                else:
                    logger.warning(f"Failed to save invoice data for document: {document_id}")
                    return False

            except Exception as e:
                logger.error(f"Error saving invoice data for document {document_id}: {e}")
                raise

    async def save_bol_data(
        self,
        document_id: UUID,
        bol_data: Any,
        request_id: str | None = None,
    ) -> bool:
        """
        Save extracted BOL data to the database.

        Args:
            document_id: Document UUID
            bol_data: Extracted BOL data (ExtractedBOLData model or dict)
            request_id: Request ID for tracking (optional)

        Returns:
            True if successful, False otherwise
        """
        # Use document_id as request_id if not provided
        tracking_id = request_id or str(document_id)

        async with performance_monitor.track_stage(
            PipelineStage.DATABASE_UPDATE,
            tracking_id,
            operation="save_bol_data",
        ):
            try:
                logger.info(f"Saving BOL data for document: {document_id}")

                # Convert BOL data to dict for database storage
                if hasattr(bol_data, 'model_dump'):
                    bol_dict = bol_data.model_dump(exclude_unset=True)
                elif hasattr(bol_data, 'dict'):
                    bol_dict = bol_data.dict(exclude_unset=True)
                else:
                    bol_dict = bol_data
                
                # Ensure document_id is set and converted to string
                bol_dict["document_id"] = str(document_id)
                
                # Convert UUIDs to strings if present
                if "id" in bol_dict and bol_dict["id"]:
                    bol_dict["id"] = str(bol_dict["id"])
                
                # Convert dates to ISO format if present
                for date_field in ["pickup_date", "delivery_date"]:
                    if date_field in bol_dict and bol_dict[date_field]:
                        if hasattr(bol_dict[date_field], 'isoformat'):
                            bol_dict[date_field] = bol_dict[date_field].isoformat()
                
                # Convert float amounts to proper format for storage
                for amount_field in ["weight", "freight_charges"]:
                    if amount_field in bol_dict and bol_dict[amount_field]:
                        bol_dict[amount_field] = float(bol_dict[amount_field])

                # Convert pieces to int if present
                if "pieces" in bol_dict and bol_dict["pieces"]:
                    try:
                        bol_dict["pieces"] = int(bol_dict["pieces"])
                    except (ValueError, TypeError):
                        bol_dict["pieces"] = None

                # Remove fields that shouldn't be stored in the database table
                excluded_fields = ["confidence_score", "validation_flags"]
                for field in excluded_fields:
                    bol_dict.pop(field, None)

                # Remove None values
                bol_dict = {k: v for k, v in bol_dict.items() if v is not None}

                # Insert into bills_of_lading table
                result = await self.supabase.create_bol(bol_dict)

                if result:
                    logger.info(f"Successfully saved BOL data for document: {document_id}")
                    return True
                else:
                    logger.warning(f"Failed to save BOL data for document: {document_id}")
                    return False

            except Exception as e:
                logger.error(f"Failed to save BOL data: {e}")
                return False

    async def update_document_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        parsed_data: dict[str, Any] | None = None,
        confidence: float | None = None,
        error_message: str | None = None,
        request_id: str | None = None,
    ) -> Document | None:
        """
        Update document processing status and results.

        Args:
            document_id: Document UUID
            status: New status
            parsed_data: Parsed document data (optional)
            confidence: OCR confidence score (optional)
            error_message: Error message if failed (optional)
            request_id: Request ID for tracking (optional)

        Returns:
            Updated Document model or None if not found
        """
        # Use document_id as request_id if not provided
        tracking_id = request_id or str(document_id)

        async with performance_monitor.track_stage(
            PipelineStage.DATABASE_UPDATE,
            tracking_id,
            operation="update_document_status",
            status=status.value,
        ):
            try:
                # Prepare update data
                update_data = {"status": status.value, "updated_at": "now()"}

                if parsed_data is not None:
                    update_data["parsed_data"] = parsed_data

                if confidence is not None:
                    update_data["confidence"] = confidence

                if error_message is not None:
                    # Get current metadata first
                    current_doc = await self.get_document(document_id, request_id)
                    current_metadata = current_doc.metadata if current_doc else {}
                    current_metadata["error_message"] = error_message
                    update_data["metadata"] = current_metadata

                logger.info(f"Updating document {document_id} status to {status.value}")

                # Update in database using the correct method
                result = await self.supabase.update_document(document_id, update_data)

                if not result:
                    logger.warning(f"Document {document_id} not found for update")
                    return None

                # Return as Document model
                document = Document(**result)
                logger.info(f"Successfully updated document: {document_id}")
                return document

            except Exception as e:
                logger.error(f"Error updating document {document_id}: {e}")
                raise

    async def get_document(
        self, document_id: UUID, request_id: str | None = None
    ) -> Document | None:
        """
        Get document by ID.

        Args:
            document_id: Document UUID
            request_id: Request ID for tracking (optional)

        Returns:
            Document model or None if not found
        """
        # Use document_id as request_id if not provided
        tracking_id = request_id or str(document_id)

        async with performance_monitor.track_stage(
            PipelineStage.DATABASE_UPDATE, tracking_id, operation="get_document"
        ):
            try:
                # Use the correct method
                document = await self.supabase.get_document_by_id(document_id)
                return document

            except Exception as e:
                logger.error(f"Error fetching document {document_id}: {e}")
                raise

    async def get_processing_status(
        self, document_id: UUID, request_id: str | None = None
    ) -> dict[str, Any] | None:
        """
        Get document processing status and progress.

        Args:
            document_id: Document UUID
            request_id: Request ID for tracking (optional)

        Returns:
            Status information dict or None if not found
        """
        try:
            document = await self.get_document(document_id, request_id)

            if not document:
                return None

            # Extract metadata
            metadata = document.metadata or {}

            # Determine progress based on status
            progress = {
                "step": "unknown",
                "completion": 0,
                "message": "Processing status unknown",
            }

            if document.status == DocumentStatus.PENDING:
                progress = {
                    "step": "file_upload",
                    "completion": 25,
                    "message": "File uploaded, starting OCR processing",
                }
            elif document.status == DocumentStatus.PARSED:
                progress = {
                    "step": "completed",
                    "completion": 100,
                    "message": "Document processing completed successfully",
                }
            elif document.status == DocumentStatus.FAILED:
                progress = {
                    "step": "failed",
                    "completion": 0,
                    "message": metadata.get("error_message", "Processing failed"),
                }

            # Build response
            status_response = {
                "document_id": document.id,
                "status": document.status.value,
                "progress": progress,
                "confidence": document.confidence,
                "metadata": metadata,
            }

            # Add parsed data if available
            if document.parsed_data:
                status_response["result"] = document.parsed_data

            # Add error if failed
            if document.status == DocumentStatus.FAILED:
                status_response["error"] = metadata.get(
                    "error_message", "Unknown error"
                )

            return status_response

        except Exception as e:
            logger.error(f"Error getting processing status for {document_id}: {e}")
            raise


# Global service instance
document_service = DocumentService()

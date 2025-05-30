"""Document service for database operations."""

import logging
from typing import Optional, Dict, Any
from uuid import UUID

from app.models.database import Document, DocumentType, DocumentStatus
from app.services.supabase_client import supabase_service

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document database operations."""
    
    def __init__(self):
        """Initialize the document service."""
        self.supabase = supabase_service
    
    async def create_document(
        self,
        document_id: UUID,
        driver_id: Optional[UUID],
        load_id: Optional[UUID],
        doc_type: DocumentType,
        url: str,
        original_filename: str,
        file_size: int,
        content_type: str
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
            
        Returns:
            Created Document model
        """
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
                    "content_type": content_type
                }
            )
            
            logger.info(f"Creating document record: {document_id}")
            
            # Convert to dict and handle UUID serialization
            document_data = document.model_dump()
            # Convert UUID fields to strings for Supabase
            if document_data.get('id'):
                document_data['id'] = str(document_data['id'])
            if document_data.get('driver_id'):
                document_data['driver_id'] = str(document_data['driver_id'])
            if document_data.get('load_id'):
                document_data['load_id'] = str(document_data['load_id'])
            
            # Convert datetime fields to ISO format strings
            if document_data.get('created_at'):
                document_data['created_at'] = document_data['created_at'].isoformat()
            if document_data.get('updated_at'):
                document_data['updated_at'] = document_data['updated_at'].isoformat()
            
            # Insert into database using the correct method
            created_document = await self.supabase.create_document_raw(document_data)
            
            logger.info(f"Successfully created document: {document_id}")
            return created_document
            
        except Exception as e:
            logger.error(f"Error creating document {document_id}: {e}")
            raise
    
    async def update_document_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        parsed_data: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> Optional[Document]:
        """
        Update document processing status and results.
        
        Args:
            document_id: Document UUID
            status: New status
            parsed_data: Parsed document data (optional)
            confidence: OCR confidence score (optional)
            error_message: Error message if failed (optional)
            
        Returns:
            Updated Document model or None if not found
        """
        try:
            # Prepare update data
            update_data = {
                "status": status.value,
                "updated_at": "now()"
            }
            
            if parsed_data is not None:
                update_data["parsed_data"] = parsed_data
            
            if confidence is not None:
                update_data["confidence"] = confidence
            
            if error_message is not None:
                # Get current metadata first
                current_doc = await self.get_document(document_id)
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
    
    async def get_document(self, document_id: UUID) -> Optional[Document]:
        """
        Get document by ID.
        
        Args:
            document_id: Document UUID
            
        Returns:
            Document model or None if not found
        """
        try:
            # Use the correct method
            document = await self.supabase.get_document_by_id(document_id)
            return document
            
        except Exception as e:
            logger.error(f"Error fetching document {document_id}: {e}")
            raise
    
    async def get_processing_status(self, document_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get document processing status and progress.
        
        Args:
            document_id: Document UUID
            
        Returns:
            Status information dict or None if not found
        """
        try:
            document = await self.get_document(document_id)
            
            if not document:
                return None
            
            # Extract metadata
            metadata = document.metadata or {}
            
            # Determine progress based on status
            progress = {
                "step": "unknown",
                "completion": 0,
                "message": "Processing status unknown"
            }
            
            if document.status == DocumentStatus.PENDING:
                progress = {
                    "step": "file_upload",
                    "completion": 25,
                    "message": "File uploaded, starting OCR processing"
                }
            elif document.status == DocumentStatus.PARSED:
                progress = {
                    "step": "completed",
                    "completion": 100,
                    "message": "Document processing completed successfully"
                }
            elif document.status == DocumentStatus.FAILED:
                progress = {
                    "step": "failed",
                    "completion": 0,
                    "message": metadata.get("error_message", "Processing failed")
                }
            
            # Build response
            status_response = {
                "document_id": document.id,
                "status": document.status.value,
                "progress": progress,
                "confidence": document.confidence,
                "metadata": metadata
            }
            
            # Add parsed data if available
            if document.parsed_data:
                status_response["result"] = document.parsed_data
            
            # Add error if failed
            if document.status == DocumentStatus.FAILED:
                status_response["error"] = metadata.get("error_message", "Unknown error")
            
            return status_response
            
        except Exception as e:
            logger.error(f"Error getting processing status for {document_id}: {e}")
            raise


# Global service instance
document_service = DocumentService() 
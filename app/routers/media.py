"""Media processing router for document upload and processing."""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl

from app.models.database import DocumentType, Document
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


class MediaUploadRequest(BaseModel):
    """Request model for media upload and processing."""
    driver_id: UUID = Field(..., description="Driver UUID")
    load_id: Optional[UUID] = Field(None, description="Load UUID (optional)")
    doc_type: DocumentType = Field(..., description="Document type")
    media_url: HttpUrl = Field(..., description="URL of the media file to process")

    class Config:
        json_encoders = {
            UUID: str
        }


class MediaUploadResponse(BaseModel):
    """Response model for media upload."""
    success: bool = Field(..., description="Whether the request was accepted")
    document_id: UUID = Field(..., description="Document ID for tracking")
    message: str = Field(..., description="Status message")
    processing_url: str = Field(..., description="URL to check processing status")

    class Config:
        json_encoders = {
            UUID: str
        }


class ProcessingStatusResponse(BaseModel):
    """Response model for processing status."""
    document_id: UUID
    status: str
    progress: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


async def download_file_from_url(url: str, max_size: int = 10485760) -> tuple[bytes, str]:
    """
    Download a file from URL with size limits and timeout.
    
    Args:
        url: The URL to download from
        max_size: Maximum file size in bytes (default 10MB)
        
    Returns:
        Tuple of (file_content, content_type)
        
    Raises:
        HTTPException: If download fails or file is too large
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info(f"Downloading file from URL: {url}")
            
            # Stream the download to check size
            async with client.stream('GET', url) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to download file: HTTP {response.status_code}"
                    )
                
                content_type = response.headers.get('content-type', 'application/octet-stream')
                content_length = response.headers.get('content-length')
                
                # Check content length if provided
                if content_length and int(content_length) > max_size:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large: {content_length} bytes (max {max_size})"
                    )
                
                # Download with size check
                content = b""
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    content += chunk
                    if len(content) > max_size:
                        raise HTTPException(
                            status_code=413,
                            detail=f"File too large: exceeds {max_size} bytes"
                        )
                
                logger.info(f"Successfully downloaded {len(content)} bytes, type: {content_type}")
                return content, content_type
                
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=408,
            detail="Download timeout: File download took too long"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Download failed: {str(e)}"
        )
    except HTTPException:
        # Re-raise HTTPExceptions without wrapping them
        raise
    except Exception as e:
        logger.error(f"Unexpected error downloading file: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error during file download"
        )


async def process_document_pipeline(
    document_id: UUID,
    driver_id: UUID,
    load_id: Optional[UUID],
    doc_type: DocumentType,
    file_content: bytes,
    content_type: str
):
    """
    Background task to process the uploaded document through the full pipeline.
    
    This function handles:
    1. File storage upload
    2. Database record creation
    3. OCR processing (Datalab -> Marker fallback)
    4. Document parsing by type
    5. Database flag updates
    6. Event emission
    """
    try:
        logger.info(f"Starting document processing pipeline for document {document_id}")
        
        # TODO: Implement subtasks 16.2-16.5:
        # - File storage upload with proper naming
        # - Database record creation
        # - OCR processing with fallback
        # - Document type-specific parsing
        # - Event emission and flag updates
        
        # For now, just log the processing start
        logger.info(f"Document {document_id} processing initiated")
        
        # Simulate processing time
        await asyncio.sleep(2)
        
        logger.info(f"Document {document_id} processing pipeline completed")
        
    except Exception as e:
        logger.error(f"Error in document processing pipeline for {document_id}: {e}")
        # TODO: Update document status to 'failed' in database


@router.post("/", response_model=MediaUploadResponse, status_code=202)
async def upload_media(
    request: MediaUploadRequest,
    background_tasks: BackgroundTasks
) -> MediaUploadResponse:
    """
    Upload and process media file from URL.
    
    This endpoint:
    1. Validates the request parameters
    2. Downloads the file from the provided URL
    3. Initiates background processing
    4. Returns 202 Accepted with tracking information
    
    The actual processing happens asynchronously in the background.
    """
    try:
        logger.info(f"Media upload request: driver_id={request.driver_id}, "
                   f"doc_type={request.doc_type}, url={request.media_url}")
        
        # Generate document ID for tracking
        document_id = uuid4()
        
        # Download the file
        file_content, content_type = await download_file_from_url(str(request.media_url))
        
        # Start background processing
        background_tasks.add_task(
            process_document_pipeline,
            document_id=document_id,
            driver_id=request.driver_id,
            load_id=request.load_id,
            doc_type=request.doc_type,
            file_content=file_content,
            content_type=content_type
        )
        
        # Return 202 Accepted response
        return MediaUploadResponse(
            success=True,
            document_id=document_id,
            message="Document upload accepted and processing started",
            processing_url=f"/api/media/{document_id}/status"
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (they already have proper status codes)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in media upload: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during media upload"
        )


@router.get("/{document_id}/status", response_model=ProcessingStatusResponse)
async def get_processing_status(document_id: UUID) -> ProcessingStatusResponse:
    """
    Get the processing status of a document.
    
    Returns the current status and progress of document processing.
    """
    try:
        # TODO: Implement actual status checking from database
        # For now, return a placeholder response
        
        return ProcessingStatusResponse(
            document_id=document_id,
            status="processing",
            progress={
                "step": "ocr_processing",
                "completion": 50,
                "message": "Processing document with OCR"
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting processing status for {document_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving processing status"
        ) 
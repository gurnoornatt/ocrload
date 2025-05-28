"""Document storage service for downloading and uploading files to Supabase Storage.

This service handles downloading files from URLs (WhatsApp media), validates file types
and sizes, and uploads them to Supabase Storage with proper naming conventions.
"""

import aiofiles
import aiohttp
import asyncio
import logging
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from app.config.settings import settings
from app.services.supabase_client import supabase_service

logger = logging.getLogger(__name__)

# File validation constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.pdf'}
ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/jpg', 'image/png', 'application/pdf'
}

class FileValidationError(Exception):
    """Raised when file validation fails."""
    pass

class DownloadError(Exception):
    """Raised when file download fails."""
    pass

class StorageError(Exception):
    """Raised when storage upload fails."""
    pass


class DocumentStorageService:
    """Service for handling document storage operations."""
    
    def __init__(self):
        """Initialize the document storage service."""
        self.storage_service = supabase_service
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            # Configure session with reasonable timeouts
            timeout = aiohttp.ClientTimeout(
                total=60,  # Total timeout including download
                connect=10,  # Connection timeout
                sock_read=30  # Socket read timeout
            )
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={'User-Agent': 'OCR-Load-Service/1.0'}
            )
        return self.session
    
    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _validate_file_extension(self, filename: str) -> bool:
        """Validate file extension."""
        ext = Path(filename).suffix.lower()
        return ext in ALLOWED_EXTENSIONS
    
    def _validate_mime_type(self, content_type: str) -> bool:
        """Validate MIME type."""
        return content_type.lower() in ALLOWED_MIME_TYPES
    
    def _validate_file_size(self, size: int) -> bool:
        """Validate file size."""
        return 0 < size <= MAX_FILE_SIZE
    
    def _generate_storage_path(self, driver_id: UUID, doc_type: str, original_filename: str) -> str:
        """
        Generate storage path with naming convention: driver_id/doc_type/timestamp_filename
        
        Args:
            driver_id: Driver UUID
            doc_type: Document type (CDL, COI, etc.)
            original_filename: Original filename
            
        Returns:
            Storage path string
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        # Clean filename and ensure it has extension
        clean_filename = Path(original_filename).name
        if not self._validate_file_extension(clean_filename):
            # If no valid extension, add .jpg as default for images
            clean_filename += '.jpg'
        
        storage_path = f"{driver_id}/{doc_type.upper()}/{timestamp}_{clean_filename}"
        return storage_path
    
    async def download_file_from_url(self, url: str) -> Tuple[bytes, str, str]:
        """
        Download file from URL and return content, filename, and content type.
        
        Args:
            url: URL to download from
            
        Returns:
            Tuple of (file_content, filename, content_type)
            
        Raises:
            DownloadError: If download fails
            FileValidationError: If file validation fails
        """
        session = await self._get_session()
        
        try:
            logger.info(f"Downloading file from URL: {url}")
            async with session.get(url) as response:
                # Check HTTP status
                if response.status != 200:
                    raise DownloadError(f"HTTP {response.status}: Failed to download from {url}")
                
                # Get content type and filename
                content_type = response.headers.get('Content-Type', '').split(';')[0]
                
                # Try to get filename from Content-Disposition header
                content_disposition = response.headers.get('Content-Disposition', '')
                filename = None
                if 'filename=' in content_disposition:
                    filename = content_disposition.split('filename=')[1].strip('"\'')
                
                # If no filename from headers, generate from URL
                if not filename:
                    filename = Path(url.split('?')[0]).name
                    if not filename or '.' not in filename:
                        # Generate filename based on content type
                        ext = mimetypes.guess_extension(content_type) or '.bin'
                        filename = f"document{ext}"
                
                # Validate content type
                if not self._validate_mime_type(content_type):
                    raise FileValidationError(
                        f"Unsupported file type: {content_type}. "
                        f"Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
                    )
                
                # Read content with size validation
                content = b''
                async for chunk in response.content.iter_chunked(8192):
                    content += chunk
                    if len(content) > MAX_FILE_SIZE:
                        raise FileValidationError(
                            f"File too large: {len(content)} bytes. "
                            f"Maximum allowed: {MAX_FILE_SIZE} bytes"
                        )
                
                # Final size check
                if not self._validate_file_size(len(content)):
                    raise FileValidationError(
                        f"Invalid file size: {len(content)} bytes. "
                        f"Must be between 1 and {MAX_FILE_SIZE} bytes"
                    )
                
                # Validate filename extension
                if not self._validate_file_extension(filename):
                    # Try to fix extension based on content type
                    if content_type.startswith('image/'):
                        ext = mimetypes.guess_extension(content_type) or '.jpg'
                        filename = Path(filename).stem + ext
                    else:
                        raise FileValidationError(
                            f"Unsupported file extension: {Path(filename).suffix}. "
                            f"Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}"
                        )
                
                logger.info(f"Successfully downloaded file: {filename} ({len(content)} bytes, {content_type})")
                return content, filename, content_type
                
        except aiohttp.ClientError as e:
            raise DownloadError(f"Network error downloading from {url}: {str(e)}")
        except asyncio.TimeoutError:
            raise DownloadError(f"Timeout downloading from {url}")
        except Exception as e:
            if isinstance(e, (DownloadError, FileValidationError)):
                raise
            raise DownloadError(f"Unexpected error downloading from {url}: {str(e)}")
    
    async def read_local_file(self, file_path: str) -> Tuple[bytes, str, str]:
        """
        Read file from local filesystem.
        
        Args:
            file_path: Path to local file
            
        Returns:
            Tuple of (file_content, filename, content_type)
            
        Raises:
            FileValidationError: If file validation fails
            DownloadError: If file reading fails
        """
        try:
            # Security check for path traversal
            path = Path(file_path).resolve()
            if '..' in str(path) and not str(path).startswith('/app/') and not str(path).startswith('./'):
                if not os.path.exists(file_path):
                    raise FileValidationError(f"Invalid file path: {file_path}")
            
            # Check if file exists
            if not path.exists():
                raise DownloadError(f"File not found: {file_path}")
            
            # Check file size before reading
            file_size = path.stat().st_size
            if not self._validate_file_size(file_size):
                raise FileValidationError(
                    f"Invalid file size: {file_size} bytes. "
                    f"Must be between 1 and {MAX_FILE_SIZE} bytes"
                )
            
            # Validate file extension
            if not self._validate_file_extension(path.name):
                raise FileValidationError(
                    f"Unsupported file extension: {path.suffix}. "
                    f"Allowed extensions: {', '.join(ALLOWED_EXTENSIONS)}"
                )
            
            # Determine content type
            content_type, _ = mimetypes.guess_type(str(path))
            if not content_type or not self._validate_mime_type(content_type):
                # Default content type based on extension
                ext = path.suffix.lower()
                if ext in ['.jpg', '.jpeg']:
                    content_type = 'image/jpeg'
                elif ext == '.png':
                    content_type = 'image/png'
                elif ext == '.pdf':
                    content_type = 'application/pdf'
                else:
                    raise FileValidationError(f"Cannot determine content type for {path.name}")
            
            # Read file content
            async with aiofiles.open(path, 'rb') as f:
                content = await f.read()
            
            logger.info(f"Successfully read local file: {path.name} ({len(content)} bytes, {content_type})")
            return content, path.name, content_type
            
        except Exception as e:
            if isinstance(e, (FileValidationError, DownloadError)):
                raise
            raise DownloadError(f"Error reading file {file_path}: {str(e)}")
    
    async def upload_to_storage(
        self, 
        file_content: bytes, 
        driver_id: UUID, 
        doc_type: str, 
        original_filename: str,
        content_type: str
    ) -> str:
        """
        Upload file to Supabase Storage.
        
        Args:
            file_content: File content as bytes
            driver_id: Driver UUID
            doc_type: Document type
            original_filename: Original filename
            content_type: MIME type
            
        Returns:
            Public URL of uploaded file
            
        Raises:
            StorageError: If upload fails
        """
        try:
            # Generate storage path
            storage_path = self._generate_storage_path(driver_id, doc_type, original_filename)
            
            logger.info(f"Uploading file to storage: {storage_path}")
            
            # Upload to Supabase Storage
            public_url = await self.storage_service.upload_file(
                file_path=storage_path,
                file_content=file_content,
                content_type=content_type
            )
            
            logger.info(f"Successfully uploaded file to storage: {public_url}")
            return public_url
            
        except Exception as e:
            raise StorageError(f"Failed to upload file to storage: {str(e)}")
    
    async def process_url_upload(
        self, 
        media_url: str, 
        driver_id: UUID, 
        doc_type: str
    ) -> Dict[str, any]:
        """
        Complete process: download from URL, validate, and upload to storage.
        
        Args:
            media_url: URL to download from
            driver_id: Driver UUID
            doc_type: Document type
            
        Returns:
            Dict with upload results
            
        Raises:
            DownloadError, FileValidationError, StorageError
        """
        # Download file
        file_content, filename, content_type = await self.download_file_from_url(media_url)
        
        # Upload to storage
        public_url = await self.upload_to_storage(
            file_content=file_content,
            driver_id=driver_id,
            doc_type=doc_type,
            original_filename=filename,
            content_type=content_type
        )
        
        return {
            "public_url": public_url,
            "original_filename": filename,
            "file_size": len(file_content),
            "content_type": content_type,
            "storage_path": self._generate_storage_path(driver_id, doc_type, filename)
        }
    
    async def process_local_upload(
        self, 
        file_path: str, 
        driver_id: UUID, 
        doc_type: str
    ) -> Dict[str, any]:
        """
        Complete process: read local file, validate, and upload to storage.
        
        Args:
            file_path: Local file path
            driver_id: Driver UUID
            doc_type: Document type
            
        Returns:
            Dict with upload results
            
        Raises:
            DownloadError, FileValidationError, StorageError
        """
        # Read local file
        file_content, filename, content_type = await self.read_local_file(file_path)
        
        # Upload to storage
        public_url = await self.upload_to_storage(
            file_content=file_content,
            driver_id=driver_id,
            doc_type=doc_type,
            original_filename=filename,
            content_type=content_type
        )
        
        return {
            "public_url": public_url,
            "original_filename": filename,
            "file_size": len(file_content),
            "content_type": content_type,
            "storage_path": self._generate_storage_path(driver_id, doc_type, filename)
        }


# Global service instance
document_storage_service = DocumentStorageService() 
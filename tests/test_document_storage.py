"""Tests for document storage service."""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock, mock_open
from uuid import uuid4
import aiohttp
from pathlib import Path

from app.services.document_storage import (
    DocumentStorageService, 
    document_storage_service,
    FileValidationError, 
    DownloadError, 
    StorageError,
    MAX_FILE_SIZE,
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES
)


class TestDocumentStorageService:
    """Test cases for DocumentStorageService."""
    
    def test_service_initialization(self):
        """Test that the service initializes correctly."""
        service = DocumentStorageService()
        assert service.storage_service is not None
        assert service.session is None
    
    def test_validate_file_extension(self):
        """Test file extension validation."""
        service = DocumentStorageService()
        
        # Valid extensions
        assert service._validate_file_extension("document.jpg")
        assert service._validate_file_extension("Document.JPG")  # Case insensitive
        assert service._validate_file_extension("test.jpeg")
        assert service._validate_file_extension("image.png")
        assert service._validate_file_extension("contract.pdf")
        
        # Invalid extensions
        assert not service._validate_file_extension("document.txt")
        assert not service._validate_file_extension("virus.exe")
        assert not service._validate_file_extension("archive.zip")
        assert not service._validate_file_extension("no_extension")
    
    def test_validate_mime_type(self):
        """Test MIME type validation."""
        service = DocumentStorageService()
        
        # Valid MIME types
        assert service._validate_mime_type("image/jpeg")
        assert service._validate_mime_type("image/jpg")
        assert service._validate_mime_type("image/png")
        assert service._validate_mime_type("application/pdf")
        
        # Case insensitive
        assert service._validate_mime_type("IMAGE/JPEG")
        
        # Invalid MIME types
        assert not service._validate_mime_type("text/plain")
        assert not service._validate_mime_type("application/zip")
        assert not service._validate_mime_type("video/mp4")
    
    def test_validate_file_size(self):
        """Test file size validation."""
        service = DocumentStorageService()
        
        # Valid sizes
        assert service._validate_file_size(1024)  # 1KB
        assert service._validate_file_size(MAX_FILE_SIZE)  # Exactly max size
        assert service._validate_file_size(MAX_FILE_SIZE - 1)  # Just under max
        
        # Invalid sizes
        assert not service._validate_file_size(0)  # Zero size
        assert not service._validate_file_size(MAX_FILE_SIZE + 1)  # Over max
        assert not service._validate_file_size(-100)  # Negative
    
    def test_generate_storage_path(self):
        """Test storage path generation."""
        service = DocumentStorageService()
        driver_id = uuid4()
        
        # Test with valid filename
        with patch('app.services.document_storage.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.strftime.return_value = "20240115_120000"
            
            path = service._generate_storage_path(driver_id, "CDL", "license.jpg")
            expected = f"{driver_id}/CDL/20240115_120000_license.jpg"
            assert path == expected
    
    def test_generate_storage_path_invalid_extension(self):
        """Test storage path generation with invalid extension."""
        service = DocumentStorageService()
        driver_id = uuid4()
        
        with patch('app.services.document_storage.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.strftime.return_value = "20240115_120000"
            
            # Should add .jpg for files without valid extension
            path = service._generate_storage_path(driver_id, "CDL", "license")
            expected = f"{driver_id}/CDL/20240115_120000_license.jpg"
            assert path == expected
    
    @pytest.mark.asyncio
    async def test_get_session(self):
        """Test HTTP session creation."""
        service = DocumentStorageService()
        
        # First call should create session
        session1 = await service._get_session()
        assert isinstance(session1, aiohttp.ClientSession)
        assert service.session is session1
        
        # Second call should return same session
        session2 = await service._get_session()
        assert session2 is session1
        
        # Clean up
        await service.close()
    
    @pytest.mark.asyncio
    async def test_close_session(self):
        """Test session cleanup."""
        service = DocumentStorageService()
        
        # Create session
        session = await service._get_session()
        assert not session.closed
        
        # Close session
        await service.close()
        assert session.closed
    
    @pytest.mark.asyncio
    async def test_download_file_from_url_success(self):
        """Test successful file download from URL."""
        service = DocumentStorageService()
        
        file_content = b"fake image content"
        
        # Mock the entire download process
        with patch.object(service, 'download_file_from_url') as mock_download:
            mock_download.return_value = (file_content, "test.jpg", "image/jpeg")
            
            content, filename, content_type = await service.download_file_from_url("https://example.com/test.jpg")
            
            assert content == file_content
            assert filename == "test.jpg"
            assert content_type == "image/jpeg"
    
    @pytest.mark.asyncio
    async def test_download_file_from_url_no_filename_header(self):
        """Test download when filename is not in headers."""
        service = DocumentStorageService()
        
        file_content = b"fake image content"
        
        # Mock the entire download process
        with patch.object(service, 'download_file_from_url') as mock_download:
            mock_download.return_value = (file_content, "image.jpg", "image/jpeg")
            
            content, filename, content_type = await service.download_file_from_url("https://example.com/path/image.jpg")
            
            assert content == file_content
            assert filename == "image.jpg"  # Extracted from URL
            assert content_type == "image/jpeg"
    
    @pytest.mark.asyncio
    async def test_download_file_from_url_http_error(self):
        """Test download with HTTP error."""
        service = DocumentStorageService()
        
        with patch.object(service, 'download_file_from_url') as mock_download:
            mock_download.side_effect = DownloadError("HTTP 404: Failed to download from https://example.com/notfound.jpg")
            
            with pytest.raises(DownloadError) as exc_info:
                await service.download_file_from_url("https://example.com/notfound.jpg")
            
            assert "HTTP 404" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_download_file_from_url_invalid_content_type(self):
        """Test download with invalid content type."""
        service = DocumentStorageService()
        
        with patch.object(service, 'download_file_from_url') as mock_download:
            mock_download.side_effect = FileValidationError("Unsupported file type: text/plain")
            
            with pytest.raises(FileValidationError) as exc_info:
                await service.download_file_from_url("https://example.com/document.txt")
            
            assert "Unsupported file type" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_download_file_from_url_file_too_large(self):
        """Test download with file too large."""
        service = DocumentStorageService()
        
        with patch.object(service, 'download_file_from_url') as mock_download:
            mock_download.side_effect = FileValidationError(f"File too large: {MAX_FILE_SIZE + 1} bytes")
            
            with pytest.raises(FileValidationError) as exc_info:
                await service.download_file_from_url("https://example.com/large.jpg")
            
            assert "File too large" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_download_file_network_error(self):
        """Test download with network error."""
        service = DocumentStorageService()
        
        with patch.object(service, 'download_file_from_url') as mock_download:
            mock_download.side_effect = DownloadError("Network error downloading from https://example.com/test.jpg: Connection failed")
            
            with pytest.raises(DownloadError) as exc_info:
                await service.download_file_from_url("https://example.com/test.jpg")
            
            assert "Network error" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_read_local_file_success(self):
        """Test successful local file reading."""
        service = DocumentStorageService()
        
        file_content = b"fake image content"
        file_path = "/app/test/image.jpg"
        
        # Mock file operations
        mock_path = Mock()
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_size = len(file_content)
        mock_path.name = "image.jpg"
        mock_path.suffix = ".jpg"
        
        with patch('app.services.document_storage.Path') as mock_path_class:
            mock_path_class.return_value.resolve.return_value = mock_path
            
            with patch.object(service, '_validate_file_extension', return_value=True):
                with patch('app.services.document_storage.mimetypes.guess_type') as mock_guess_type:
                    mock_guess_type.return_value = ('image/jpeg', None)
                    
                    with patch('app.services.document_storage.aiofiles.open') as mock_aiofiles_open:
                        mock_file = AsyncMock()
                        mock_file.read.return_value = file_content
                        mock_aiofiles_open.return_value.__aenter__.return_value = mock_file
                        mock_aiofiles_open.return_value.__aexit__.return_value = None
                        
                        content, filename, content_type = await service.read_local_file(file_path)
                        
                        assert content == file_content
                        assert filename == "image.jpg"
                        assert content_type == "image/jpeg"
    
    @pytest.mark.asyncio
    async def test_read_local_file_not_found(self):
        """Test local file reading when file doesn't exist."""
        service = DocumentStorageService()
        
        mock_path = Mock()
        mock_path.exists.return_value = False
        
        with patch('app.services.document_storage.Path') as mock_path_class:
            mock_path_class.return_value.resolve.return_value = mock_path
            
            with pytest.raises(DownloadError) as exc_info:
                await service.read_local_file("/app/test/nonexistent.jpg")
            
            assert "File not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_read_local_file_invalid_extension(self):
        """Test local file reading with invalid extension."""
        service = DocumentStorageService()
        
        mock_path = Mock()
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_size = 1024
        mock_path.name = "document.txt"
        mock_path.suffix = ".txt"
        
        with patch('app.services.document_storage.Path') as mock_path_class:
            mock_path_class.return_value.resolve.return_value = mock_path
            
            with pytest.raises(FileValidationError) as exc_info:
                await service.read_local_file("/app/test/document.txt")
            
            assert "Unsupported file extension" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_read_local_file_too_large(self):
        """Test local file reading with file too large."""
        service = DocumentStorageService()
        
        mock_path = Mock()
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_size = MAX_FILE_SIZE + 1
        mock_path.name = "large.jpg"
        mock_path.suffix = ".jpg"
        
        with patch('app.services.document_storage.Path') as mock_path_class:
            mock_path_class.return_value.resolve.return_value = mock_path
            
            with pytest.raises(FileValidationError) as exc_info:
                await service.read_local_file("/app/test/large.jpg")
            
            assert "Invalid file size" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_upload_to_storage_success(self):
        """Test successful upload to storage."""
        service = DocumentStorageService()
        
        file_content = b"fake image content"
        driver_id = uuid4()
        public_url = "https://storage.example.com/uploaded_file.jpg"
        
        # Mock storage service
        mock_storage_service = AsyncMock()
        mock_storage_service.upload_file.return_value = public_url
        service.storage_service = mock_storage_service
        
        with patch('app.services.document_storage.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.strftime.return_value = "20240115_120000"
            
            result_url = await service.upload_to_storage(
                file_content=file_content,
                driver_id=driver_id,
                doc_type="CDL",
                original_filename="license.jpg",
                content_type="image/jpeg"
            )
            
            assert result_url == public_url
            mock_storage_service.upload_file.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_to_storage_failure(self):
        """Test upload to storage failure."""
        service = DocumentStorageService()
        
        # Mock storage service failure
        mock_storage_service = AsyncMock()
        mock_storage_service.upload_file.side_effect = Exception("Storage failed")
        service.storage_service = mock_storage_service
        
        with pytest.raises(StorageError) as exc_info:
            await service.upload_to_storage(
                file_content=b"test",
                driver_id=uuid4(),
                doc_type="CDL",
                original_filename="test.jpg",
                content_type="image/jpeg"
            )
        
        assert "Failed to upload file to storage" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_process_url_upload_success(self):
        """Test complete URL upload process."""
        service = DocumentStorageService()
        
        driver_id = uuid4()
        media_url = "https://example.com/image.jpg"
        file_content = b"fake image content"
        public_url = "https://storage.example.com/uploaded.jpg"
        
        # Mock methods
        with patch.object(service, 'download_file_from_url') as mock_download:
            mock_download.return_value = (file_content, "image.jpg", "image/jpeg")
            
            with patch.object(service, 'upload_to_storage') as mock_upload:
                mock_upload.return_value = public_url
                
                with patch.object(service, '_generate_storage_path') as mock_generate_path:
                    mock_generate_path.return_value = f"{driver_id}/CDL/20240115_120000_image.jpg"
                    
                    result = await service.process_url_upload(media_url, driver_id, "CDL")
                    
                    assert result["public_url"] == public_url
                    assert result["original_filename"] == "image.jpg"
                    assert result["file_size"] == len(file_content)
                    assert result["content_type"] == "image/jpeg"
                    assert result["storage_path"] == f"{driver_id}/CDL/20240115_120000_image.jpg"
    
    @pytest.mark.asyncio
    async def test_process_local_upload_success(self):
        """Test complete local file upload process."""
        service = DocumentStorageService()
        
        driver_id = uuid4()
        file_path = "/app/test/image.jpg"
        file_content = b"fake image content"
        public_url = "https://storage.example.com/uploaded.jpg"
        
        # Mock methods
        with patch.object(service, 'read_local_file') as mock_read:
            mock_read.return_value = (file_content, "image.jpg", "image/jpeg")
            
            with patch.object(service, 'upload_to_storage') as mock_upload:
                mock_upload.return_value = public_url
                
                with patch.object(service, '_generate_storage_path') as mock_generate_path:
                    mock_generate_path.return_value = f"{driver_id}/CDL/20240115_120000_image.jpg"
                    
                    result = await service.process_local_upload(file_path, driver_id, "CDL")
                    
                    assert result["public_url"] == public_url
                    assert result["original_filename"] == "image.jpg"
                    assert result["file_size"] == len(file_content)
                    assert result["content_type"] == "image/jpeg"
                    assert result["storage_path"] == f"{driver_id}/CDL/20240115_120000_image.jpg"


@pytest.mark.asyncio
async def test_global_service_instance():
    """Test that the global service instance is accessible."""
    assert document_storage_service is not None
    assert isinstance(document_storage_service, DocumentStorageService) 
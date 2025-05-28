"""Tests for Datalab OCR client."""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
import aiohttp
from pathlib import Path

from app.services.ocr_clients.datalab_client import (
    DatalabOCRClient,
    DatalabOCRError,
    DatalabAuthenticationError,
    DatalabRateLimitError,
    DatalabProcessingError,
    DatalabTimeoutError,
    datalab_ocr_client
)


class TestDatalabOCRClient:
    """Test cases for DatalabOCRClient."""
    
    def test_initialization_with_api_key(self):
        """Test client initialization with provided API key."""
        client = DatalabOCRClient(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.session is None
    
    def test_initialization_without_api_key_raises_error(self):
        """Test client initialization without API key raises error."""
        with patch('app.services.ocr_clients.datalab_client.settings') as mock_settings:
            mock_settings.DATALAB_API_KEY = None
            
            with pytest.raises(DatalabAuthenticationError) as exc_info:
                DatalabOCRClient()
            
            assert "DATALAB_API_KEY is required" in str(exc_info.value)
    
    def test_client_constants(self):
        """Test client configuration constants."""
        client = DatalabOCRClient(api_key="test-key")
        
        assert client.BASE_URL == "https://www.datalab.to/api/v1"
        assert client.OCR_ENDPOINT == "https://www.datalab.to/api/v1/ocr"
        assert client.MAX_REQUESTS_PER_MINUTE == 200
        assert client.MAX_CONCURRENT_REQUESTS == 200
        assert client.MAX_FILE_SIZE == 200 * 1024 * 1024  # 200MB
        assert client.DEFAULT_POLL_INTERVAL == 2
        assert client.DEFAULT_MAX_POLLS == 300
        assert client.DEFAULT_TIMEOUT == 30
    
    def test_supported_mime_types(self):
        """Test supported MIME types."""
        client = DatalabOCRClient(api_key="test-key")
        
        expected_types = {
            'application/pdf',
            'image/png',
            'image/jpeg',
            'image/webp',
            'image/gif',
            'image/tiff',
            'image/jpg'
        }
        
        assert client.SUPPORTED_MIME_TYPES == expected_types
    
    def test_validate_file_size_valid(self):
        """Test file size validation with valid sizes."""
        client = DatalabOCRClient(api_key="test-key")
        
        # Should not raise for valid sizes
        client._validate_file_size(1024)  # 1KB
        client._validate_file_size(client.MAX_FILE_SIZE)  # Max size
        client._validate_file_size(client.MAX_FILE_SIZE - 1)  # Just under max
    
    def test_validate_file_size_invalid(self):
        """Test file size validation with invalid sizes."""
        client = DatalabOCRClient(api_key="test-key")
        
        # Zero size
        with pytest.raises(DatalabOCRError) as exc_info:
            client._validate_file_size(0)
        assert "File size must be greater than 0" in str(exc_info.value)
        
        # Too large
        with pytest.raises(DatalabOCRError) as exc_info:
            client._validate_file_size(client.MAX_FILE_SIZE + 1)
        assert "exceeds maximum" in str(exc_info.value)
        
        # Negative size
        with pytest.raises(DatalabOCRError) as exc_info:
            client._validate_file_size(-100)
        assert "File size must be greater than 0" in str(exc_info.value)
    
    def test_validate_mime_type_valid(self):
        """Test MIME type validation with valid types."""
        client = DatalabOCRClient(api_key="test-key")
        
        # Should not raise for valid MIME types
        client._validate_mime_type("image/jpeg")
        client._validate_mime_type("application/pdf")
        client._validate_mime_type("image/png")
        client._validate_mime_type("IMAGE/JPEG")  # Case insensitive
    
    def test_validate_mime_type_invalid(self):
        """Test MIME type validation with invalid types."""
        client = DatalabOCRClient(api_key="test-key")
        
        with pytest.raises(DatalabOCRError) as exc_info:
            client._validate_mime_type("text/plain")
        assert "Unsupported MIME type" in str(exc_info.value)
        
        with pytest.raises(DatalabOCRError) as exc_info:
            client._validate_mime_type("application/zip")
        assert "Unsupported MIME type" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_ensure_session_creates_session(self):
        """Test that session is created with proper configuration."""
        client = DatalabOCRClient(api_key="test-api-key")
        
        await client._ensure_session()
        
        assert client.session is not None
        assert isinstance(client.session, aiohttp.ClientSession)
        assert client.session.headers['X-Api-Key'] == "test-api-key"
        assert client.session.headers['User-Agent'] == "OCR-Load-Service/1.0"
        
        # Clean up
        await client.close()
    
    @pytest.mark.asyncio
    async def test_close_session(self):
        """Test session cleanup."""
        client = DatalabOCRClient(api_key="test-key")
        
        await client._ensure_session()
        session = client.session
        assert not session.closed
        
        await client.close()
        assert session.closed
        assert client.session is None
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager usage."""
        async with DatalabOCRClient(api_key="test-key") as client:
            assert client.session is not None
            session = client.session
        
        # Session should be closed after context exit
        assert session.closed
    
    @pytest.mark.asyncio
    async def test_submit_ocr_request_success(self):
        """Test successful OCR request submission."""
        client = DatalabOCRClient(api_key="test-key")
        
        # Mock response
        mock_response_data = {
            "success": True,
            "request_id": "test-request-id",
            "request_check_url": "https://www.datalab.to/api/v1/ocr/test-request-id"
        }
        
        # Mock the entire _ensure_session and session.post context
        with patch.object(client, '_ensure_session', new_callable=AsyncMock):
            with patch('aiohttp.ClientSession.post') as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_response_data)
                
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # Create a fake session
                client.session = AsyncMock()
                client.session.post = mock_post
                
                result = await client._submit_ocr_request(
                    file_content=b"fake image content",
                    filename="test.jpg",
                    mime_type="image/jpeg"
                )
        
        assert result == mock_response_data
    
    @pytest.mark.asyncio
    async def test_submit_ocr_request_authentication_error(self):
        """Test OCR request with authentication error."""
        client = DatalabOCRClient(api_key="test-key")
        
        # Mock the entire _ensure_session and session.post context
        with patch.object(client, '_ensure_session', new_callable=AsyncMock):
            with patch('aiohttp.ClientSession.post') as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 401
                mock_response.json = AsyncMock(return_value={"error": "Invalid API key"})
                
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # Create a fake session
                client.session = AsyncMock()
                client.session.post = mock_post
                
                with pytest.raises(DatalabAuthenticationError) as exc_info:
                    await client._submit_ocr_request(
                        file_content=b"fake content",
                        filename="test.jpg",
                        mime_type="image/jpeg"
                    )
        
        assert "Invalid API key" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_submit_ocr_request_rate_limit_error(self):
        """Test OCR request with rate limit error."""
        client = DatalabOCRClient(api_key="test-key")
        
        # Mock the entire _ensure_session and session.post context
        with patch.object(client, '_ensure_session', new_callable=AsyncMock):
            with patch('aiohttp.ClientSession.post') as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 429
                mock_response.json = AsyncMock(return_value={"error": "Rate limit exceeded"})
                
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # Create a fake session
                client.session = AsyncMock()
                client.session.post = mock_post
                
                with pytest.raises(DatalabRateLimitError):
                    await client._submit_ocr_request(
                        file_content=b"fake content",
                        filename="test.jpg",
                        mime_type="image/jpeg"
                    )
    
    @pytest.mark.asyncio
    async def test_submit_ocr_request_with_languages(self):
        """Test OCR request submission with language hints."""
        client = DatalabOCRClient(api_key="test-key")
        
        mock_response_data = {"success": True, "request_id": "test-id", "request_check_url": "https://test.com/check"}
        
        # Mock the entire _ensure_session and session.post context
        with patch.object(client, '_ensure_session', new_callable=AsyncMock):
            with patch('aiohttp.ClientSession.post') as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_response_data)
                
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # Create a fake session
                client.session = AsyncMock()
                client.session.post = mock_post
                
                result = await client._submit_ocr_request(
                    file_content=b"fake content",
                    filename="test.jpg",
                    mime_type="image/jpeg",
                    languages=["English", "Spanish"],
                    max_pages=5
                )
        
        assert result == mock_response_data
    
    @pytest.mark.asyncio
    async def test_submit_ocr_request_too_many_languages(self):
        """Test OCR request with too many languages."""
        client = DatalabOCRClient(api_key="test-key")
        
        with pytest.raises(DatalabOCRError) as exc_info:
            await client._submit_ocr_request(
                file_content=b"fake content",
                filename="test.jpg",
                mime_type="image/jpeg",
                languages=["English", "Spanish", "French", "German", "Italian"]  # 5 languages
            )
        
        assert "Maximum 4 languages allowed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_poll_for_results_success(self):
        """Test successful polling for results."""
        client = DatalabOCRClient(api_key="test-key")
        
        # Mock response - complete on first poll
        mock_response_data = {
            "status": "complete",
            "success": True,
            "pages": [{"text_lines": [{"text": "Test text", "confidence": 0.95}]}],
            "page_count": 1
        }
        
        # Mock the entire _ensure_session and session.get context
        with patch.object(client, '_ensure_session', new_callable=AsyncMock):
            with patch('aiohttp.ClientSession.get') as mock_get:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=mock_response_data)
                
                mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_get.return_value.__aexit__ = AsyncMock(return_value=None)
                
                # Create a fake session
                client.session = AsyncMock()
                client.session.get = mock_get
                
                result = await client._poll_for_results(
                    check_url="https://test.com/check",
                    max_polls=10,
                    poll_interval=0.1  # Fast polling for tests
                )
        
        assert result == mock_response_data
    
    @pytest.mark.asyncio
    async def test_poll_for_results_processing_then_complete(self):
        """Test polling that starts with processing then completes."""
        client = DatalabOCRClient(api_key="test-key")
        
        # Mock responses - processing first, then complete
        processing_response = {
            "status": "processing",
            "success": True
        }
        
        complete_response = {
            "status": "complete",
            "success": True,
            "pages": [{"text_lines": [{"text": "Test text", "confidence": 0.95}]}],
            "page_count": 1
        }
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.side_effect = [processing_response, complete_response]
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        mock_session.get.return_value.__aexit__.return_value = None
        
        client.session = mock_session
        
        with patch('asyncio.sleep', new_callable=AsyncMock):  # Mock sleep for fast tests
            result = await client._poll_for_results(
                check_url="https://test.com/check",
                max_polls=10,
                poll_interval=0.01
            )
        
        assert result == complete_response
        assert mock_session.get.call_count == 2
    
    @pytest.mark.asyncio
    async def test_poll_for_results_timeout(self):
        """Test polling timeout."""
        client = DatalabOCRClient(api_key="test-key")
        
        # Always return processing status
        mock_response_data = {"status": "processing", "success": True}
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_response_data
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        mock_session.get.return_value.__aexit__.return_value = None
        
        client.session = mock_session
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            with pytest.raises(DatalabTimeoutError) as exc_info:
                await client._poll_for_results(
                    check_url="https://test.com/check",
                    max_polls=3,  # Small number for fast test
                    poll_interval=0.01
                )
        
        assert "timed out after 3 polling attempts" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_poll_for_results_processing_error(self):
        """Test polling with processing error."""
        client = DatalabOCRClient(api_key="test-key")
        
        mock_response_data = {
            "status": "complete",
            "success": False,
            "error": "OCR processing failed"
        }
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = mock_response_data
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        mock_session.get.return_value.__aexit__.return_value = None
        
        client.session = mock_session
        
        with pytest.raises(DatalabProcessingError) as exc_info:
            await client._poll_for_results("https://test.com/check")
        
        assert "OCR processing failed" in str(exc_info.value)
    
    def test_parse_ocr_results_success(self):
        """Test parsing successful OCR results."""
        client = DatalabOCRClient(api_key="test-key")
        
        response_data = {
            "status": "complete",
            "success": True,
            "page_count": 2,
            "pages": [
                {
                    "page": 1,
                    "text_lines": [
                        {
                            "text": "First line",
                            "confidence": 0.95,
                            "bbox": [10, 20, 100, 40],
                            "polygon": [[10, 20], [100, 20], [100, 40], [10, 40]]
                        },
                        {
                            "text": "Second line",
                            "confidence": 0.90,
                            "bbox": [10, 50, 120, 70]
                        }
                    ],
                    "languages": ["en"],
                    "image_bbox": [0, 0, 800, 600]
                },
                {
                    "page": 2,
                    "text_lines": [
                        {
                            "text": "Third line",
                            "confidence": 0.98,
                            "bbox": [15, 25, 110, 45]
                        }
                    ],
                    "languages": ["en"],
                    "image_bbox": [0, 0, 800, 600]
                }
            ]
        }
        
        result = client._parse_ocr_results(response_data)
        
        assert result['success'] is True
        assert result['page_count'] == 2
        assert result['full_text'] == "First line\nSecond line\n\nThird line"
        assert result['average_confidence'] == (0.95 + 0.90 + 0.98) / 3
        assert result['metadata']['provider'] == 'datalab'
        assert result['metadata']['total_text_lines'] == 3
        
        # Check page parsing
        assert len(result['pages']) == 2
        page1 = result['pages'][0]
        assert page1['page_number'] == 1
        assert page1['text'] == "First line\nSecond line"
        assert page1['average_confidence'] == (0.95 + 0.90) / 2
        assert len(page1['text_lines']) == 2
    
    def test_parse_ocr_results_empty(self):
        """Test parsing empty OCR results."""
        client = DatalabOCRClient(api_key="test-key")
        
        response_data = {
            "status": "complete",
            "success": True,
            "page_count": 0,
            "pages": []
        }
        
        result = client._parse_ocr_results(response_data)
        
        assert result['success'] is True
        assert result['page_count'] == 0
        assert result['full_text'] == ""
        assert result['average_confidence'] == 0.0
        assert result['metadata']['total_text_lines'] == 0
        assert len(result['pages']) == 0
    
    @pytest.mark.asyncio
    async def test_process_file_content_success(self):
        """Test successful file content processing."""
        client = DatalabOCRClient(api_key="test-key")
        
        # Mock the internal methods
        submit_response = {
            "success": True,
            "request_id": "test-id",
            "request_check_url": "https://test.com/check"
        }
        
        poll_response = {
            "status": "complete",
            "success": True,
            "page_count": 1,
            "pages": [{
                "page": 1,
                "text_lines": [{"text": "Test text", "confidence": 0.95}],
                "languages": ["en"],
                "image_bbox": [0, 0, 800, 600]
            }]
        }
        
        with patch.object(client, '_submit_ocr_request', return_value=submit_response) as mock_submit:
            with patch.object(client, '_poll_for_results', return_value=poll_response) as mock_poll:
                result = await client.process_file_content(
                    file_content=b"fake image content",
                    filename="test.jpg",
                    mime_type="image/jpeg",
                    languages=["English"]
                )
        
        assert result['success'] is True
        assert result['full_text'] == "Test text"
        assert 'processing_time' in result['metadata']
        
        mock_submit.assert_called_once_with(
            b"fake image content", "test.jpg", "image/jpeg", ["English"], None
        )
        mock_poll.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_file_content_no_check_url(self):
        """Test file content processing with missing check URL."""
        client = DatalabOCRClient(api_key="test-key")
        
        submit_response = {
            "success": True,
            "request_id": "test-id"
            # Missing request_check_url
        }
        
        with patch.object(client, '_submit_ocr_request', return_value=submit_response):
            with pytest.raises(DatalabProcessingError) as exc_info:
                await client.process_file_content(
                    file_content=b"fake content",
                    filename="test.jpg",
                    mime_type="image/jpeg"
                )
        
        assert "No check URL received" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_process_file_path_success(self):
        """Test successful file path processing."""
        client = DatalabOCRClient(api_key="test-key")
        
        # Mock file content
        file_content = b"fake image content"
        
        # Mock the process_file_content method
        expected_result = {
            "success": True,
            "full_text": "Test text from file",
            "page_count": 1
        }
        
        with patch('aiofiles.open') as mock_aio_open:
            mock_file = AsyncMock()
            mock_file.read.return_value = file_content
            mock_aio_open.return_value.__aenter__.return_value = mock_file
            mock_aio_open.return_value.__aexit__.return_value = None
            
            with patch.object(Path, 'exists', return_value=True):
                with patch('mimetypes.guess_type', return_value=('image/jpeg', None)):
                    with patch.object(client, 'process_file_content', return_value=expected_result) as mock_process:
                        result = await client.process_file_path(
                            file_path="test.jpg",
                            languages=["English"]
                        )
        
        assert result == expected_result
        mock_process.assert_called_once_with(
            file_content, "test.jpg", "image/jpeg", ["English"], None
        )
    
    @pytest.mark.asyncio
    async def test_process_file_path_not_found(self):
        """Test file path processing with missing file."""
        client = DatalabOCRClient(api_key="test-key")
        
        with patch.object(Path, 'exists', return_value=False):
            with pytest.raises(DatalabOCRError) as exc_info:
                await client.process_file_path("nonexistent.jpg")
        
        assert "File not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_process_file_path_mime_type_fallback(self):
        """Test file path processing with MIME type fallback."""
        client = DatalabOCRClient(api_key="test-key")
        
        file_content = b"fake pdf content"
        expected_result = {"success": True}
        
        with patch('aiofiles.open') as mock_aio_open:
            mock_file = AsyncMock()
            mock_file.read.return_value = file_content
            mock_aio_open.return_value.__aenter__.return_value = mock_file
            mock_aio_open.return_value.__aexit__.return_value = None
            
            with patch.object(Path, 'exists', return_value=True):
                with patch('mimetypes.guess_type', return_value=(None, None)):  # No MIME type detected
                    with patch.object(client, 'process_file_content', return_value=expected_result) as mock_process:
                        result = await client.process_file_path("document.pdf")
        
        # Should use fallback MIME type for .pdf
        mock_process.assert_called_once_with(
            file_content, "document.pdf", "application/pdf", None, None
        )


def test_global_client_instance():
    """Test that the global client instance is accessible."""
    # Note: This test might fail if DATALAB_API_KEY is not set in environment
    # In a real test environment, we'd mock the settings
    with patch('app.services.ocr_clients.datalab_client.settings') as mock_settings:
        mock_settings.DATALAB_API_KEY = "test-key"
        
        # Import should work without error
        from app.services.ocr_clients.datalab_client import datalab_ocr_client
        assert datalab_ocr_client is not None
        assert isinstance(datalab_ocr_client, DatalabOCRClient) 
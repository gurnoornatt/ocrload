"""Real integration tests for the media endpoint."""

import asyncio
import pytest
import httpx
from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app
from app.models.database import DocumentType


class TestMediaEndpointReal:
    """Real integration tests for the media endpoint."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    def test_post_media_endpoint_valid_request(self, client):
        """Test POST /api/media with valid request."""
        # Use a real public image URL for testing
        test_url = "https://httpbin.org/image/png"
        
        request_data = {
            "driver_id": str(uuid4()),
            "doc_type": "CDL",
            "media_url": test_url
        }
        
        response = client.post("/api/media/", json=request_data)
        
        # Should return 202 Accepted
        assert response.status_code == 202
        
        data = response.json()
        assert data["success"] is True
        assert "document_id" in data
        assert "processing_url" in data
        assert "message" in data
        
        # Verify the processing URL format
        assert data["processing_url"].startswith("/api/media/")
        assert data["processing_url"].endswith("/status")
    
    def test_post_media_endpoint_with_load_id(self, client):
        """Test POST /api/media with optional load_id."""
        test_url = "https://httpbin.org/image/jpeg"
        
        request_data = {
            "driver_id": str(uuid4()),
            "load_id": str(uuid4()),
            "doc_type": "POD",
            "media_url": test_url
        }
        
        response = client.post("/api/media/", json=request_data)
        
        assert response.status_code == 202
        data = response.json()
        assert data["success"] is True
    
    def test_post_media_endpoint_invalid_uuid(self, client):
        """Test POST /api/media with invalid UUID."""
        request_data = {
            "driver_id": "invalid-uuid",
            "doc_type": "CDL",
            "media_url": "https://httpbin.org/image/png"
        }
        
        response = client.post("/api/media/", json=request_data)
        
        # Should return 422 Validation Error
        assert response.status_code == 422
    
    def test_post_media_endpoint_invalid_doc_type(self, client):
        """Test POST /api/media with invalid document type."""
        request_data = {
            "driver_id": str(uuid4()),
            "doc_type": "INVALID_TYPE",
            "media_url": "https://httpbin.org/image/png"
        }
        
        response = client.post("/api/media/", json=request_data)
        
        # Should return 422 Validation Error
        assert response.status_code == 422
    
    def test_post_media_endpoint_invalid_url(self, client):
        """Test POST /api/media with invalid URL."""
        request_data = {
            "driver_id": str(uuid4()),
            "doc_type": "CDL",
            "media_url": "not-a-valid-url"
        }
        
        response = client.post("/api/media/", json=request_data)
        
        # Should return 422 Validation Error
        assert response.status_code == 422
    
    def test_post_media_endpoint_nonexistent_url(self, client):
        """Test POST /api/media with URL that doesn't exist."""
        request_data = {
            "driver_id": str(uuid4()),
            "doc_type": "CDL",
            "media_url": "https://httpbin.org/status/404"
        }
        
        response = client.post("/api/media/", json=request_data)
        
        # Should return 400 Bad Request due to download failure
        assert response.status_code == 400
        assert "Failed to download file" in response.json()["error"]
    
    def test_get_status_endpoint(self, client):
        """Test GET /api/media/{document_id}/status endpoint."""
        document_id = uuid4()
        
        response = client.get(f"/api/media/{document_id}/status")
        
        assert response.status_code == 200
        
        data = response.json()
        assert "document_id" in data
        assert "status" in data
        assert "progress" in data
        assert str(document_id) == data["document_id"]
    
    def test_get_status_endpoint_invalid_uuid(self, client):
        """Test GET /api/media/{document_id}/status with invalid UUID."""
        response = client.get("/api/media/invalid-uuid/status")
        
        # Should return 422 Validation Error
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_download_file_function_real_url(self):
        """Test the download_file_from_url function with real URL."""
        from app.routers.media import download_file_from_url
        
        # Test with a small image from httpbin
        url = "https://httpbin.org/image/png"
        
        content, content_type = await download_file_from_url(url)
        
        assert len(content) > 0
        assert "image" in content_type.lower() or "png" in content_type.lower()
    
    @pytest.mark.asyncio
    async def test_download_file_function_timeout(self):
        """Test the download_file_from_url function with timeout URL."""
        from app.routers.media import download_file_from_url
        from fastapi import HTTPException
        
        # Test with httpbin delay endpoint that takes longer than our timeout
        url = "https://httpbin.org/delay/35"  # 35 seconds delay, our timeout is 30
        
        with pytest.raises(HTTPException) as exc_info:
            await download_file_from_url(url)
        
        assert exc_info.value.status_code == 408
        assert "timeout" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio 
    async def test_download_file_function_large_file(self):
        """Test the download_file_from_url function with file too large."""
        from app.routers.media import download_file_from_url
        from fastapi import HTTPException
        
        # Test with a small max_size to trigger the size limit
        url = "https://httpbin.org/image/png"
        
        with pytest.raises(HTTPException) as exc_info:
            await download_file_from_url(url, max_size=100)  # Very small limit
        
        assert exc_info.value.status_code == 413
        assert "too large" in exc_info.value.detail.lower()


if __name__ == "__main__":
    # Run specific tests
    pytest.main([__file__ + "::TestMediaEndpointReal::test_post_media_endpoint_valid_request", "-v"]) 
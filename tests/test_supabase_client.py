"""Tests for Supabase client service."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from uuid import uuid4

from app.services.supabase_client import SupabaseService, supabase_service


class TestSupabaseService:
    """Test cases for SupabaseService."""
    
    def test_service_initialization(self):
        """Test that the service initializes correctly."""
        service = SupabaseService()
        assert service._client is None
        assert not service._initialized
        assert service.storage_bucket == "raw_docs"  # From settings
    
    @patch('app.services.supabase_client.create_client')
    def test_client_property_initialization(self, mock_create_client):
        """Test that client property initializes the Supabase client."""
        mock_client = Mock()
        mock_create_client.return_value = mock_client
        
        service = SupabaseService()
        client = service.client
        
        assert client == mock_client
        assert service._initialized
        mock_create_client.assert_called_once()
    
    @patch('app.services.supabase_client.create_client')
    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_create_client):
        """Test successful health check."""
        # Mock successful database query
        mock_result = Mock()
        mock_result.data = [{"id": "test-id"}]
        
        mock_table = Mock()
        mock_table.select.return_value.limit.return_value.execute.return_value = mock_result
        
        # Mock successful storage operations
        mock_bucket = Mock()
        mock_bucket.name = "raw_docs"
        
        mock_storage = Mock()
        mock_storage.list_buckets.return_value = [mock_bucket]
        mock_storage.from_.return_value.list.return_value = []
        
        mock_client = Mock()
        mock_client.table.return_value = mock_table
        mock_client.storage = mock_storage
        mock_create_client.return_value = mock_client
        
        service = SupabaseService()
        health_status = await service.health_check()
        
        assert health_status["database"]["status"] == "healthy"
        assert health_status["storage"]["status"] == "healthy"
        assert "Database connection successful" in health_status["database"]["message"]
        assert "Storage bucket accessible" in health_status["storage"]["message"]
    
    @patch('app.services.supabase_client.create_client')
    @pytest.mark.asyncio
    async def test_health_check_database_failure(self, mock_create_client):
        """Test health check with database failure."""
        # Mock database query failure
        mock_table = Mock()
        mock_table.select.return_value.limit.return_value.execute.side_effect = Exception("DB connection failed")
        
        mock_client = Mock()
        mock_client.table.return_value = mock_table
        mock_create_client.return_value = mock_client
        
        service = SupabaseService()
        health_status = await service.health_check()
        
        assert health_status["database"]["status"] == "unhealthy"
        assert "DB connection failed" in health_status["database"]["message"]
    
    @patch('app.services.supabase_client.create_client')
    @pytest.mark.asyncio
    async def test_get_driver_by_id(self, mock_create_client):
        """Test getting driver by ID."""
        driver_id = str(uuid4())
        mock_driver_data = {"id": driver_id, "phone_number": "+1234567890"}
        
        mock_result = Mock()
        mock_result.data = [mock_driver_data]
        
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_result
        
        mock_client = Mock()
        mock_client.table.return_value = mock_table
        mock_create_client.return_value = mock_client
        
        service = SupabaseService()
        result = await service.get_driver_by_id(driver_id)
        
        assert result == mock_driver_data
        mock_client.table.assert_called_with("drivers")
    
    @patch('app.services.supabase_client.create_client')
    @pytest.mark.asyncio
    async def test_get_driver_by_id_not_found(self, mock_create_client):
        """Test getting driver by ID when not found."""
        driver_id = str(uuid4())
        
        mock_result = Mock()
        mock_result.data = []
        
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_result
        
        mock_client = Mock()
        mock_client.table.return_value = mock_table
        mock_create_client.return_value = mock_client
        
        service = SupabaseService()
        result = await service.get_driver_by_id(driver_id)
        
        assert result is None
    
    @patch('app.services.supabase_client.create_client')
    @pytest.mark.asyncio
    async def test_create_document(self, mock_create_client):
        """Test creating a document."""
        document_data = {
            "driver_id": str(uuid4()),
            "type": "CDL",
            "url": "https://example.com/cdl.jpg",
            "confidence": 0.95
        }
        
        mock_created_doc = {**document_data, "id": str(uuid4())}
        mock_result = Mock()
        mock_result.data = [mock_created_doc]
        
        mock_table = Mock()
        mock_table.insert.return_value.execute.return_value = mock_result
        
        mock_client = Mock()
        mock_client.table.return_value = mock_table
        mock_create_client.return_value = mock_client
        
        service = SupabaseService()
        result = await service.create_document(document_data)
        
        assert result == mock_created_doc
        mock_table.insert.assert_called_with(document_data)
    
    @patch('app.services.supabase_client.create_client')
    @pytest.mark.asyncio
    async def test_update_driver_flags(self, mock_create_client):
        """Test updating driver flags."""
        driver_id = str(uuid4())
        current_driver = {
            "id": driver_id,
            "doc_flags": {"cdl_verified": False}
        }
        new_flags = {"cdl_verified": True, "insurance_verified": True}
        
        # Mock get driver
        mock_get_result = Mock()
        mock_get_result.data = [current_driver]
        
        # Mock update
        mock_update_result = Mock()
        mock_update_result.data = [{"updated": True}]
        
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_get_result
        mock_table.update.return_value.eq.return_value.execute.return_value = mock_update_result
        
        mock_client = Mock()
        mock_client.table.return_value = mock_table
        mock_create_client.return_value = mock_client
        
        service = SupabaseService()
        result = await service.update_driver_flags(driver_id, new_flags)
        
        assert result is True
        # Verify update was called with merged flags
        expected_flags = {"cdl_verified": True, "insurance_verified": True}
        mock_table.update.assert_called_with({
            "doc_flags": expected_flags,
            "updated_at": "now()"
        })
    
    @patch('app.services.supabase_client.create_client')
    @pytest.mark.asyncio
    async def test_upload_file(self, mock_create_client):
        """Test file upload to storage."""
        file_path = "test/document.jpg"
        file_content = b"fake image content"
        content_type = "image/jpeg"
        public_url = "https://storage.supabase.co/test/document.jpg"
        
        mock_storage_bucket = Mock()
        mock_storage_bucket.upload.return_value = True
        mock_storage_bucket.get_public_url.return_value = public_url
        
        mock_storage = Mock()
        mock_storage.from_.return_value = mock_storage_bucket
        
        mock_client = Mock()
        mock_client.storage = mock_storage
        mock_create_client.return_value = mock_client
        
        service = SupabaseService()
        result = await service.upload_file(file_path, file_content, content_type)
        
        assert result == public_url
        mock_storage_bucket.upload.assert_called_with(
            path=file_path,
            file=file_content,
            file_options={
                "content-type": content_type,
                "upsert": False
            }
        )
    
    @patch('app.services.supabase_client.create_client')
    @pytest.mark.asyncio
    async def test_check_load_ratecon_verified(self, mock_create_client):
        """Test checking if load has verified rate confirmation."""
        load_id = str(uuid4())
        
        # Mock result with rate confirmation document
        mock_result = Mock()
        mock_result.data = [{"confidence": 0.95}]
        
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = mock_result
        
        mock_client = Mock()
        mock_client.table.return_value = mock_table
        mock_create_client.return_value = mock_client
        
        service = SupabaseService()
        result = await service.check_load_ratecon_verified(load_id)
        
        assert result is True
        mock_client.table.assert_called_with("documents")


@pytest.mark.asyncio
async def test_global_service_instance():
    """Test that the global service instance is accessible."""
    assert supabase_service is not None
    assert isinstance(supabase_service, SupabaseService) 
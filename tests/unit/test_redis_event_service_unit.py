"""
Unit tests for Redis Event Service

Tests the Redis event service functionality with mocked Redis client.
Focuses on testing business logic, error handling, and graceful degradation.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, PropertyMock
from uuid import uuid4

from redis.exceptions import ConnectionError, TimeoutError, RedisError

from app.services.redis_event_service import RedisEventService


class TestRedisEventService:
    """Test suite for Redis Event Service unit tests."""
    
    @pytest.fixture
    def service(self):
        """Create a fresh Redis event service instance for each test."""
        return RedisEventService()
    
    @pytest.fixture
    def mock_redis_client(self):
        """Create a mock Redis client."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.publish.return_value = 1  # 1 subscriber
        return mock_client
    
    def test_init(self, service):
        """Test service initialization."""
        assert service._client is None
        assert service._connection_failed is False
        assert service._last_connection_attempt is None
        assert service.INVOICE_READY_CHANNEL == "invoice_ready"
        assert service.RETRY_INTERVAL_SECONDS == 300
    
    @patch('app.services.redis_event_service.settings')
    def test_client_property_no_redis_url(self, mock_settings, service):
        """Test client property when Redis URL is not configured."""
        mock_settings.redis_url = None
        
        client = service.client
        
        assert client is None
        assert service._connection_failed is True
    
    @patch('app.services.redis_event_service.settings')
    @patch('app.services.redis_event_service.redis.from_url')
    def test_client_property_successful_connection(self, mock_from_url, mock_settings, service, mock_redis_client):
        """Test client property with successful Redis connection."""
        mock_settings.redis_url = "redis://localhost:6379"
        mock_from_url.return_value = mock_redis_client
        
        client = service.client
        
        assert client == mock_redis_client
        assert service._connection_failed is False
        mock_from_url.assert_called_once_with(
            "redis://localhost:6379",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
        mock_redis_client.ping.assert_called_once()
    
    @patch('app.services.redis_event_service.settings')
    @patch('app.services.redis_event_service.redis.from_url')
    def test_client_property_connection_failure(self, mock_from_url, mock_settings, service):
        """Test client property with Redis connection failure."""
        mock_settings.redis_url = "redis://localhost:6379"
        mock_from_url.side_effect = ConnectionError("Connection failed")
        
        client = service.client
        
        assert client is None
        assert service._connection_failed is True
        assert service._last_connection_attempt is not None
    
    @pytest.mark.asyncio
    @patch('app.services.redis_event_service.settings')
    async def test_emit_invoice_ready_event_success(self, mock_settings, service, mock_redis_client):
        """Test successful invoice ready event emission."""
        # Mock settings to have Redis URL configured
        mock_settings.redis_url = "redis://localhost:6379"
        
        # Directly set the client to bypass the property
        service._client = mock_redis_client
        service._connection_failed = False
        
        load_id = uuid4()
        driver_id = uuid4()
        
        result = await service.emit_invoice_ready_event(load_id, driver_id)
        
        assert result is True
        mock_redis_client.publish.assert_called_once()
        
        # Verify the published message
        call_args = mock_redis_client.publish.call_args
        channel, message = call_args[0]
        
        assert channel == "invoice_ready"
        
        # Parse and verify message content
        message_data = json.loads(message)
        assert message_data["event"] == "invoice_ready"
        assert message_data["load_id"] == str(load_id)
        assert message_data["driver_id"] == str(driver_id)
        assert "timestamp" in message_data
        
        # Verify timestamp format
        timestamp = datetime.fromisoformat(message_data["timestamp"].replace('Z', '+00:00'))
        assert timestamp.tzinfo is not None
    
    @pytest.mark.asyncio
    @patch('app.services.redis_event_service.settings')
    async def test_emit_invoice_ready_event_with_additional_data(self, mock_settings, service, mock_redis_client):
        """Test invoice ready event emission with additional data."""
        mock_settings.redis_url = "redis://localhost:6379"
        
        service._client = mock_redis_client
        service._connection_failed = False
        
        load_id = uuid4()
        driver_id = uuid4()
        additional_data = {
            "origin": "Chicago, IL",
            "destination": "Dallas, TX",
            "rate": 1500.00
        }
        
        result = await service.emit_invoice_ready_event(load_id, driver_id, additional_data)
        
        assert result is True
        
        # Verify additional data is included
        call_args = mock_redis_client.publish.call_args
        channel, message = call_args[0]
        message_data = json.loads(message)
        
        assert message_data["origin"] == "Chicago, IL"
        assert message_data["destination"] == "Dallas, TX"
        assert message_data["rate"] == 1500.00
    
    @pytest.mark.asyncio
    async def test_emit_invoice_ready_event_no_client(self, service):
        """Test invoice ready event emission when Redis client is unavailable."""
        service._client = None
        service._connection_failed = True
        
        load_id = uuid4()
        driver_id = uuid4()
        
        result = await service.emit_invoice_ready_event(load_id, driver_id)
        
        assert result is False
    
    @pytest.mark.asyncio
    @patch('app.services.redis_event_service.settings')
    async def test_emit_invoice_ready_event_redis_error(self, mock_settings, service, mock_redis_client):
        """Test invoice ready event emission with Redis error."""
        mock_settings.redis_url = "redis://localhost:6379"
        
        service._client = mock_redis_client
        service._connection_failed = False
        mock_redis_client.publish.side_effect = ConnectionError("Redis connection lost")
        
        load_id = uuid4()
        driver_id = uuid4()
        
        result = await service.emit_invoice_ready_event(load_id, driver_id)
        
        assert result is False
        assert service._connection_failed is True
        assert service._last_connection_attempt is not None
    
    @pytest.mark.asyncio
    @patch('app.services.redis_event_service.settings')
    async def test_emit_custom_event_success(self, mock_settings, service, mock_redis_client):
        """Test successful custom event emission."""
        mock_settings.redis_url = "redis://localhost:6379"
        
        service._client = mock_redis_client
        service._connection_failed = False
        
        result = await service.emit_custom_event(
            channel="test_channel",
            event_type="test_event",
            payload={"test_key": "test_value"}
        )
        
        assert result is True
        mock_redis_client.publish.assert_called_once()
        
        # Verify the published message
        call_args = mock_redis_client.publish.call_args
        channel, message = call_args[0]
        
        assert channel == "test_channel"
        
        message_data = json.loads(message)
        assert message_data["event"] == "test_event"
        assert message_data["test_key"] == "test_value"
        assert "timestamp" in message_data
    
    @pytest.mark.asyncio
    async def test_health_check_redis_not_configured(self, service):
        """Test health check when Redis is not configured."""
        with patch('app.services.redis_event_service.settings') as mock_settings:
            mock_settings.redis_url = None
            
            health = await service.health_check()
            
            assert health["status"] == "disabled"
            assert health["message"] == "Redis URL not configured"
            assert health["configured"] is False
            assert health["connected"] is False
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, service, mock_redis_client):
        """Test successful health check."""
        service._client = mock_redis_client
        
        with patch('app.services.redis_event_service.settings') as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379"
            
            health = await service.health_check()
            
            assert health["status"] == "healthy"
            assert "successful" in health["message"]
            assert health["configured"] is True
            assert health["connected"] is True
            
            mock_redis_client.ping.assert_called()
            mock_redis_client.publish.assert_called()
    
    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, service):
        """Test health check with Redis connection error."""
        with patch('app.services.redis_event_service.settings') as mock_settings:
            mock_settings.redis_url = "redis://localhost:6379"
            
            # Mock client property to return None (connection failed)
            service._client = None
            service._connection_failed = True
            
            health = await service.health_check()
            
            assert health["status"] == "unhealthy"
            assert "Failed to initialize" in health["message"]
            assert health["configured"] is True
            assert health["connected"] is False
    
    def test_should_retry_connection_no_previous_failure(self, service):
        """Test retry logic when there was no previous failure."""
        result = service._should_retry_connection()
        assert result is True
    
    def test_should_retry_connection_recent_failure(self, service):
        """Test retry logic with recent connection failure."""
        service._connection_failed = True
        service._last_connection_attempt = datetime.now(timezone.utc)
        
        result = service._should_retry_connection()
        assert result is False
    
    def test_should_retry_connection_old_failure(self, service):
        """Test retry logic with old connection failure."""
        service._connection_failed = True
        # Set last attempt to 10 minutes ago (older than 5 minute retry interval)
        past_time = datetime.now(timezone.utc).timestamp() - 600
        service._last_connection_attempt = datetime.fromtimestamp(past_time, timezone.utc)
        
        result = service._should_retry_connection()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_emit_invoice_ready_event_retry_connection(self, service, mock_redis_client):
        """Test that event emission retries connection after interval."""
        # Set up initial connection failure
        service._connection_failed = True
        past_time = datetime.now(timezone.utc).timestamp() - 600  # 10 minutes ago
        service._last_connection_attempt = datetime.fromtimestamp(past_time, timezone.utc)
        
        # Mock the client property to return the mock client after retry
        with patch.object(type(service), 'client', new_callable=PropertyMock) as mock_client_prop:
            mock_client_prop.return_value = mock_redis_client
            
            load_id = uuid4()
            driver_id = uuid4()
            
            result = await service.emit_invoice_ready_event(load_id, driver_id)
            
            assert result is True
            # Connection should be reset for retry
            assert service._connection_failed is False
            assert service._client is None  # Reset for retry


if __name__ == "__main__":
    pytest.main([__file__]) 
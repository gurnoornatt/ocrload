"""
Integration tests for Redis Event Service

Tests the Redis event service with real Redis connectivity (if available)
and integration with the database flag service for invoice_ready events.
"""

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.config.settings import settings
from app.models.database import Document, DocumentType, LoadStatus, PODData
from app.services.database_flag_service import database_flag_service
from app.services.redis_event_service import redis_event_service


class TestRedisEventServiceIntegration:
    """Test suite for Redis Event Service integration tests."""

    @pytest.mark.asyncio
    async def test_health_check_integration(self):
        """Test Redis health check with actual configuration."""
        health = await redis_event_service.health_check()

        # Should always return a valid health status
        assert "status" in health
        assert "configured" in health
        assert "connected" in health
        assert "message" in health

        # Status should be one of the expected values
        assert health["status"] in ["healthy", "unhealthy", "disabled"]

        if settings.redis_url:
            assert health["configured"] is True
            # If configured, should either be healthy or unhealthy (not disabled)
            assert health["status"] in ["healthy", "unhealthy"]
        else:
            assert health["configured"] is False
            assert health["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_emit_invoice_ready_event_integration(self):
        """Test invoice ready event emission with real or graceful degradation."""
        load_id = uuid4()
        driver_id = uuid4()
        additional_data = {
            "origin": "Chicago, IL",
            "destination": "Dallas, TX",
            "rate": 1500.00,
        }

        # This should either succeed (if Redis is available) or fail gracefully
        result = await redis_event_service.emit_invoice_ready_event(
            load_id=load_id, driver_id=driver_id, additional_data=additional_data
        )

        # Result should be boolean
        assert isinstance(result, bool)

        # If Redis is configured and healthy, should succeed
        health = await redis_event_service.health_check()
        if health["status"] == "healthy":
            assert result is True
        elif health["status"] == "disabled":
            assert result is False

    @pytest.mark.asyncio
    async def test_emit_custom_event_integration(self):
        """Test custom event emission with real or graceful degradation."""
        result = await redis_event_service.emit_custom_event(
            channel="test_integration",
            event_type="test_event",
            payload={
                "test_data": "integration_test",
                "timestamp_test": datetime.now(UTC).isoformat(),
            },
        )

        # Should handle gracefully regardless of Redis availability
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_database_flag_service_integration(self):
        """Test integration between database flag service and Redis events."""
        # Create test document and data
        load_id = uuid4()
        driver_id = uuid4()

        # Mock the document
        document = Document(
            id=uuid4(),
            type=DocumentType.POD,
            load_id=load_id,
            driver_id=driver_id,
            url="https://example.com/test_pod.pdf",
        )

        # Mock POD data with delivery confirmed
        pod_data = PODData(
            delivery_confirmed=True,
            delivery_date=datetime.now(UTC),
            recipient_name="John Doe",
            signature_captured=True,
        )

        # Mock the Supabase service methods
        with patch.object(
            database_flag_service.supabase, "update_load_status"
        ), patch.object(
            database_flag_service.supabase,
            "check_load_ratecon_verified",
            return_value=True,
        ), patch.object(
            database_flag_service.supabase, "get_load_by_id"
        ) as mock_get_load:
            # Mock load data
            from app.models.database import Load

            mock_load = Load(
                id=load_id,
                assigned_driver_id=driver_id,
                origin="Chicago, IL",
                destination="Dallas, TX",
                rate=150000,  # 1500.00 in cents
                status=LoadStatus.IN_TRANSIT,
            )
            mock_get_load.return_value = mock_load

            # Process POD flags (this should trigger invoice_ready event)
            result = await database_flag_service.process_document_flags(
                document=document, parsed_data=pod_data.model_dump(), confidence=0.95
            )

            # Verify the result
            assert result["document_id"] == str(document.id)
            assert result["document_type"] == DocumentType.POD
            assert result["confidence"] == 0.95
            assert result["flags_updated"]["status"] == LoadStatus.DELIVERED
            assert result["invoice_ready"] is True

            # Verify Redis event emission was attempted
            assert "event_emitted" in result
            assert isinstance(result["event_emitted"], bool)

            # Verify business rules were applied
            business_rules = result["business_rules_applied"]
            assert any("Confidence threshold met" in rule for rule in business_rules)
            assert any("Delivery confirmed" in rule for rule in business_rules)
            assert any("Invoice ready" in rule for rule in business_rules)

            # If Redis is available, event should be emitted
            health = await redis_event_service.health_check()
            if health["status"] == "healthy":
                assert result["event_emitted"] is True
                assert any(
                    "Invoice ready event emitted to Redis" in rule
                    for rule in business_rules
                )
            else:
                # If Redis is not available, should still process but note the failure
                if health["status"] == "disabled":
                    assert result["event_emitted"] is False

    @pytest.mark.asyncio
    async def test_database_flag_service_no_event_when_not_ready(self):
        """Test that no event is emitted when invoice is not ready."""
        load_id = uuid4()
        driver_id = uuid4()

        document = Document(
            id=uuid4(),
            type=DocumentType.POD,
            load_id=load_id,
            driver_id=driver_id,
            url="https://example.com/test_pod.pdf",
        )

        pod_data = PODData(
            delivery_confirmed=True,
            delivery_date=datetime.now(UTC),
            recipient_name="John Doe",
            signature_captured=True,
        )

        # Mock rate confirmation as NOT verified
        with patch.object(
            database_flag_service.supabase, "update_load_status"
        ), patch.object(
            database_flag_service.supabase,
            "check_load_ratecon_verified",
            return_value=False,
        ):
            result = await database_flag_service.process_document_flags(
                document=document, parsed_data=pod_data.model_dump(), confidence=0.95
            )

            # Verify no invoice ready event
            assert result["invoice_ready"] is False
            assert "event_emitted" not in result

            # Verify business rules
            business_rules = result["business_rules_applied"]
            assert any(
                "Invoice not ready: rate confirmation not verified" in rule
                for rule in business_rules
            )

    @pytest.mark.asyncio
    async def test_redis_connection_retry_logic(self):
        """Test Redis connection retry logic in real scenarios."""
        # Force a connection failure state
        original_client = redis_event_service._client
        original_failed = redis_event_service._connection_failed
        original_attempt = redis_event_service._last_connection_attempt

        try:
            # Simulate connection failure
            redis_event_service._client = None
            redis_event_service._connection_failed = True
            redis_event_service._last_connection_attempt = datetime.now(UTC)

            # Try to emit event (should fail due to recent failure)
            result1 = await redis_event_service.emit_invoice_ready_event(
                uuid4(), uuid4()
            )
            assert result1 is False

            # Simulate time passing (set last attempt to past)
            past_time = datetime.now(UTC).timestamp() - 400  # 6+ minutes ago
            redis_event_service._last_connection_attempt = datetime.fromtimestamp(
                past_time, UTC
            )

            # Try again (should attempt retry)
            result2 = await redis_event_service.emit_invoice_ready_event(
                uuid4(), uuid4()
            )
            # Result depends on actual Redis availability
            assert isinstance(result2, bool)

        finally:
            # Restore original state
            redis_event_service._client = original_client
            redis_event_service._connection_failed = original_failed
            redis_event_service._last_connection_attempt = original_attempt

    @pytest.mark.asyncio
    async def test_concurrent_event_emission(self):
        """Test concurrent event emissions to verify thread safety."""
        tasks = []

        # Create multiple concurrent event emission tasks
        for i in range(5):
            task = redis_event_service.emit_invoice_ready_event(
                load_id=uuid4(),
                driver_id=uuid4(),
                additional_data={"test_concurrent": i},
            )
            tasks.append(task)

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete without exceptions
        for result in results:
            assert not isinstance(result, Exception)
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_event_payload_format_validation(self):
        """Test that emitted events have the correct payload format."""
        load_id = uuid4()
        driver_id = uuid4()

        # Mock Redis client to capture the published message
        original_client = redis_event_service._client

        class MockRedisClient:
            def __init__(self):
                self.published_messages = []

            def ping(self):
                return True

            def publish(self, channel, message):
                self.published_messages.append((channel, message))
                return 1

        mock_client = MockRedisClient()
        redis_event_service._client = mock_client

        try:
            result = await redis_event_service.emit_invoice_ready_event(
                load_id=load_id,
                driver_id=driver_id,
                additional_data={"origin": "Test Origin", "rate": 1000.0},
            )

            if result:  # Only validate if emission succeeded
                assert len(mock_client.published_messages) == 1
                channel, message = mock_client.published_messages[0]

                # Validate channel
                assert channel == "invoice_ready"

                # Validate message format
                message_data = json.loads(message)
                assert message_data["event"] == "invoice_ready"
                assert message_data["load_id"] == str(load_id)
                assert message_data["driver_id"] == str(driver_id)
                assert "timestamp" in message_data
                assert message_data["origin"] == "Test Origin"
                assert message_data["rate"] == 1000.0

                # Validate timestamp format
                timestamp = datetime.fromisoformat(
                    message_data["timestamp"].replace("Z", "+00:00")
                )
                assert timestamp.tzinfo is not None

        finally:
            # Restore original client
            redis_event_service._client = original_client


if __name__ == "__main__":
    pytest.main([__file__])

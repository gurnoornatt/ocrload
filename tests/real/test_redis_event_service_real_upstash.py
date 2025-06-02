"""Real integration test for Redis Event Service with actual Upstash Redis."""

import asyncio
import os

import pytest

# Load from environment variables - DO NOT hardcode production credentials
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL")
TEST_REDIS_TOKEN = os.getenv("TEST_REDIS_TOKEN")


@pytest.mark.skipif(
    not TEST_REDIS_URL or not TEST_REDIS_TOKEN,
    reason="TEST_REDIS_URL and TEST_REDIS_TOKEN environment variables required for real Redis testing",
)
class TestRedisEventServiceReal:
    """Test Redis Event Service with real Upstash connection."""

    @pytest.fixture
    async def redis_service(self):
        """Create Redis service instance for testing."""
        service = RedisEventService()
        yield service
        service.close()

    @pytest.mark.asyncio
    async def test_health_check_real_connection(self, redis_service):
        """Test health check with real Upstash connection."""
        health_result = await redis_service.health_check()

        assert health_result["status"] == "healthy"
        assert "timestamp" in health_result
        print(f"✅ Health check passed: {health_result}")

    @pytest.mark.asyncio
    async def test_emit_invoice_ready_event_real(self, redis_service):
        """Test emitting invoice ready event to real Redis."""
        load_id = "test_load_real_123"
        driver_id = "test_driver_real_456"

        # Emit the event
        success = await redis_service.emit_invoice_ready(load_id, driver_id)

        assert success is True
        print(f"✅ Invoice ready event emitted for load {load_id}")

    @pytest.mark.asyncio
    async def test_multiple_events_real(self, redis_service):
        """Test emitting multiple events in sequence."""
        events = [
            ("load_001", "driver_001"),
            ("load_002", "driver_002"),
            ("load_003", "driver_003"),
        ]

        results = []
        for load_id, driver_id in events:
            success = await redis_service.emit_invoice_ready(load_id, driver_id)
            results.append(success)

        assert all(results), f"Some events failed: {results}"
        print(f"✅ All {len(events)} events emitted successfully")

    @pytest.mark.asyncio
    async def test_error_handling_invalid_data(self, redis_service):
        """Test error handling with edge cases."""
        # Test with empty strings (should still work)
        success = await redis_service.emit_invoice_ready("", "")
        assert success is True  # Empty strings are valid JSON

        # Test with None values (should be handled gracefully)
        success = await redis_service.emit_invoice_ready(None, None)
        assert success is True  # None will be serialized as null in JSON

        print("✅ Error handling tests passed")


async def manual_test():
    """Manual test function to run outside pytest."""
    print("🧪 Running manual Redis integration test...")

    service = RedisEventService()

    # Test 1: Health check
    print("\n1️⃣ Testing health check...")
    health = await service.health_check()
    print(f"Health: {health}")

    # Test 2: Single event
    print("\n2️⃣ Testing single event emission...")
    success = await service.emit_invoice_ready("manual_load_123", "manual_driver_456")
    print(f"Event emission success: {success}")

    # Test 3: Multiple events
    print("\n3️⃣ Testing multiple events...")
    for i in range(3):
        success = await service.emit_invoice_ready(
            f"batch_load_{i}", f"batch_driver_{i}"
        )
        print(f"Batch event {i} success: {success}")

    service.close()
    print("✅ Manual test completed!")


if __name__ == "__main__":
    # Run manual test
    asyncio.run(manual_test())

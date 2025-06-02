"""Tests for health check endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_basic():
    """Test that /health returns 200 and correct structure."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    # Check required fields
    assert data["ok"] is True
    # Status can be "healthy" or "degraded" depending on permissions
    assert data["status"] in ["healthy", "degraded"]
    assert "timestamp" in data
    assert "service" in data
    assert "version" in data
    assert "environment" in data
    assert "checks" in data
    assert "response_time_ms" in data

    # Check that response time is reasonable (allowing for network calls to Supabase)
    assert data["response_time_ms"] < 2000

    # Check environment checks structure
    assert "environment" in data["checks"]
    env_check = data["checks"]["environment"]
    assert "status" in env_check
    assert "supabase_url_configured" in env_check
    assert "supabase_service_key_configured" in env_check
    assert "datalab_api_key_configured" in env_check


def test_readiness_endpoint_basic():
    """Test that /health/ready returns correct structure."""
    response = client.get("/health/ready")

    # Status code depends on configuration completeness
    assert response.status_code in [200, 503]
    data = response.json()

    # Check required fields
    assert "ready" in data
    assert "timestamp" in data
    assert "service" in data
    assert "version" in data
    assert "checks" in data
    assert "response_time_ms" in data

    # Check configuration checks structure
    assert "configuration" in data["checks"]
    config_check = data["checks"]["configuration"]
    assert "status" in config_check
    assert "message" in config_check


def test_health_endpoint_performance():
    """Test that health endpoint responds quickly for liveness probes."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    # Health check should be reasonably fast (allowing for network calls to Supabase)
    # In production with proper service keys, this should be much faster
    assert (
        data["response_time_ms"] < 2000
    ), f"Health check too slow: {data['response_time_ms']}ms"


def test_health_response_headers():
    """Test that health endpoint has appropriate headers."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    # Should have timing headers from middleware
    assert "x-process-time" in response.headers
    assert "x-request-id" in response.headers

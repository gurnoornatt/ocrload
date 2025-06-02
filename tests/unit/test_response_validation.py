"""Unit tests for response model validation."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.responses import (
    DocumentFlags,
    ErrorResponse,
    HealthCheckResponse,
    MediaUploadResponse,
    ParseTestResponse,
    ProcessingStatusResponse,
    StandardAPIResponse,
)


class TestDocumentFlags:
    """Test DocumentFlags model."""

    def test_default_flags(self):
        """Test default flag values."""
        flags = DocumentFlags()
        assert flags.cdl_verified is False
        assert flags.insurance_verified is False
        assert flags.agreement_signed is False
        assert flags.ratecon_parsed is False
        assert flags.pod_ok is False

    def test_custom_flags(self):
        """Test custom flag values."""
        flags = DocumentFlags(
            cdl_verified=True,
            insurance_verified=True,
            agreement_signed=False,
            ratecon_parsed=True,
            pod_ok=False,
        )
        assert flags.cdl_verified is True
        assert flags.insurance_verified is True
        assert flags.agreement_signed is False
        assert flags.ratecon_parsed is True
        assert flags.pod_ok is False

    def test_flags_serialization(self):
        """Test flag serialization to dict."""
        flags = DocumentFlags(cdl_verified=True, insurance_verified=True)
        data = flags.model_dump()

        assert data == {
            "cdl_verified": True,
            "insurance_verified": True,
            "agreement_signed": False,
            "ratecon_parsed": False,
            "pod_ok": False,
        }


class TestStandardAPIResponse:
    """Test StandardAPIResponse base model."""

    def test_valid_response(self):
        """Test valid standard response."""
        doc_id = uuid4()
        response = StandardAPIResponse(success=True, doc_id=doc_id, confidence=0.95)

        assert response.success is True
        assert response.doc_id == doc_id
        assert response.needs_retry is False
        assert response.confidence == 0.95
        assert isinstance(response.flags, DocumentFlags)
        assert response.message is None
        assert isinstance(response.timestamp, datetime)
        assert response.request_id is None
        assert response.processing_time_ms is None

    def test_response_with_all_fields(self):
        """Test response with all fields populated."""
        doc_id = uuid4()
        flags = DocumentFlags(cdl_verified=True)
        timestamp = datetime.now(UTC)

        response = StandardAPIResponse(
            success=True,
            doc_id=doc_id,
            needs_retry=False,
            confidence=0.88,
            flags=flags,
            message="Processing complete",
            timestamp=timestamp,
            request_id="req_123",
            processing_time_ms=2500,
        )

        assert response.success is True
        assert response.doc_id == doc_id
        assert response.needs_retry is False
        assert response.confidence == 0.88
        assert response.flags.cdl_verified is True
        assert response.message == "Processing complete"
        assert response.timestamp == timestamp
        assert response.request_id == "req_123"
        assert response.processing_time_ms == 2500

    def test_confidence_validation(self):
        """Test confidence score validation."""
        doc_id = uuid4()

        # Valid confidence values
        response = StandardAPIResponse(success=True, doc_id=doc_id, confidence=0.0)
        assert response.confidence == 0.0

        response = StandardAPIResponse(success=True, doc_id=doc_id, confidence=1.0)
        assert response.confidence == 1.0

        response = StandardAPIResponse(success=True, doc_id=doc_id, confidence=0.5)
        assert response.confidence == 0.5

    def test_json_serialization(self):
        """Test JSON serialization."""
        doc_id = uuid4()
        response = StandardAPIResponse(
            success=True, doc_id=doc_id, confidence=0.95, message="Test message"
        )

        data = response.model_dump(mode="json")

        assert data["success"] is True
        assert data["doc_id"] == str(doc_id)
        assert data["confidence"] == 0.95
        assert data["message"] == "Test message"
        assert "timestamp" in data
        assert "flags" in data


class TestMediaUploadResponse:
    """Test MediaUploadResponse model."""

    def test_valid_media_response(self):
        """Test valid media upload response."""
        doc_id = uuid4()
        response = MediaUploadResponse(
            success=True, doc_id=doc_id, processing_url=f"/api/media/{doc_id}/status"
        )

        assert response.success is True
        assert response.doc_id == doc_id
        assert response.processing_url == f"/api/media/{doc_id}/status"
        assert response.confidence == 0.0  # Default for upload
        assert response.needs_retry is False

    def test_media_response_inheritance(self):
        """Test that MediaUploadResponse inherits from StandardAPIResponse."""
        doc_id = uuid4()
        response = MediaUploadResponse(
            success=True,
            doc_id=doc_id,
            processing_url="/test/url",
            message="Upload accepted",
            request_id="req_456",
        )

        # Standard fields
        assert response.success is True
        assert response.doc_id == doc_id
        assert response.message == "Upload accepted"
        assert response.request_id == "req_456"

        # Specific field
        assert response.processing_url == "/test/url"


class TestParseTestResponse:
    """Test ParseTestResponse model."""

    def test_valid_parse_test_response(self):
        """Test valid parse test response."""
        doc_id = uuid4()
        response = ParseTestResponse(
            success=True, doc_id=doc_id, processing_url=f"/api/media/{doc_id}/status"
        )

        assert response.success is True
        assert response.doc_id == doc_id
        assert response.processing_url == f"/api/media/{doc_id}/status"
        assert response.confidence == 0.0  # Default for parse test
        assert response.needs_retry is False


class TestProcessingStatusResponse:
    """Test ProcessingStatusResponse model."""

    def test_valid_status_response(self):
        """Test valid processing status response."""
        doc_id = uuid4()
        progress = {"step": "ocr", "completion": 50}

        response = ProcessingStatusResponse(
            success=True, doc_id=doc_id, status="processing", progress=progress
        )

        assert response.success is True
        assert response.doc_id == doc_id
        assert response.status == "processing"
        assert response.progress == progress
        assert response.result is None
        assert response.error is None
        assert response.metadata is None

    def test_complete_status_response(self):
        """Test complete processing status response."""
        doc_id = uuid4()
        progress = {"step": "completed", "completion": 100}
        result = {"extracted_text": "Sample text", "parsed_data": {}}
        metadata = {"doc_type": "CDL", "processing_time": 2500}

        response = ProcessingStatusResponse(
            success=True,
            doc_id=doc_id,
            confidence=0.95,
            status="completed",
            progress=progress,
            result=result,
            metadata=metadata,
        )

        assert response.success is True
        assert response.doc_id == doc_id
        assert response.confidence == 0.95
        assert response.status == "completed"
        assert response.progress == progress
        assert response.result == result
        assert response.metadata == metadata
        assert response.error is None

    def test_failed_status_response(self):
        """Test failed processing status response."""
        doc_id = uuid4()
        progress = {"step": "failed", "completion": 0}
        error = "OCR processing failed"

        response = ProcessingStatusResponse(
            success=False,
            doc_id=doc_id,
            needs_retry=True,
            status="failed",
            progress=progress,
            error=error,
        )

        assert response.success is False
        assert response.doc_id == doc_id
        assert response.needs_retry is True
        assert response.status == "failed"
        assert response.progress == progress
        assert response.error == error
        assert response.result is None


class TestErrorResponse:
    """Test ErrorResponse model."""

    def test_valid_error_response(self):
        """Test valid error response."""
        response = ErrorResponse(
            error="Document not found", error_code="DOCUMENT_NOT_FOUND", status_code=404
        )

        assert response.success is False
        assert response.error == "Document not found"
        assert response.error_code == "DOCUMENT_NOT_FOUND"
        assert response.status_code == 404
        assert response.details is None
        assert isinstance(response.timestamp, datetime)
        assert response.request_id is None

    def test_error_response_with_details(self):
        """Test error response with details."""
        details = {"doc_id": "123", "attempted_at": "2024-01-15T12:00:00Z"}

        response = ErrorResponse(
            error="Validation failed",
            error_code="VALIDATION_ERROR",
            details=details,
            request_id="req_789",
            status_code=422,
        )

        assert response.success is False
        assert response.error == "Validation failed"
        assert response.error_code == "VALIDATION_ERROR"
        assert response.details == details
        assert response.request_id == "req_789"
        assert response.status_code == 422

    def test_error_response_serialization(self):
        """Test error response JSON serialization."""
        response = ErrorResponse(
            error="Test error", error_code="TEST_ERROR", status_code=500
        )

        data = response.model_dump(mode="json")

        assert data["success"] is False
        assert data["error"] == "Test error"
        assert data["error_code"] == "TEST_ERROR"
        assert data["status_code"] == 500
        assert "timestamp" in data


class TestHealthCheckResponse:
    """Test HealthCheckResponse model."""

    def test_valid_health_response(self):
        """Test valid health check response."""
        checks = {
            "database": {"status": "ok", "message": "Connected"},
            "storage": {"status": "ok", "message": "Accessible"},
        }

        response = HealthCheckResponse(
            ok=True,
            status="healthy",
            service="ocr-load-service",
            version="1.0.0",
            environment="production",
            checks=checks,
            response_time_ms=45.2,
        )

        assert response.ok is True
        assert response.status == "healthy"
        assert response.service == "ocr-load-service"
        assert response.version == "1.0.0"
        assert response.environment == "production"
        assert response.checks == checks
        assert response.response_time_ms == 45.2
        assert isinstance(response.timestamp, datetime)

    def test_unhealthy_response(self):
        """Test unhealthy health check response."""
        checks = {
            "database": {"status": "error", "message": "Connection failed"},
            "storage": {"status": "error", "message": "Bucket not accessible"},
        }

        response = HealthCheckResponse(
            ok=False,
            status="unhealthy",
            service="ocr-load-service",
            version="1.0.0",
            environment="production",
            checks=checks,
            response_time_ms=120.5,
        )

        assert response.ok is False
        assert response.status == "unhealthy"
        assert response.checks == checks
        assert response.response_time_ms == 120.5

    def test_health_response_serialization(self):
        """Test health response JSON serialization."""
        checks = {"test": {"status": "ok"}}

        response = HealthCheckResponse(
            ok=True,
            status="healthy",
            service="test-service",
            version="1.0.0",
            environment="test",
            checks=checks,
            response_time_ms=10.0,
        )

        data = response.model_dump(mode="json")

        assert data["ok"] is True
        assert data["status"] == "healthy"
        assert data["service"] == "test-service"
        assert data["version"] == "1.0.0"
        assert data["environment"] == "test"
        assert data["checks"] == checks
        assert data["response_time_ms"] == 10.0
        assert "timestamp" in data


class TestResponseValidation:
    """Test response model field validation."""

    def test_required_fields(self):
        """Test that required fields are enforced."""
        # StandardAPIResponse requires success and doc_id
        with pytest.raises(ValidationError) as exc_info:
            StandardAPIResponse()

        errors = exc_info.value.errors()
        required_fields = [
            error["loc"][0] for error in errors if error["type"] == "missing"
        ]
        assert "success" in required_fields
        assert "doc_id" in required_fields

        # ErrorResponse requires error, error_code, and status_code
        with pytest.raises(ValidationError) as exc_info:
            ErrorResponse()

        errors = exc_info.value.errors()
        required_fields = [
            error["loc"][0] for error in errors if error["type"] == "missing"
        ]
        assert "error" in required_fields
        assert "error_code" in required_fields
        assert "status_code" in required_fields

    def test_uuid_validation(self):
        """Test UUID field validation."""
        # Valid UUID
        doc_id = uuid4()
        response = StandardAPIResponse(success=True, doc_id=doc_id)
        assert response.doc_id == doc_id

        # String representation of UUID should work
        response = StandardAPIResponse(success=True, doc_id=str(doc_id))
        assert response.doc_id == doc_id

        # Invalid UUID should fail
        with pytest.raises(ValidationError):
            StandardAPIResponse(success=True, doc_id="invalid-uuid")

    def test_type_validation(self):
        """Test field type validation."""
        doc_id = uuid4()

        # Test confidence validation range (should coerce string numbers)
        response = StandardAPIResponse(success=True, doc_id=doc_id, confidence="0.95")
        assert response.confidence == 0.95

        # Invalid confidence (non-numeric string should fail)
        with pytest.raises(ValidationError):
            StandardAPIResponse(success=True, doc_id=doc_id, confidence="high")

        # Test boolean coercion (strings "true"/"false" are coerced by Pydantic)
        response = StandardAPIResponse(success="true", doc_id=doc_id)
        assert response.success is True

        # Invalid boolean (non-boolean-like string should fail)
        with pytest.raises(ValidationError):
            StandardAPIResponse(success="maybe", doc_id=doc_id)

        # Integer validation for status code
        with pytest.raises(ValidationError):
            ErrorResponse(
                error="Test",
                error_code="TEST",
                status_code="not-a-number",  # String that can't be converted to int
            )

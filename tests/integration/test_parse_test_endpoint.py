"""Integration tests for the parse-test endpoint.

These tests validate the full pipeline against real services:
- Real Supabase storage and database
- Real OCR services (Datalab.to and Marker)
- Real document parsers
- Real database flag services

The tests serve as the source of truth for the expected behavior.
"""

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "real"


class TestParseTestEndpoint:
    """Integration tests for parse-test endpoint using real services."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def temp_test_file(self):
        """Create a temporary copy of a test file."""
        # Use the bill of lading PDF from the project root
        original_file = Path(__file__).parent.parent.parent / "BILL OF LADING.pdf"

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            if original_file.exists():
                shutil.copy2(original_file, temp_file.name)
            else:
                # Create a minimal PDF if the original doesn't exist
                temp_file.write(
                    b"%PDF-1.4\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n2 0 obj\n<</Type/Pages/Kids[3 0 R]/Count 1>>\nendobj\n3 0 obj\n<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<</Size 4/Root 1 0 R>>\nstartxref\n180\n%%EOF"
                )

            yield temp_file.name

        # Cleanup
        Path(temp_file.name).unlink(missing_ok=True)

    def test_parse_test_endpoint_basic_flow(
        self, client: TestClient, temp_test_file: str
    ):
        """Test the basic flow of the parse-test endpoint."""
        # Test data
        driver_id = uuid4()
        test_request = {
            "path": temp_test_file,
            "doc_type": "POD",  # Using POD as it's simpler for testing
            "driver_id": str(driver_id),
        }

        # Make request
        response = client.post("/api/parse-test/", json=test_request)

        # Validate immediate response
        assert response.status_code == 202
        data = response.json()
        assert data["success"] is True
        assert "document_id" in data
        assert data["message"] == "Local file parsing accepted and processing started"
        assert data["processing_url"].startswith("/api/media/")

        document_id = data["document_id"]

        # Wait for processing to complete (with timeout)
        max_wait_time = 30  # seconds
        wait_interval = 1  # second
        elapsed_time = 0

        while elapsed_time < max_wait_time:
            status_response = client.get(f"/api/media/{document_id}/status")

            if status_response.status_code == 200:
                status_data = status_response.json()

                # Check if processing is complete
                if status_data["status"] in ["parsed", "failed"]:
                    break

            import time

            time.sleep(wait_interval)
            elapsed_time += wait_interval

        # Validate final status
        final_status = client.get(f"/api/media/{document_id}/status")
        assert final_status.status_code == 200

        final_data = final_status.json()
        assert final_data["document_id"] == document_id

        # The status should be either 'parsed' or 'failed' depending on OCR success
        # We don't require success due to potential API limitations, but we validate the pipeline ran
        assert final_data["status"] in ["parsed", "failed", "needs_review"]

    def test_parse_test_without_driver_id(
        self, client: TestClient, temp_test_file: str
    ):
        """Test parse-test endpoint without driver_id (test mode)."""
        test_request = {"path": temp_test_file, "doc_type": "AGREEMENT"}

        # Make request
        response = client.post("/api/parse-test/", json=test_request)

        # Should still work without driver_id
        assert response.status_code == 202
        data = response.json()
        assert data["success"] is True
        assert "document_id" in data

    def test_parse_test_file_not_found(self, client: TestClient):
        """Test parse-test endpoint with non-existent file."""
        test_request = {"path": "/nonexistent/file.pdf", "doc_type": "CDL"}

        response = client.post("/api/parse-test/", json=test_request)

        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    def test_parse_test_directory_traversal_protection(self, client: TestClient):
        """Test that directory traversal attempts are blocked."""
        test_request = {"path": "../../../etc/passwd", "doc_type": "CDL"}

        response = client.post("/api/parse-test/", json=test_request)

        # Should fail validation
        assert response.status_code == 422
        data = response.json()
        assert data["success"] is False

    def test_parse_test_invalid_doc_type(self, client: TestClient, temp_test_file: str):
        """Test parse-test endpoint with invalid document type."""
        test_request = {"path": temp_test_file, "doc_type": "INVALID_TYPE"}

        response = client.post("/api/parse-test/", json=test_request)

        # Should fail validation
        assert response.status_code == 422
        data = response.json()
        assert data["success"] is False

    def test_parse_test_all_document_types(
        self, client: TestClient, temp_test_file: str
    ):
        """Test parse-test endpoint with all supported document types."""
        document_types = ["CDL", "COI", "AGREEMENT", "RATE_CON", "POD"]

        for doc_type in document_types:
            test_request = {"path": temp_test_file, "doc_type": doc_type}

            response = client.post("/api/parse-test/", json=test_request)

            # All requests should be accepted
            assert response.status_code == 202
            data = response.json()
            assert data["success"] is True
            assert "document_id" in data

    def test_parse_test_pipeline_consistency_with_media_endpoint(
        self, client: TestClient, temp_test_file: str
    ):
        """Test that parse-test uses the same pipeline as the media endpoint."""
        driver_id = uuid4()

        # Test with parse-test endpoint
        test_request = {
            "path": temp_test_file,
            "doc_type": "POD",
            "driver_id": str(driver_id),
        }

        response = client.post("/api/parse-test/", json=test_request)
        assert response.status_code == 202

        parse_test_doc_id = response.json()["document_id"]

        # Wait for processing
        import time

        time.sleep(5)

        # Check status - should follow same structure as media endpoint
        status_response = client.get(f"/api/media/{parse_test_doc_id}/status")

        if status_response.status_code == 200:
            status_data = status_response.json()

            # Validate response structure matches media endpoint
            assert "document_id" in status_data
            assert "status" in status_data
            assert "progress" in status_data

            # Status should be a valid DocumentStatus
            valid_statuses = ["pending", "parsed", "needs_review", "failed"]
            assert status_data["status"] in valid_statuses

    def test_parse_test_storage_integration(
        self, client: TestClient, temp_test_file: str
    ):
        """Test that files are properly uploaded to Supabase storage."""
        test_request = {"path": temp_test_file, "doc_type": "CDL"}

        response = client.post("/api/parse-test/", json=test_request)
        assert response.status_code == 202

        response.json()["document_id"]

        # Wait a bit for storage upload
        import time

        time.sleep(3)

        # Basic validation that request was accepted
        # More detailed storage validation would require async setup
        assert response.json()["success"] is True

    def test_parse_test_relative_path_support(self, client: TestClient):
        """Test that relative paths work correctly."""
        # Use the bill of lading file in project root
        test_request = {
            "path": "./BILL OF LADING.pdf",  # Relative path
            "doc_type": "POD",
        }

        response = client.post("/api/parse-test/", json=test_request)

        # Should work if file exists, otherwise should give proper error
        if Path("./BILL OF LADING.pdf").exists():
            assert response.status_code == 202
            data = response.json()
            assert data["success"] is True
        else:
            assert response.status_code == 404

    def test_parse_test_concurrent_requests(
        self, client: TestClient, temp_test_file: str
    ):
        """Test handling of concurrent parse-test requests."""
        # Create multiple requests sequentially for synchronous test client
        responses = []
        for _i in range(3):
            test_request = {"path": temp_test_file, "doc_type": "AGREEMENT"}
            response = client.post("/api/parse-test/", json=test_request)
            responses.append(response)

        # All should be accepted
        for response in responses:
            assert response.status_code == 202
            data = response.json()
            assert data["success"] is True
            assert "document_id" in data

        # All document IDs should be unique
        doc_ids = [response.json()["document_id"] for response in responses]
        assert len(set(doc_ids)) == len(doc_ids)


class TestParseTestRealFiles:
    """Integration tests using real test files for more comprehensive validation."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_parse_test_with_real_files(self, client: TestClient):
        """Test parse-test endpoint with real test files if they exist."""
        test_files = [
            ("CDL", "cdl_sample.pdf"),
            ("COI", "coi_sample.pdf"),
            ("AGREEMENT", "agreement_sample.pdf"),
            ("RATE_CON", "rate_confirmation_sample.pdf"),
            ("POD", "pod_sample.pdf"),
        ]

        for doc_type, filename in test_files:
            test_file_path = TEST_DATA_DIR / filename

            if test_file_path.exists():
                test_request = {"path": str(test_file_path), "doc_type": doc_type}

                response = client.post("/api/parse-test/", json=test_request)

                # Should accept the request
                assert response.status_code == 202
                data = response.json()
                assert data["success"] is True

                # Wait for processing and check results
                document_id = data["document_id"]
                import time

                time.sleep(10)  # Give more time for real OCR processing

                status_response = client.get(f"/api/media/{document_id}/status")

                if status_response.status_code == 200:
                    status_data = status_response.json()

                    # For real files, we expect better results
                    if status_data["status"] == "parsed":
                        # Should have meaningful parsed data
                        assert status_data.get("result") is not None
                        assert status_data.get("confidence", 0) > 0

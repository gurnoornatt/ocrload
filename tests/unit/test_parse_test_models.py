"""Unit tests for parse-test endpoint models and validation."""

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.database import DocumentType
from app.routers.parse_test import ParseTestRequest


class TestParseTestRequest:
    """Unit tests for ParseTestRequest model validation."""

    def test_valid_absolute_path(self):
        """Test validation with valid absolute path."""
        with tempfile.NamedTemporaryFile() as temp_file:
            request = ParseTestRequest(path=temp_file.name, doc_type=DocumentType.CDL)
            assert request.path == str(Path(temp_file.name).resolve())
            assert request.doc_type == DocumentType.CDL

    def test_valid_relative_path(self):
        """Test validation with valid relative path."""
        # Use current file as test
        current_file = Path(__file__)
        relative_path = str(current_file.relative_to(Path.cwd()))

        request = ParseTestRequest(path=relative_path, doc_type=DocumentType.POD)

        # Should resolve to absolute path
        assert Path(request.path).is_absolute()
        assert request.doc_type == DocumentType.POD

    def test_directory_traversal_prevention(self):
        """Test that directory traversal attempts are blocked."""
        malicious_paths = [
            "../../../etc/passwd",
            "../../config/secrets.yml",
            "/etc/../etc/passwd",
            "C:\\..\\..\\Windows\\System32\\config\\SAM",
        ]

        for malicious_path in malicious_paths:
            with pytest.raises(ValidationError) as exc_info:
                ParseTestRequest(path=malicious_path, doc_type=DocumentType.CDL)

            # Should contain directory traversal error
            error_details = exc_info.value.errors()
            assert any(
                "Directory traversal not allowed" in str(error.get("msg", ""))
                or "Invalid file path" in str(error.get("msg", ""))
                for error in error_details
            )

    def test_invalid_path_format(self):
        """Test validation with invalid path formats."""
        invalid_paths = [
            "",  # Empty path
            "   ",  # Whitespace only
            None,  # None value would be caught by pydantic
        ]

        for invalid_path in invalid_paths:
            if invalid_path is None:
                # Pydantic should catch None values
                with pytest.raises(ValidationError):
                    ParseTestRequest(path=invalid_path, doc_type=DocumentType.CDL)
            else:
                # Empty string or whitespace should fail our validation
                with pytest.raises(ValidationError) as exc_info:
                    ParseTestRequest(path=invalid_path, doc_type=DocumentType.CDL)

                # Should contain appropriate error message
                error_details = exc_info.value.errors()
                assert any(
                    "Path cannot be empty" in str(error.get("msg", ""))
                    or "Invalid file path" in str(error.get("msg", ""))
                    for error in error_details
                )

    def test_all_document_types(self):
        """Test that all document types are supported."""
        with tempfile.NamedTemporaryFile() as temp_file:
            for doc_type in DocumentType:
                request = ParseTestRequest(path=temp_file.name, doc_type=doc_type)
                assert request.doc_type == doc_type

    def test_optional_fields(self):
        """Test that driver_id and load_id are optional."""
        with tempfile.NamedTemporaryFile() as temp_file:
            # Without optional fields
            request = ParseTestRequest(
                path=temp_file.name, doc_type=DocumentType.AGREEMENT
            )
            assert request.driver_id is None
            assert request.load_id is None

            # With optional fields
            from uuid import uuid4

            driver_id = uuid4()
            load_id = uuid4()

            request_with_ids = ParseTestRequest(
                path=temp_file.name,
                doc_type=DocumentType.AGREEMENT,
                driver_id=driver_id,
                load_id=load_id,
            )
            assert request_with_ids.driver_id == driver_id
            assert request_with_ids.load_id == load_id

    def test_path_resolution_edge_cases(self):
        """Test path resolution for edge cases."""
        with tempfile.NamedTemporaryFile() as temp_file:
            # Test with symbolic links (if supported)
            test_cases = [
                temp_file.name,  # Regular file
                str(Path(temp_file.name).resolve()),  # Already resolved
            ]

            for test_path in test_cases:
                request = ParseTestRequest(path=test_path, doc_type=DocumentType.CDL)

                # Should always resolve to absolute path
                result_path = Path(request.path)
                assert result_path.is_absolute()

    def test_model_serialization(self):
        """Test that the model can be serialized/deserialized properly."""
        with tempfile.NamedTemporaryFile() as temp_file:
            from uuid import uuid4

            original_request = ParseTestRequest(
                path=temp_file.name,
                doc_type=DocumentType.COI,
                driver_id=uuid4(),
                load_id=uuid4(),
            )

            # Convert to dict and back
            request_dict = original_request.model_dump()
            reconstructed_request = ParseTestRequest(**request_dict)

            assert reconstructed_request.path == original_request.path
            assert reconstructed_request.doc_type == original_request.doc_type
            assert reconstructed_request.driver_id == original_request.driver_id
            assert reconstructed_request.load_id == original_request.load_id

    def test_json_encoding_config(self):
        """Test that UUID fields are properly encoded to strings."""
        with tempfile.NamedTemporaryFile() as temp_file:
            from uuid import uuid4

            driver_id = uuid4()
            load_id = uuid4()

            request = ParseTestRequest(
                path=temp_file.name,
                doc_type=DocumentType.RATE_CON,
                driver_id=driver_id,
                load_id=load_id,
            )

            # Test JSON serialization
            json_data = request.model_dump(mode="json")

            # UUIDs should be converted to strings
            assert isinstance(json_data["driver_id"], str)
            assert isinstance(json_data["load_id"], str)
            assert json_data["driver_id"] == str(driver_id)
            assert json_data["load_id"] == str(load_id)

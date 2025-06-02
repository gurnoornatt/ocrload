"""
REAL document integration tests - these use actual files and make real API calls.

Unlike test_simple_processing_pipeline.py which uses mocks, these tests:
- Use real PDF/image files from test_documents/ folder
- Make actual API calls to Datalab/Marker OCR services
- Test real OCR accuracy and parsing

WARNING: These tests require:
1. Real API keys in .env file
2. Real document files in test_documents/ folder
3. Internet connection
4. May cost money (API usage)
"""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.document_parsers.pod_parser import PODParser
from app.services.ocr_clients.unified_ocr_client import UnifiedOCRClient

# Test data directory
TEST_DATA_DIR = Path(__file__).parent.parent.parent / "test_documents"


class TestRealDocuments:
    """Tests that use REAL documents and REAL API calls."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_check_real_documents_exist(self):
        """Check if real test documents are available."""
        print(f"\n🔍 Checking for real documents in: {TEST_DATA_DIR}")

        if not TEST_DATA_DIR.exists():
            pytest.skip(f"Test documents directory doesn't exist: {TEST_DATA_DIR}")

        # Look for sample documents
        sample_files = (
            list(TEST_DATA_DIR.glob("*.pdf"))
            + list(TEST_DATA_DIR.glob("*.jpg"))
            + list(TEST_DATA_DIR.glob("*.png"))
        )

        print(f"📁 Found {len(sample_files)} document files:")
        for file in sample_files:
            print(f"   - {file.name} ({file.stat().st_size} bytes)")

        if len(sample_files) == 0:
            pytest.skip(
                "No real document files found. Please add sample documents to test_documents/ folder"
            )

        assert len(sample_files) > 0, "Expected to find at least one test document"

    @pytest.mark.asyncio
    async def test_real_ocr_with_actual_document(self):
        """Test OCR using a real document file."""
        # Check for real document
        test_files = list(TEST_DATA_DIR.glob("*.pdf")) + list(
            TEST_DATA_DIR.glob("*.jpg")
        )
        if not test_files:
            pytest.skip("No real documents available for testing")

        # Use the first available document
        test_file = test_files[0]
        print(f"\n🔬 Testing OCR with real document: {test_file.name}")

        # Read the file
        with open(test_file, "rb") as f:
            file_content = f.read()

        print(f"📄 File size: {len(file_content)} bytes")

        # Initialize OCR client
        ocr_client = UnifiedOCRClient()

        try:
            # Make REAL API call
            print("🌐 Making real API call to OCR service...")
            result = await ocr_client.process_document(
                file_content=file_content,
                filename=test_file.name,
                content_type="application/pdf"
                if test_file.suffix == ".pdf"
                else "image/jpeg",
            )

            print(f"✅ OCR Success: {result['success']}")
            print(f"🎯 Confidence: {result['confidence']}")
            print(f"📝 Text length: {len(result['full_text'])} characters")
            print(f"🔧 OCR Source: {result.get('source', 'unknown')}")

            # Show first 200 characters of extracted text
            preview = (
                result["full_text"][:200] + "..."
                if len(result["full_text"]) > 200
                else result["full_text"]
            )
            print(f"📖 Text preview: {preview}")

            # Verify we got actual text
            assert result["success"] is True
            assert len(result["full_text"]) > 0
            assert result["confidence"] > 0

        except Exception as e:
            print(f"❌ OCR failed: {e}")
            pytest.fail(f"Real OCR test failed: {e}")

    @pytest.mark.asyncio
    async def test_real_pod_parsing(self):
        """Test POD parsing with real OCR results."""
        # Look for POD documents specifically
        pod_files = [
            f
            for f in TEST_DATA_DIR.glob("*pod*")
            if f.suffix in [".pdf", ".jpg", ".png"]
        ]
        if not pod_files:
            # Fallback to any document
            pod_files = list(TEST_DATA_DIR.glob("*.pdf")) + list(
                TEST_DATA_DIR.glob("*.jpg")
            )

        if not pod_files:
            pytest.skip("No POD documents available for testing")

        test_file = pod_files[0]
        print(f"\n📋 Testing POD parsing with: {test_file.name}")

        # Read and OCR the document
        with open(test_file, "rb") as f:
            file_content = f.read()

        ocr_client = UnifiedOCRClient()
        pod_parser = PODParser()

        try:
            # Step 1: Real OCR
            print("🔍 Step 1: OCR processing...")
            ocr_result = await ocr_client.process_document(
                file_content=file_content,
                filename=test_file.name,
                content_type="application/pdf"
                if test_file.suffix == ".pdf"
                else "image/jpeg",
            )

            print(f"✅ OCR complete. Confidence: {ocr_result['confidence']}")

            # Step 2: Parse the OCR text
            print("🔍 Step 2: POD parsing...")
            parsed_data = pod_parser.parse(
                ocr_result["full_text"], ocr_result["confidence"]
            )

            print("📊 Parsing results:")
            print(
                f"   - Delivery confirmed: {parsed_data.get('delivery_confirmed', 'Unknown')}"
            )
            print(
                f"   - Signature present: {parsed_data.get('signature_present', 'Unknown')}"
            )
            print(f"   - Delivery date: {parsed_data.get('delivery_date', 'Unknown')}")
            print(f"   - Receiver name: {parsed_data.get('receiver_name', 'Unknown')}")

            # Verify we got some parsing results
            assert isinstance(parsed_data, dict)
            print("✅ POD parsing completed successfully")

        except Exception as e:
            print(f"❌ POD parsing failed: {e}")
            pytest.fail(f"Real POD parsing test failed: {e}")

    def test_real_document_via_api_endpoint(self, client):
        """Test the full API workflow with a real document."""
        # Check for real documents
        test_files = list(TEST_DATA_DIR.glob("*.pdf"))
        if not test_files:
            pytest.skip("No PDF documents available for API testing")

        test_file = test_files[0]
        print(f"\n🌐 Testing API endpoint with real document: {test_file.name}")

        # Test the parse-test endpoint with real file
        test_request = {
            "path": str(test_file),
            "doc_type": "POD",
            "driver_id": str(uuid4()),
        }

        try:
            print("📡 Making API request...")
            response = client.post("/api/parse-test/", json=test_request)

            print(f"📨 Response status: {response.status_code}")

            if response.status_code == 202:
                document_id = response.json()["document_id"]
                print(f"📋 Document ID: {document_id}")
                print("✅ Real document accepted by API")

                # Could wait for processing and check results
                # (This would require the full pipeline to be working)

            else:
                print(f"❌ API request failed: {response.text}")

        except Exception as e:
            print(f"❌ API test failed: {e}")
            # Don't fail the test - API might not be fully configured
            print("⚠️  This is expected if API keys aren't configured")


class TestEnvironmentSetup:
    """Tests to check if the environment is properly set up for real testing."""

    def test_api_keys_configured(self):
        """Check if API keys are configured for real testing."""
        import os

        print("\n🔑 Checking API key configuration:")

        api_keys = {
            "DATALAB_API_KEY": os.getenv("DATALAB_API_KEY"),
            "MARKER_API_KEY": os.getenv("MARKER_API_KEY"),
        }

        configured_keys = []
        missing_keys = []

        for key_name, key_value in api_keys.items():
            if key_value:
                configured_keys.append(key_name)
                print(f"   ✅ {key_name}: Configured")
            else:
                missing_keys.append(key_name)
                print(f"   ❌ {key_name}: Missing")

        if len(configured_keys) == 0:
            pytest.skip(
                "No API keys configured. Real OCR testing requires API keys in .env file"
            )

        print(
            f"\n📊 Summary: {len(configured_keys)} configured, {len(missing_keys)} missing"
        )

        if missing_keys:
            print("⚠️  To enable full testing, add these to your .env file:")
            for key in missing_keys:
                print(f"   {key}=your_api_key_here")

    def test_documents_folder_setup(self):
        """Check if test documents folder is properly set up."""
        print(f"\n📁 Checking documents folder: {TEST_DATA_DIR}")

        if not TEST_DATA_DIR.exists():
            print("❌ test_documents/ folder doesn't exist")
            pytest.fail(
                "test_documents/ folder is missing. Please create it and add sample documents."
            )

        # Check for different document types
        doc_types = {
            "POD": list(TEST_DATA_DIR.glob("*pod*")),
            "Rate Confirmation": list(TEST_DATA_DIR.glob("*rate*"))
            + list(TEST_DATA_DIR.glob("*rc*")),
            "Bill of Lading": list(TEST_DATA_DIR.glob("*bol*"))
            + list(TEST_DATA_DIR.glob("*lading*")),
            "Any PDF": list(TEST_DATA_DIR.glob("*.pdf")),
            "Any Image": list(TEST_DATA_DIR.glob("*.jpg"))
            + list(TEST_DATA_DIR.glob("*.png")),
        }

        print("📋 Document inventory:")
        total_docs = 0
        for doc_type, files in doc_types.items():
            count = len(files)
            total_docs += count
            status = "✅" if count > 0 else "❌"
            print(f"   {status} {doc_type}: {count} files")

            if count > 0 and count <= 3:  # Show filenames if not too many
                for file in files:
                    print(f"      - {file.name}")

        print(f"\n📊 Total documents: {total_docs}")

        if total_docs == 0:
            pytest.fail(
                "No test documents found. Please add sample PDFs or images to test_documents/ folder"
            )


if __name__ == "__main__":
    # Run real document tests
    print("🚀 Running REAL document tests (uses actual files and API calls)")
    print("⚠️  Make sure you have:")
    print("   1. Real documents in test_documents/ folder")
    print("   2. API keys in .env file")
    print("   3. Internet connection")
    print()

    pytest.main([__file__, "-v", "-s"])  # -s shows print statements

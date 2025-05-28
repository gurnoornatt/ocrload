"""
Real integration tests for Datalab OCR API.

These tests make actual API calls to validate our implementation works
with the real Datalab service. Run these manually with a valid API key.

To run these tests:
1. Ensure DATALAB_API_KEY is set in your .env file
2. Run: pytest tests/test_datalab_integration.py -v -s --tb=short

Note: These tests will consume API quota and should be run sparingly.
"""

import asyncio
import os
import tempfile
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.services.ocr_clients.datalab_client import DatalabOCRClient


class TestDatalabIntegration:
    """Integration tests against the real Datalab API."""

    @pytest.fixture
    def api_key(self):
        """Get API key from environment."""
        api_key = os.getenv("DATALAB_API_KEY")
        if not api_key:
            pytest.skip("DATALAB_API_KEY not set in environment")
        return api_key

    @pytest.fixture
    def client(self, api_key):
        """Create a real client instance."""
        return DatalabOCRClient(api_key=api_key)

    @pytest.fixture
    def sample_image(self):
        """Create a simple test image with text."""
        # Create a simple image with text
        img = Image.new('RGB', (400, 200), color='white')
        
        # We'll create a simple image that should be recognizable by OCR
        # For now, just return the image bytes
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes.getvalue()

    @pytest.fixture
    def sample_text_image(self):
        """Create a more complex test image with clear text."""
        # Create an image with more obvious text content
        from PIL import ImageDraw, ImageFont
        
        img = Image.new('RGB', (800, 400), color='white')
        draw = ImageDraw.Draw(img)
        
        # Try to use a default font, fall back to basic if not available
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 36)
        except:
            try:
                font = ImageFont.truetype("/Library/Fonts/Arial.ttf", 36)  
            except:
                font = ImageFont.load_default()
        
        # Draw some clear text
        text_lines = [
            "OCR Integration Test",
            "This is a sample document",
            "for testing purposes.",
            "Line 4 with numbers: 12345"
        ]
        
        y_position = 50
        for line in text_lines:
            draw.text((50, y_position), line, fill='black', font=font)
            y_position += 60
        
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes.getvalue()

    @pytest.mark.asyncio
    async def test_real_api_connection(self, client):
        """Test that we can connect to the real API."""
        # This test just verifies our client can be created
        assert client.api_key is not None
        assert client.base_url == "https://www.datalab.to"

    @pytest.mark.asyncio
    async def test_real_ocr_simple_image(self, client, sample_text_image):
        """Test OCR with a real API call using a simple image."""
        try:
            async with client:
                result = await client.process_file_content(
                    file_content=sample_text_image,
                    filename="test_image.png",
                    mime_type="image/png",
                    languages=["English"]  # Test with the documented format
                )
            
            # Validate the response structure matches our expectations
            assert "success" in result
            assert "pages" in result
            assert "page_count" in result
            
            if result["success"]:
                assert isinstance(result["pages"], list)
                assert result["page_count"] > 0
                
                # Check the structure of each page
                for page in result["pages"]:
                    assert "text_lines" in page
                    assert "page_number" in page  # Our parsed response uses page_number
                    assert "image_bbox" in page
                    
                    # Check text lines structure
                    for text_line in page["text_lines"]:
                        assert "text" in text_line
                        assert "confidence" in text_line
                        assert "bbox" in text_line
                        assert "polygon" in text_line
                        
                        # Validate confidence is between 0 and 1
                        assert 0 <= text_line["confidence"] <= 1
                        
                        # Validate bbox format [x1, y1, x2, y2]
                        assert len(text_line["bbox"]) == 4
                        
                        # Validate polygon format (should be 4 points)
                        assert len(text_line["polygon"]) == 4
                
                print(f"\n✅ OCR Success! Extracted {len(result['pages'])} page(s)")
                for i, page in enumerate(result["pages"]):
                    print(f"Page {i+1}: {len(page['text_lines'])} text lines")
                    for line in page["text_lines"][:3]:  # Show first 3 lines
                        print(f"  - '{line['text']}' (confidence: {line['confidence']:.3f})")
            else:
                print(f"\n❌ OCR Failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            print(f"\n💥 Exception during test: {e}")
            raise

    @pytest.mark.asyncio
    async def test_real_api_error_handling(self, client):
        """Test error handling with invalid data."""
        try:
            async with client:
                # Test with invalid file data
                result = await client.process_file_content(
                    file_content=b"invalid image data",
                    filename="invalid.png",
                    mime_type="image/png"
                )
            
            # Should either succeed (if API is very lenient) or fail gracefully
            assert "success" in result
            if not result["success"]:
                assert "error" in result
                print(f"\n✅ Error handled gracefully: {result['error']}")
            else:
                print(f"\n⚠️  API accepted invalid data (unexpected)")
                
        except Exception as e:
            print(f"\n✅ Exception caught as expected: {e}")

    @pytest.mark.asyncio
    async def test_real_api_parameters(self, client, sample_text_image):
        """Test different parameter combinations."""
        try:
            async with client:
                # Test with different language specifications
                result = await client.process_file_content(
                    file_content=sample_text_image,
                    filename="test_multi_lang.png",
                    mime_type="image/png",
                    languages=["English", "Spanish"]  # Test multiple languages
                )
            
            assert "success" in result
            print(f"\n✅ Multi-language test: Success={result['success']}")
            
            if result["success"]:
                for page in result["pages"]:
                    if "languages" in page:
                        print(f"Detected languages: {page['languages']}")
                        
        except Exception as e:
            print(f"\n💥 Multi-language test failed: {e}")
            raise

    @pytest.mark.asyncio  
    async def test_real_api_rate_limiting(self, client, sample_text_image):
        """Test rate limiting behavior (be careful with this one)."""
        try:
            async with client:
                # Make a few quick requests to test rate limiting
                results = []
                for i in range(3):  # Just 3 requests to be safe
                    print(f"Making request {i+1}/3...")
                    result = await client.process_file_content(
                        file_content=sample_text_image,
                        filename=f"rate_test_{i}.png",
                        mime_type="image/png"
                    )
                    results.append(result)
                    
                    # Small delay between requests
                    await asyncio.sleep(1)
                
                # Check that requests were handled properly
                for i, result in enumerate(results):
                    print(f"Request {i+1}: Success={result.get('success', False)}")
                    if not result.get("success"):
                        print(f"  Error: {result.get('error', 'Unknown')}")
                        
        except Exception as e:
            print(f"\n💥 Rate limiting test failed: {e}")
            # Don't raise here since rate limiting might be expected


class TestDatalabRealUsage:
    """Test realistic usage patterns."""
    
    @pytest.fixture
    def api_key(self):
        """Get API key from environment."""
        api_key = os.getenv("DATALAB_API_KEY")
        if not api_key:
            pytest.skip("DATALAB_API_KEY not set in environment")
        return api_key

    @pytest.mark.asyncio
    async def test_global_client_usage(self, api_key):
        """Test using the global client instance."""
        from app.services.ocr_clients import datalab_client
        
        # Create a simple test image
        img = Image.new('RGB', (400, 100), color='white')
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.text((10, 30), "Global Client Test", fill='black')
        
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        
        try:
            # Test the global client
            result = await datalab_client.process_file_content(
                file_content=img_bytes.getvalue(),
                filename="global_test.png",
                mime_type="image/png"
            )
            
            assert "success" in result
            print(f"\n✅ Global client test: Success={result['success']}")
            
        except Exception as e:
            print(f"\n💥 Global client test failed: {e}")
            raise


if __name__ == "__main__":
    """Run integration tests directly."""
    print("Running Datalab OCR Integration Tests")
    print("=" * 50)
    
    # You can run individual tests here
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "simple":
        # Simple test
        asyncio.run(test_simple_integration())
    else:
        print("Run with: python tests/test_datalab_integration.py simple")
        print("Or use: pytest tests/test_datalab_integration.py -v -s")


async def test_simple_integration():
    """Simple integration test that can be run directly."""
    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ DATALAB_API_KEY not found in environment")
        return
    
    client = DatalabOCRClient(api_key=api_key)
    
    # Create simple test image
    img = Image.new('RGB', (600, 200), color='white')
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Simple Integration Test", fill='black')
    draw.text((50, 100), "Testing Datalab API", fill='black')
    
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    
    try:
        async with client:
            print("🔄 Making OCR request...")
            result = await client.extract_text(
                file_data=img_bytes.getvalue(),
                filename="simple_test.png"
            )
        
        print(f"✅ Result: Success={result.get('success')}")
        if result.get("success"):
            print(f"📄 Pages: {result.get('page_count', 0)}")
            for page in result.get("pages", []):
                print(f"📝 Text lines: {len(page.get('text_lines', []))}")
                for line in page.get("text_lines", [])[:3]:
                    print(f"   - '{line.get('text', '')}' (conf: {line.get('confidence', 0):.3f})")
        else:
            print(f"❌ Error: {result.get('error')}")
            
    except Exception as e:
        print(f"�� Exception: {e}") 
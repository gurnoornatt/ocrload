#!/usr/bin/env python3
"""
Simple script to test the real Datalab OCR API.

This script creates a test image and sends it to the Datalab API
to validate our implementation works with the real service.

Usage:
    export DATALAB_API_KEY="your_key_here"
    python test_datalab_real.py
"""

import asyncio
import os
import sys
from io import BytesIO

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("❌ PIL/Pillow not found. Install with: pip install Pillow")
    sys.exit(1)

# Add the app directory to the path so we can import our client
sys.path.insert(0, ".")

try:
    from app.services.ocr_clients.datalab_client import DatalabOCRClient
except ImportError as e:
    print(f"❌ Failed to import DatalabOCRClient: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


def create_test_image():
    """Create a simple test image with clear text."""
    # Create a white background image
    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)

    # Try to use a decent font
    try:
        # macOS system font
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 48)
        title_font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 64)
    except:
        try:
            # Alternative macOS font path
            font = ImageFont.truetype("/Library/Fonts/Arial.ttf", 48)
            title_font = ImageFont.truetype("/Library/Fonts/Arial.ttf", 64)
        except:
            # Fallback to default
            font = ImageFont.load_default()
            title_font = font

    # Draw clear, OCR-friendly text
    y_pos = 50

    # Title
    draw.text((50, y_pos), "OCR API TEST", fill="black", font=title_font)
    y_pos += 100

    # Test content
    test_lines = [
        "Datalab OCR Integration Test",
        "Document Processing Service",
        "Text Extraction Validation",
        "Numbers: 1234567890",
        "Date: December 2024",
        "Status: Testing Phase",
    ]

    for line in test_lines:
        draw.text((50, y_pos), line, fill="black", font=font)
        y_pos += 70

    # Convert to bytes
    img_bytes = BytesIO()
    img.save(img_bytes, format="PNG")
    return img_bytes.getvalue()


async def test_real_api():
    """Test the real Datalab API."""
    print("🚀 Testing Real Datalab OCR API")
    print("=" * 50)

    # Check for API key
    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ DATALAB_API_KEY environment variable not set")
        print("Set it with: export DATALAB_API_KEY='your_key_here'")
        return False

    print(f"✅ API Key found: {api_key[:10]}...")

    # Create test image
    print("📸 Creating test image...")
    test_image = create_test_image()
    print(f"✅ Test image created: {len(test_image)} bytes")

    # Initialize client
    print("🔧 Initializing Datalab client...")
    client = DatalabOCRClient(api_key=api_key)

    try:
        async with client:
            print("🔄 Submitting OCR request...")
            result = await client.process_file_content(
                file_content=test_image,
                filename="test_document.png",
                mime_type="image/png",
                languages=["English"],
            )

            print("✅ API Request completed!")
            print(f"Success: {result.get('success', False)}")

            if result.get("success"):
                print(f"📄 Page count: {result.get('page_count', 0)}")
                print(
                    f"🎯 Average confidence: {result.get('average_confidence', 0):.3f}"
                )

                pages = result.get("pages", [])
                for i, page in enumerate(pages):
                    print(f"\n📖 Page {i+1}:")
                    print(f"   Text lines: {len(page.get('text_lines', []))}")
                    print(f"   Confidence: {page.get('average_confidence', 0):.3f}")

                    # Show first few lines of extracted text
                    text_lines = page.get("text_lines", [])
                    for j, line in enumerate(text_lines[:5]):  # First 5 lines
                        text = line.get("text", "").strip()
                        conf = line.get("confidence", 0)
                        if text:
                            print(f"   📝 {j+1}: '{text}' (conf: {conf:.3f})")

                    if len(text_lines) > 5:
                        print(f"   ... and {len(text_lines) - 5} more lines")

                # Show full text
                full_text = result.get("full_text", "").strip()
                if full_text:
                    print("\n📄 Full extracted text:")
                    print("-" * 40)
                    print(full_text[:500])  # First 500 chars
                    if len(full_text) > 500:
                        print(f"\n... and {len(full_text) - 500} more characters")
                    print("-" * 40)

                return True
            else:
                error = result.get("error", "Unknown error")
                print(f"❌ OCR failed: {error}")
                return False

    except Exception as e:
        print(f"💥 Exception occurred: {e}")
        print(f"Exception type: {type(e).__name__}")
        import traceback

        traceback.print_exc()
        return False


async def test_api_structure():
    """Test API structure understanding."""
    print("\n🔍 Testing API Understanding")
    print("=" * 30)

    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ No API key - skipping structure test")
        return

    # Test with minimal image
    img = Image.new("RGB", (200, 100), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 40), "Hello World", fill="black")

    img_bytes = BytesIO()
    img.save(img_bytes, format="PNG")

    client = DatalabOCRClient(api_key=api_key)

    try:
        async with client:
            print("🔄 Testing simple request...")
            result = await client.process_file_content(
                file_content=img_bytes.getvalue(),
                filename="simple.png",
                mime_type="image/png",
            )

            print("📋 Response structure validation:")
            required_fields = ["success", "pages", "page_count"]
            for field in required_fields:
                if field in result:
                    print(f"   ✅ {field}: {type(result[field]).__name__}")
                else:
                    print(f"   ❌ Missing: {field}")

            if result.get("success") and result.get("pages"):
                page = result["pages"][0]
                # Check raw response fields vs our parsed response
                if "page_number" in page:  # Our parsed response
                    page_fields = [
                        "text_lines",
                        "page_number",
                        "image_bbox",
                        "languages",
                        "average_confidence",
                    ]
                else:  # Raw API response
                    page_fields = ["text_lines", "page", "image_bbox", "languages"]
                print("\n   Page structure:")
                for field in page_fields:
                    if field in page:
                        print(f"   ✅ {field}: {type(page[field]).__name__}")
                    else:
                        print(f"   ❌ Missing: {field}")

                if page.get("text_lines"):
                    line = page["text_lines"][0]
                    line_fields = ["text", "confidence", "bbox", "polygon"]
                    print("\n   Text line structure:")
                    for field in line_fields:
                        if field in line:
                            print(f"   ✅ {field}: {type(line[field]).__name__}")
                        else:
                            print(f"   ❌ Missing: {field}")

    except Exception as e:
        print(f"💥 Structure test failed: {e}")


def main():
    """Main function."""
    print("Datalab OCR Real API Test")
    print("========================")

    # Check dependencies
    try:
        import aiohttp

        print("✅ aiohttp available")
    except ImportError:
        print("❌ aiohttp not found. Install with: pip install aiohttp")
        return

    # Run tests
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Test main functionality
        success = loop.run_until_complete(test_real_api())

        if success:
            # Test additional structure understanding
            loop.run_until_complete(test_api_structure())
            print("\n🎉 All tests completed successfully!")
        else:
            print("\n❌ Main test failed")

    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
    finally:
        loop.close()


if __name__ == "__main__":
    main()

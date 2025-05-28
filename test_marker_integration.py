#!/usr/bin/env python3
"""
Real Integration Test for MarkerOCRClient

This script tests our MarkerOCRClient implementation against the real
Marker API to ensure it works correctly as a fallback OCR service.

Usage:
    export DATALAB_API_KEY="your_key"
    python test_marker_integration.py
"""

import asyncio
import os
import sys
from io import BytesIO

# Add project to path
sys.path.insert(0, '.')

try:
    from PIL import Image, ImageDraw
    from app.services.ocr_clients.marker_client import MarkerOCRClient, MarkerOCRError
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)


async def test_marker_client_basic():
    """Test basic MarkerOCRClient functionality."""
    print("🧪 TESTING MARKER OCR CLIENT - BASIC FUNCTIONALITY")
    print("=" * 60)
    
    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ DATALAB_API_KEY not set")
        return False
    
    # Create test document
    img = Image.new('RGB', (600, 400), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "COMMERCIAL DRIVER'S LICENSE", fill='black')
    draw.text((50, 100), "Name: John Smith", fill='black')
    draw.text((50, 130), "License #: D12345678", fill='black')
    draw.text((50, 160), "Expiry: 12/31/2025", fill='black')
    
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    
    async with MarkerOCRClient() as client:
        try:
            print("📝 Processing test image with MarkerOCRClient...")
            
            result = await client.process_file_content(
                file_content=img_bytes.getvalue(),
                filename="test_cdl.png",
                mime_type="image/png",
                languages=["English"]
            )
            
            print("✅ Processing successful!")
            print(f"📊 Result structure: {type(result)}")
            print(f"📄 Pages extracted: {result.get('page_count', 0)}")
            print(f"🎯 Average confidence: {result.get('average_confidence', 0):.2f}")
            print(f"🔧 Extraction method: {result.get('extraction_method')}")
            
            # Validate structure matches OCR format
            expected_fields = ['pages', 'page_count', 'average_confidence', 'success']
            missing_fields = [field for field in expected_fields if field not in result]
            
            if missing_fields:
                print(f"❌ Missing fields: {missing_fields}")
                return False
            
            # Check pages structure
            pages = result.get('pages', [])
            if not pages:
                print("❌ No pages in result")
                return False
            
            page = pages[0]
            page_fields = ['page_number', 'text_lines', 'languages', 'image_bbox']
            missing_page_fields = [field for field in page_fields if field not in page]
            
            if missing_page_fields:
                print(f"❌ Missing page fields: {missing_page_fields}")
                return False
            
            # Check text extraction
            text_lines = page.get('text_lines', [])
            if not text_lines:
                print("❌ No text lines extracted")
                return False
            
            print(f"📝 Text lines extracted: {len(text_lines)}")
            
            # Display extracted text
            print("\n📋 EXTRACTED TEXT:")
            print("-" * 30)
            for i, line in enumerate(text_lines):
                text = line.get('text', '')
                confidence = line.get('confidence', 0)
                print(f"   {i+1}: '{text}' (confidence: {confidence:.2f})")
            
            # Verify we got meaningful text
            all_text = ' '.join(line.get('text', '') for line in text_lines)
            expected_keywords = ['COMMERCIAL', 'LICENSE', 'John Smith', 'D12345678']
            found_keywords = [kw for kw in expected_keywords if kw in all_text]
            
            print(f"\n🔍 Found keywords: {found_keywords}")
            
            if len(found_keywords) >= 2:  # At least 2 keywords found
                print("✅ Text extraction successful!")
                return True
            else:
                print("❌ Text extraction incomplete")
                return False
            
        except MarkerOCRError as e:
            print(f"❌ Marker OCR Error: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return False


async def test_marker_client_error_handling():
    """Test MarkerOCRClient error handling."""
    print("\n\n🚨 TESTING MARKER OCR CLIENT - ERROR HANDLING")
    print("=" * 60)
    
    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ DATALAB_API_KEY not set")
        return False
    
    async with MarkerOCRClient() as client:
        # Test 1: Invalid file content
        print("📝 Test 1: Invalid file content")
        try:
            await client.process_file_content(
                file_content=b"invalid image data",
                filename="invalid.png",
                mime_type="image/png"
            )
            print("❌ Should have failed with invalid content")
            return False
        except MarkerOCRError as e:
            print(f"✅ Correctly caught error: {e}")
        
        # Test 2: Unsupported MIME type
        print("\n📝 Test 2: Unsupported MIME type")
        try:
            await client.process_file_content(
                file_content=b"some content",
                filename="test.xyz",
                mime_type="application/unknown"
            )
            print("❌ Should have failed with unsupported MIME type")
            return False
        except MarkerOCRError as e:
            print(f"✅ Correctly caught error: {e}")
        
        # Test 3: Empty file content
        print("\n📝 Test 3: Empty file content")
        try:
            await client.process_file_content(
                file_content=b"",
                filename="empty.png",
                mime_type="image/png"
            )
            print("❌ Should have failed with empty content")
            return False
        except MarkerOCRError as e:
            print(f"✅ Correctly caught error: {e}")
    
    print("✅ Error handling tests passed!")
    return True


async def test_marker_vs_datalab_comparison():
    """Compare Marker results with Datalab OCR results."""
    print("\n\n🔄 TESTING MARKER vs DATALAB COMPARISON")
    print("=" * 60)
    
    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ DATALAB_API_KEY not set")
        return False
    
    # Create test image
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Hello World", fill='black')
    draw.text((50, 100), "Test Document", fill='black')
    
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    test_content = img_bytes.getvalue()
    
    try:
        # Test with Marker
        print("📄 Processing with Marker API...")
        async with MarkerOCRClient() as marker_client:
            marker_result = await marker_client.process_file_content(
                file_content=test_content,
                filename="comparison_test.png",
                mime_type="image/png"
            )
        
        # Test with Datalab OCR
        print("📄 Processing with Datalab OCR API...")
        from app.services.ocr_clients.datalab_client import DatalabOCRClient
        
        async with DatalabOCRClient() as ocr_client:
            ocr_result = await ocr_client.process_file_content(
                file_content=test_content,
                filename="comparison_test.png",
                mime_type="image/png"
            )
        
        # Compare results
        print("\n📊 COMPARISON RESULTS:")
        print("-" * 40)
        print(f"Marker - Pages: {marker_result.get('page_count')}, Confidence: {marker_result.get('average_confidence', 0):.2f}")
        print(f"OCR    - Pages: {ocr_result.get('page_count')}, Confidence: {ocr_result.get('average_confidence', 0):.2f}")
        
        # Extract text from both
        marker_text = []
        if marker_result.get('pages'):
            for line in marker_result['pages'][0].get('text_lines', []):
                marker_text.append(line.get('text', ''))
        
        ocr_text = []
        if ocr_result.get('pages'):
            for line in ocr_result['pages'][0].get('text_lines', []):
                ocr_text.append(line.get('text', ''))
        
        print(f"\nMarker Text: {' | '.join(marker_text)}")
        print(f"OCR Text:    {' | '.join(ocr_text)}")
        
        print("✅ Comparison completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Comparison test failed: {e}")
        return False


async def main():
    """Run all MarkerOCRClient integration tests."""
    print("🚀 MARKER OCR CLIENT REAL INTEGRATION TESTS")
    print("=" * 70)
    
    results = []
    
    # Test 1: Basic functionality
    result1 = await test_marker_client_basic()
    results.append(result1)
    
    # Test 2: Error handling
    result2 = await test_marker_client_error_handling()
    results.append(result2)
    
    # Test 3: Comparison with Datalab OCR
    result3 = await test_marker_vs_datalab_comparison()
    results.append(result3)
    
    # Summary
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ ALL TESTS PASSED! ({passed}/{total})")
        print("🎉 MarkerOCRClient is ready for use as OCR fallback!")
        return True
    else:
        print(f"❌ SOME TESTS FAILED ({passed}/{total})")
        print("🔧 Need to fix issues before using in production")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 
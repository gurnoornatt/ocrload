#!/usr/bin/env python3
"""
Real Marker API Integration Test

This script tests the Marker API directly to understand its behavior
before implementing our MarkerOCRClient.

Usage:
    export DATALAB_API_KEY="your_key"  # Same key works for all Datalab endpoints
    python test_marker_real.py
"""

import asyncio
import os
import sys
import json
from io import BytesIO
from pathlib import Path

# Add project to path
sys.path.insert(0, '.')

try:
    from PIL import Image, ImageDraw
    import aiohttp
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Install with: pip install Pillow aiohttp")
    sys.exit(1)


async def test_marker_api_direct():
    """Test the Marker API directly to understand its response format."""
    print("🧪 TESTING MARKER API DIRECTLY")
    print("=" * 50)
    
    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ DATALAB_API_KEY not set")
        return
    
    # Create test document with structured content
    img = Image.new('RGB', (600, 400), color='white')
    draw = ImageDraw.Draw(img)
    
    # Add structured content that Marker should handle well
    draw.text((50, 50), "COMMERCIAL DRIVER'S LICENSE", fill='black')
    draw.text((50, 100), "Name: John Smith", fill='black')
    draw.text((50, 130), "License #: D12345678", fill='black')
    draw.text((50, 160), "Expiry: 12/31/2025", fill='black')
    draw.text((50, 200), "Class A - Commercial", fill='black')
    draw.text((50, 250), "Endorsements: H, N, P", fill='black')
    
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    
    async with aiohttp.ClientSession() as session:
        # Test 1: Basic Marker API call
        print("\n📝 Test 1: Basic Marker API Request")
        print("-" * 30)
        
        form_data = aiohttp.FormData()
        form_data.add_field('file', img_bytes.getvalue(), 
                           filename='test_cdl.png', 
                           content_type='image/png')
        form_data.add_field('langs', 'English')
        form_data.add_field('output_format', 'json')  # Get JSON for easier parsing
        form_data.add_field('force_ocr', 'true')  # Force OCR to ensure text extraction
        
        headers = {"X-Api-Key": api_key}
        
        try:
            # Submit request
            async with session.post(
                "https://www.datalab.to/api/v1/marker",
                data=form_data,
                headers=headers
            ) as response:
                if response.status != 200:
                    print(f"❌ Submit failed: {response.status}")
                    text = await response.text()
                    print(f"Error: {text}")
                    return
                
                submit_data = await response.json()
                print(f"✅ Submitted: {submit_data}")
                
                if not submit_data.get('success'):
                    print(f"❌ Submission not successful: {submit_data}")
                    return
                
                # Poll for results
                check_url = submit_data['request_check_url']
                print(f"🔄 Polling: {check_url}")
                
                max_polls = 60  # 2 minutes max
                for i in range(max_polls):
                    await asyncio.sleep(2)
                    
                    async with session.get(check_url, headers=headers) as poll_response:
                        if poll_response.status != 200:
                            print(f"❌ Poll failed: {poll_response.status}")
                            continue
                        
                        poll_data = await poll_response.json()
                        status = poll_data.get('status', 'unknown')
                        print(f"   Poll {i+1}: {status}")
                        
                        if status == 'complete':
                            print("✅ Processing complete!")
                            print("\n📋 RAW MARKER RESPONSE:")
                            print("=" * 40)
                            print(json.dumps(poll_data, indent=2))
                            
                            # Analyze the response structure
                            print("\n🔍 RESPONSE ANALYSIS:")
                            print("=" * 40)
                            print(f"Success: {poll_data.get('success')}")
                            print(f"Output Format: {poll_data.get('output_format')}")
                            print(f"Page Count: {poll_data.get('page_count')}")
                            print(f"Error: {poll_data.get('error', 'None')}")
                            
                            # Check what content we got
                            if 'json' in poll_data:
                                print(f"JSON Content: {type(poll_data['json'])}")
                                if isinstance(poll_data['json'], dict):
                                    print(f"JSON Keys: {list(poll_data['json'].keys())}")
                            
                            if 'markdown' in poll_data:
                                markdown = poll_data['markdown']
                                print(f"Markdown Length: {len(markdown)} chars")
                                print(f"Markdown Preview: {markdown[:200]}...")
                            
                            if 'images' in poll_data:
                                images = poll_data['images']
                                print(f"Images: {len(images)} images")
                            
                            if 'metadata' in poll_data:
                                metadata = poll_data['metadata']
                                print(f"Metadata: {type(metadata)}")
                                if isinstance(metadata, dict):
                                    print(f"Metadata Keys: {list(metadata.keys())}")
                            
                            return poll_data
                        
                        elif status == 'failed' or not poll_data.get('success', True):
                            print(f"❌ Processing failed: {poll_data}")
                            return None
                
                print("⏰ Polling timeout")
                return None
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None


async def test_marker_different_formats():
    """Test different output formats to understand the differences."""
    print("\n\n🎨 TESTING DIFFERENT OUTPUT FORMATS")
    print("=" * 50)
    
    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ DATALAB_API_KEY not set")
        return
    
    # Create simple test content
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Hello World", fill='black')
    draw.text((50, 100), "This is a test", fill='black')
    
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    
    formats = ['markdown', 'json', 'html']
    
    for output_format in formats:
        print(f"\n📄 Testing format: {output_format}")
        print("-" * 30)
        
        async with aiohttp.ClientSession() as session:
            form_data = aiohttp.FormData()
            form_data.add_field('file', img_bytes.getvalue(), 
                               filename=f'test_{output_format}.png', 
                               content_type='image/png')
            form_data.add_field('output_format', output_format)
            form_data.add_field('force_ocr', 'true')
            
            headers = {"X-Api-Key": api_key}
            
            try:
                # Quick test - just submit and check format
                async with session.post(
                    "https://www.datalab.to/api/v1/marker",
                    data=form_data,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        submit_data = await response.json()
                        print(f"✅ Submitted {output_format}: {submit_data.get('success')}")
                    else:
                        print(f"❌ Submit failed for {output_format}: {response.status}")
            
            except Exception as e:
                print(f"❌ Error testing {output_format}: {e}")


async def main():
    """Run all Marker API tests."""
    print("🚀 MARKER API REAL INTEGRATION TESTS")
    print("=" * 60)
    
    # Test 1: Basic API functionality and response structure
    result = await test_marker_api_direct()
    
    # Test 2: Different output formats
    await test_marker_different_formats()
    
    print("\n" + "=" * 60)
    if result:
        print("✅ Marker API tests completed successfully!")
        print("💡 Ready to implement MarkerOCRClient with real understanding of API behavior")
    else:
        print("❌ Marker API tests failed - need to debug before implementation")


if __name__ == "__main__":
    asyncio.run(main()) 
#!/usr/bin/env python3
"""
Debug script to see the raw Datalab API response.
"""

import asyncio
import os
import sys
import json
from io import BytesIO

sys.path.insert(0, '.')

from PIL import Image, ImageDraw
from app.services.ocr_clients.datalab_client import DatalabOCRClient


async def debug_raw_response():
    """Debug the raw API response to understand the structure."""
    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ DATALAB_API_KEY not set")
        return
    
    # Create simple test image
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Hello World", fill='black')
    draw.text((50, 100), "Test 123", fill='black')
    
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    
    client = DatalabOCRClient(api_key=api_key)
    
    try:
        async with client:
            # Let's modify the client to show us the raw response
            file_content = img_bytes.getvalue()
            
            # Submit request
            print("🔄 Submitting request...")
            response = await client._submit_ocr_request(
                file_content=file_content,
                filename="debug.png",
                mime_type="image/png"
            )
            
            print("📋 Submit response:")
            print(json.dumps(response, indent=2))
            
            # Poll for results  
            check_url = response.get('request_check_url')
            if check_url:
                print(f"\n🔄 Polling {check_url}...")
                final_response = await client._poll_for_results(check_url)
                
                print("\n📋 Final raw response:")
                print(json.dumps(final_response, indent=2))
                
                # Show our parsed version
                print("\n📋 Our parsed response:")
                parsed = client._parse_ocr_results(final_response)
                print(json.dumps(parsed, indent=2))
    
    except Exception as e:
        print(f"💥 Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_raw_response()) 
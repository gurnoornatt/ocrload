#!/usr/bin/env python3
"""
Test Datalab API Connection

Quick test to verify:
1. DATALAB_API_KEY is loaded from .env
2. API connection works
3. Marker API responds correctly
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.ocr_clients.datalab_marker_client import DatalabMarkerClient

async def test_api_connection():
    """Test the Datalab API connection."""
    
    print("🔑 DATALAB API CONNECTION TEST")
    print("=" * 50)
    
    # Check if API key is loaded
    api_key = os.getenv("DATALAB_API_KEY")
    if api_key:
        print(f"✅ DATALAB_API_KEY found: {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else '***'}")
    else:
        print("❌ DATALAB_API_KEY not found in environment")
        return
    
    # Test with a small document
    test_dir = Path("test_documents")
    
    # Find any test image
    test_image = None
    for doc_type in ["bol", "lumper", "invoice"]:
        type_dir = test_dir / doc_type
        if type_dir.exists():
            images = list(type_dir.glob("*.jpg"))
            if images:
                test_image = images[0]
                break
    
    if not test_image:
        print("❌ No test images found in test_documents/")
        return
    
    print(f"📄 Testing with: {test_image.name}")
    print(f"📦 File size: {test_image.stat().st_size:,} bytes")
    
    try:
        # Read test image
        with open(test_image, "rb") as f:
            file_content = f.read()
        
        # Test Marker API connection
        async with DatalabMarkerClient() as client:
            print("\n🔄 Testing Marker API connection...")
            
            result = await client.process_document(
                file_content=file_content,
                filename=test_image.name,
                mime_type="image/jpeg",
                language="English",
                force_ocr=True,
                use_llm=True,
                output_format="markdown"
            )
            
            if result.success:
                print("✅ Marker API connection successful!")
                print(f"   Content length: {result.content_length:,} chars")
                print(f"   Processing time: {result.processing_time:.2f}s")
                print(f"   Tables detected: {len(result.get_tables())}")
                print(f"   Sections found: {len(result.get_sections())}")
                
                # Show first few lines of markdown
                if result.markdown_content:
                    print(f"\n📝 Sample output (first 5 lines):")
                    lines = result.markdown_content.split('\n')[:5]
                    for i, line in enumerate(lines):
                        if line.strip():
                            print(f"   {i+1}: {line[:80]}...")
                
                print(f"\n🎉 DATALAB MARKER API WORKING PERFECTLY!")
                print(f"🚀 Ready for enhanced workflow deployment!")
                
            else:
                print(f"❌ Marker API failed: {result.error}")
                
                if "403" in result.error or "authentication" in result.error.lower():
                    print("\n🔧 TROUBLESHOOTING TIPS:")
                    print("   1. Verify your DATALAB_API_KEY is correct")
                    print("   2. Check if the key has proper permissions")
                    print("   3. Ensure your account has Marker API access")
                elif "404" in result.error:
                    print("\n🔧 TROUBLESHOOTING: API endpoint might have changed")
                elif "429" in result.error:
                    print("\n🔧 TROUBLESHOOTING: Rate limit hit - wait and retry")
                else:
                    print(f"\n🔧 TROUBLESHOOTING: Unexpected error - {result.error}")
    
    except Exception as e:
        print(f"💥 Connection test failed: {e}")

async def main():
    """Run the API connection test."""
    await test_api_connection()

if __name__ == "__main__":
    asyncio.run(main()) 
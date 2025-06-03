#!/usr/bin/env python3
"""
Debug Sonnet 3.5 API Connection

Quick test to verify:
1. ANTHROPIC_API_KEY is loaded
2. Sonnet 3.5 responds to a simple request
3. Response format is correct
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent / "app"))

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

async def test_sonnet_connection():
    """Test Sonnet 3.5 API connection."""
    
    print("🤖 SONNET 3.5 API CONNECTION TEST")
    print("=" * 50)
    
    # Check if API key is loaded
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if api_key:
        print(f"✅ ANTHROPIC_API_KEY found: {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else '***'}")
    else:
        print("❌ ANTHROPIC_API_KEY not found in environment")
        return
    
    if not ANTHROPIC_AVAILABLE:
        print("❌ Anthropic package not available")
        return
    
    try:
        # Initialize client
        client = anthropic.Anthropic(api_key=api_key)
        print("✅ Anthropic client initialized")
        
        # Test simple request
        print("\n🔄 Testing simple API call...")
        
        simple_prompt = """Extract BOL data from this test content:

BOL Number: TEST123
Shipper: ABC Company
Consignee: XYZ Corp

Return JSON format:
{"bol_number": "TEST123", "shipper_name": "ABC Company", "consignee_name": "XYZ Corp", "confidence_score": 0.9}"""

        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            temperature=0.1,
            messages=[{
                "role": "user",
                "content": simple_prompt
            }]
        )
        
        # Check response
        response_content = response.content[0].text
        print(f"✅ Sonnet 3.5 response received ({len(response_content)} chars)")
        print(f"📝 Raw response:\n{response_content}")
        
        # Try to parse as JSON
        import json
        try:
            parsed = json.loads(response_content)
            print(f"✅ JSON parsing successful: {parsed}")
            print(f"🎉 SONNET 3.5 API WORKING PERFECTLY!")
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing failed: {e}")
            print(f"🔧 Response might not be pure JSON")
            
            # Check if response contains JSON
            if '{' in response_content and '}' in response_content:
                print("🔍 Trying to extract JSON from response...")
                start = response_content.find('{')
                end = response_content.rfind('}') + 1
                json_part = response_content[start:end]
                try:
                    parsed = json.loads(json_part)
                    print(f"✅ Extracted JSON: {parsed}")
                except:
                    print(f"❌ Could not extract valid JSON")
    
    except Exception as e:
        print(f"💥 Sonnet API test failed: {e}")

async def main():
    """Run the API connection test."""
    await test_sonnet_connection()

if __name__ == "__main__":
    asyncio.run(main()) 
#!/usr/bin/env python3
"""
Debug Lumper2 Sonnet Response

Shows exactly what Sonnet 3.5 returns for lumper2 processing
to understand why JSON parsing is failing.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Configure logging to show responses
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.enhanced_lumper_extractor import EnhancedLumperExtractor
from app.services.ocr_clients.datalab_marker_client import DatalabMarkerClient


async def debug_lumper2_response():
    """Debug the exact response from Sonnet 3.5 for lumper2."""
    
    print("🔍 LUMPER2 SONNET RESPONSE DEBUG")
    print("="*60)
    
    # Find lumper2 document
    lumper_file = Path("test_documents/lumper/lumper2.webp")
    if not lumper_file.exists():
        print(f"❌ File not found: {lumper_file}")
        return
    
    print(f"📁 File: {lumper_file.name}")
    
    # Read document
    with open(lumper_file, 'rb') as f:
        file_content = f.read()
    print(f"📂 Size: {len(file_content):,} bytes\n")
    
    # Process with Marker API
    print("🟢 PROCESSING WITH MARKER API...")
    async with DatalabMarkerClient() as marker:
        marker_result = await marker.process_document(
            file_content=file_content,
            filename=lumper_file.name,
            mime_type="image/webp",
            language="English",
            force_ocr=True,
            use_llm=True,  # Enhanced processing
            output_format="markdown"
        )
    
    if not marker_result.success:
        print(f"❌ Marker API failed: {marker_result.error}")
        return
    
    print(f"✅ Marker API success: {len(marker_result.markdown_content)} chars")
    print(f"📋 Content preview:\n{marker_result.markdown_content[:500]}...\n")
    
    # Now test Sonnet 3.5 extraction
    print("🤖 TESTING SONNET 3.5 EXTRACTION...")
    extractor = EnhancedLumperExtractor()
    
    # Temporarily modify the extractor to log raw responses
    original_method = extractor.extract_fields_from_markdown
    
    async def debug_extract_fields_from_markdown(markdown_content, marker_metadata=None, model="claude-3-5-sonnet-20241022"):
        """Debug version that shows raw responses."""
        if not extractor.anthropic_client:
            print("❌ Anthropic client not available")
            return {}, 0.0
        
        try:
            system_prompt = """You are an expert lumper receipt data extraction specialist working with structured markdown input.

Extract lumper receipt data with high accuracy. Focus on:

CORE IDENTIFIERS:
- Receipt numbers: Look for "Receipt", "Receipt #", "Transaction", "Trans#"
- Facility names: Company names, warehouses, distribution centers
- Driver information: Driver names, signatures

FINANCIAL DATA:
- Total amounts: "Total", "Amount Due", "Balance", "Charge"
- Service dates: Any dates on the receipt
- Hours worked: Time spans, duration

LOGISTICS:
- Trailer numbers: "Trailer", "Unit", "Equipment"
- Carrier information: Transportation companies
- PO numbers: Purchase order references

Return a JSON object with exact field names specified."""

            user_prompt = f"""Extract all lumper receipt data from this structured markdown content:

{markdown_content}

Return valid JSON with these exact fields:
- receipt_number, facility_name, driver_name, total_amount, service_date
- trailer_number, carrier_name, po_number, start_time, end_time, hours_worked
- confidence_score (0.0-1.0), validation_flags (array)

IMPORTANT: 
- total_amount must be a number (e.g., 150.00, not "$150")
- hours_worked must be a number (e.g., 3.5, not "3.5 hours")
- If you cannot determine a numeric value, use null"""
            
            print(f"📤 SENDING TO SONNET 3.5:")
            print(f"   Content length: {len(markdown_content)} chars")
            print(f"   Prompt length: {len(user_prompt)} chars\n")
            
            # Make the API call (Note: lumper extractor uses sync client)
            response = extractor.anthropic_client.messages.create(
                model=model,
                max_tokens=4000,
                temperature=0.1,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": user_prompt
                }]
            )
            
            # Extract response
            response_content = response.content[0].text
            
            print(f"📥 RAW SONNET RESPONSE:")
            print(f"   Length: {len(response_content)} chars")
            print(f"   Full response:\n{'-'*40}")
            print(response_content)
            print(f"{'-'*40}\n")
            
            # Show where JSON parsing would fail
            print(f"🔍 JSON PARSING ANALYSIS:")
            if '```json' in response_content:
                print("   Found ```json code block")
                start = response_content.find('```json') + 7
                end = response_content.find('```', start)
                if end != -1:
                    json_part = response_content[start:end].strip()
                    print(f"   Extracted JSON part ({len(json_part)} chars):")
                    print(f"   {json_part[:200]}...")
                else:
                    print("   ❌ No closing ``` found")
            elif '{' in response_content:
                print("   Found JSON object without code blocks")
                start = response_content.find('{')
                end = response_content.rfind('}') + 1
                json_part = response_content[start:end]
                print(f"   JSON part ({len(json_part)} chars):")
                print(f"   {json_part[:200]}...")
            else:
                print("   ❌ No JSON structure found")
            
            return {}, 0.0
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {}, 0.0
    
    # Replace the method temporarily
    extractor.extract_fields_from_markdown = debug_extract_fields_from_markdown
    
    # Run extraction
    await extractor.extract_fields_from_markdown(marker_result.markdown_content)


if __name__ == "__main__":
    asyncio.run(debug_lumper2_response()) 
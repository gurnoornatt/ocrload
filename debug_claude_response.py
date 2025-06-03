#!/usr/bin/env python3

import asyncio
import json
from pathlib import Path
from app.services.enhanced_delivery_extractor import EnhancedDeliveryExtractor

async def debug_claude():
    print("Debugging Claude response for delivery document...")
    
    extractor = EnhancedDeliveryExtractor()
    
    # Try with a packing list instead
    test_file = 'test_documents/packing_list/Packing_List1.png'
    if not Path(test_file).exists():
        test_file = 'test_documents/delivery_note/POD2.png'
    
    print(f"Testing with: {test_file}")
    
    with open(test_file, 'rb') as f:
        content = f.read()
    
    # Process with Marker API
    async with extractor.marker_client as marker:
        marker_result = await marker.process_document(
            file_content=content,
            filename=Path(test_file).name,
            mime_type='image/png',
            language="English",
            force_ocr=True,
            use_llm=False,
            output_format="markdown"
        )
    
    if marker_result.success:
        print(f"✅ Marker successful: {len(marker_result.markdown_content)} chars")
        
        # Save the full markdown to a file
        with open('debug_delivery_markdown.txt', 'w') as f:
            f.write(marker_result.markdown_content)
        print(f"📄 Full markdown saved to debug_delivery_markdown.txt")
        
        # Show more of the content
        print("📄 First 1000 chars of markdown:")
        print(repr(marker_result.markdown_content[:1000]))
        print("\n" + "="*50 + "\n")
        
        # Count meaningful content
        lines = marker_result.markdown_content.split('\n')
        non_empty_lines = [line.strip() for line in lines if line.strip() and line.strip() != '|']
        print(f"📊 Total lines: {len(lines)}, Non-empty lines: {len(non_empty_lines)}")
        
        if non_empty_lines:
            print("📝 First 10 non-empty lines:")
            for i, line in enumerate(non_empty_lines[:10]):
                print(f"  {i+1}: {line}")
        
        print("\n" + "="*50 + "\n")
        
        # Now test Claude extraction with the better prompt
        try:
            system_prompt = """You are an expert delivery note and packing list data extraction specialist working with structured markdown input.

Extract ALL relevant information from the document. Be extremely flexible with field names and data interpretation. 

CRITICAL: Focus on data completeness - extract every piece of useful information you can find, even if it doesn't fit perfectly into the expected fields."""

            user_prompt = f"""Extract delivery and packing list data from this markdown:

{marker_result.markdown_content}

Return valid JSON with all the information you can extract. Fill as many fields as possible with actual data from the document.

Return ONLY the JSON object with fields like:
- document_number, document_type, document_date
- shipper_name, consignee_name, carrier_name
- driver_name, bol_number, pro_number, po_number
- items array with item details
- delivery information
- any other relevant data you find

Be creative but accurate - extract maximum data!"""
            
            response = extractor.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                temperature=0.1,
                system=system_prompt,
                messages=[{
                    "role": "user", 
                    "content": user_prompt
                }]
            )
            
            raw_response = response.content[0].text
            print("🤖 Claude's raw response:")
            print(raw_response)
            
            # Try parsing
            try:
                if '```json' in raw_response:
                    start = raw_response.find('```json') + 7
                    end = raw_response.find('```', start)
                    json_content = raw_response[start:end].strip()
                else:
                    json_content = raw_response
                
                parsed = json.loads(json_content)
                print(f"\n✅ Successfully parsed JSON!")
                
                # Show extracted data
                print("\n📋 Extracted fields:")
                for key, value in parsed.items():
                    if isinstance(value, list):
                        print(f"  {key}: {len(value)} items")
                        if value:
                            print(f"    First item: {value[0]}")
                    else:
                        print(f"  {key}: {value}")
                
            except Exception as e:
                print(f"\n❌ JSON parsing failed: {e}")
                print("Raw response:")
                print(repr(raw_response[:200]))
        
        except Exception as e:
            print(f"❌ Claude API call failed: {e}")
    
    else:
        print(f"❌ Marker failed: {marker_result.error}")

if __name__ == "__main__":
    asyncio.run(debug_claude()) 
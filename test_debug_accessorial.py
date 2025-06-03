#!/usr/bin/env python3
"""
Debug Accessorial Extraction - Show Raw Data Flow

This test shows exactly what's happening in the extraction pipeline:
1. Raw file → Marker API → markdown content
2. Markdown → Claude → JSON response 
3. JSON → ExtractedAccessorialData → database format

Shows where data is being lost.
"""

import asyncio
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import what we need
from app.services.enhanced_accessorial_extractor import EnhancedAccessorialExtractor

async def debug_accessorial_extraction():
    """Debug the extraction pipeline step by step."""
    print("🔍 DEBUGGING ACCESSORIAL EXTRACTION PIPELINE")
    print("=" * 70)
    
    # Check API keys
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")):
        print("❌ No Claude API key found!")
        return
    
    if not os.getenv("DATALAB_API_KEY"):
        print("❌ No Datalab API key found!")
        return
    
    print("✅ API keys found")
    
    # Initialize extractor
    extractor = EnhancedAccessorialExtractor()
    
    # Pick one test document to debug
    test_file = Path("test_documents/accessorial/loadslip1.png")
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return
    
    print(f"🧪 DEBUGGING: {test_file.name}")
    
    # Read file
    with open(test_file, "rb") as f:
        file_content = f.read()
    
    print(f"📄 File size: {len(file_content):,} bytes")
    
    try:
        # STEP 1: Get raw markdown from Marker API
        print("\n" + "="*50)
        print("STEP 1: MARKER API - RAW MARKDOWN EXTRACTION")
        print("="*50)
        
        async with extractor.marker_client as marker:
            marker_result = await marker.process_document(
                file_content=file_content,
                filename=test_file.name,
                mime_type="image/png",
                language="English",
                force_ocr=True,
                use_llm=False,
                output_format="markdown"
            )
        
        if not marker_result.success:
            print(f"❌ Marker API failed: {marker_result.error}")
            return
        
        print(f"✅ Marker API success")
        print(f"📊 Content length: {marker_result.content_length:,} characters")
        print(f"📊 Tables detected: {len(marker_result.get_tables())}")
        
        print("\n📄 RAW MARKDOWN CONTENT (first 1000 chars):")
        print("-" * 50)
        print(marker_result.markdown_content[:1000])
        print("-" * 50)
        
        if len(marker_result.markdown_content) > 1000:
            print("... (truncated for display)")
        
        # Save full markdown for debugging
        with open("debug_markdown.txt", "w") as f:
            f.write(marker_result.markdown_content)
        print("💾 Full markdown saved to debug_markdown.txt")
        
        # STEP 2: Claude extraction from markdown
        print("\n" + "="*50)
        print("STEP 2: CLAUDE AI - SEMANTIC EXTRACTION")
        print("="*50)
        
        extracted_dict, ai_confidence = await extractor.extract_fields_from_markdown(
            markdown_content=marker_result.markdown_content,
            marker_metadata=marker_result.metadata
        )
        
        print(f"✅ Claude extraction completed")
        print(f"📊 AI Confidence: {ai_confidence:.3f}")
        print(f"📊 Fields returned: {len(extracted_dict)}")
        
        print("\n📄 RAW CLAUDE RESPONSE:")
        print("-" * 50)
        print(json.dumps(extracted_dict, indent=2, default=str))
        print("-" * 50)
        
        # Save raw Claude response for debugging
        with open("debug_claude_response.json", "w") as f:
            json.dump(extracted_dict, f, indent=2, default=str)
        print("💾 Claude response saved to debug_claude_response.json")
        
        # STEP 3: Data cleaning and validation
        print("\n" + "="*50)
        print("STEP 3: DATA CLEANING & VALIDATION")
        print("="*50)
        
        # Show what happens during data cleaning
        print("🧹 Before cleaning:")
        for key, value in extracted_dict.items():
            print(f"  {key}: {value} ({type(value).__name__})")
        
        # Now run the full extraction to see the final result
        extracted_data, final_confidence, needs_review = await extractor.extract_accessorial_fields_enhanced(
            file_content=file_content,
            filename=test_file.name,
            mime_type="image/png"
        )
        
        print(f"\n🧹 After cleaning and validation:")
        print(f"📊 Final Confidence: {final_confidence:.3f}")
        print(f"📊 Needs Review: {needs_review}")
        print(f"📊 Validation Flags: {extracted_data.validation_flags}")
        
        print("\n📄 FINAL EXTRACTED DATA:")
        print("-" * 50)
        data_dict = extracted_data.dict()
        for key, value in data_dict.items():
            if value is not None and value != [] and value != "":
                print(f"  ✅ {key}: {value}")
            else:
                print(f"  ❌ {key}: {value}")
        print("-" * 50)
        
        # STEP 4: Database format conversion
        print("\n" + "="*50)
        print("STEP 4: DATABASE FORMAT CONVERSION")
        print("="*50)
        
        from app.services.document_parsers.enhanced_accessorial_parser import EnhancedAccessorialParser
        parser = EnhancedAccessorialParser()
        
        db_format = parser._convert_to_accessorial_charges_format(extracted_data, "test-doc-id")
        
        print("📄 DATABASE FORMAT:")
        print("-" * 50)
        for key, value in db_format.items():
            if value is not None and value != {} and value != []:
                print(f"  ✅ {key}: {value}")
            else:
                print(f"  ❌ {key}: {value}")
        print("-" * 50)
        
        # Save final database format
        with open("debug_database_format.json", "w") as f:
            json.dump(db_format, f, indent=2, default=str)
        print("💾 Database format saved to debug_database_format.json")
        
        # SUMMARY
        print("\n" + "="*50)
        print("🎯 DEBUGGING SUMMARY")
        print("="*50)
        
        print(f"1. ✅ Marker API: {marker_result.content_length:,} chars extracted")
        print(f"2. ✅ Claude AI: {len(extracted_dict)} fields returned, {ai_confidence:.1%} confidence")
        print(f"3. ✅ Data Cleaning: {final_confidence:.1%} final confidence")
        print(f"4. ✅ Database Format: {len([k for k,v in db_format.items() if v is not None])} fields mapped")
        
        # Identify specific issues
        print(f"\n🔍 IDENTIFIED ISSUES:")
        if not extracted_dict.get('total_charges'):
            print("❌ total_charges not extracted from Claude")
        if not extracted_dict.get('rate_per_hour') and not extracted_dict.get('rate_flat'):
            print("❌ No rate information extracted")
        if not extracted_dict.get('bol_number'):
            print("❌ BOL number not extracted")
        if not extracted_dict.get('document_number'):
            print("❌ Document number not extracted")
        
        print(f"\n📁 Debug files created:")
        print(f"  - debug_markdown.txt (raw Marker output)")
        print(f"  - debug_claude_response.json (raw Claude output)")
        print(f"  - debug_database_format.json (final database format)")
        
    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_accessorial_extraction()) 
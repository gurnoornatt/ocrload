#!/usr/bin/env python3

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client
import os

# Load environment
load_dotenv()

# Import what we need
from app.services.enhanced_delivery_extractor import EnhancedDeliveryExtractor

async def test_single_with_db():
    print("🚚 Testing single delivery document with database storage...")
    
    # Initialize Supabase
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")  # Use service key
    
    if not (supabase_url and supabase_key):
        print("❌ Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    
    # Initialize extractor
    extractor = EnhancedDeliveryExtractor()
    
    # Test with POD2.png (we know this has good data)
    test_file = 'test_documents/delivery_note/POD2.png'
    print(f"📄 Processing: {test_file}")
    
    with open(test_file, 'rb') as f:
        content = f.read()
    
    # Extract data
    result = await extractor.extract_delivery_fields_enhanced(content, 'POD2.png')
    data, confidence, needs_review = result
    
    print(f"📊 Extraction Results:")
    print(f"   Document Type: {data.document_type}")
    print(f"   Confidence: {confidence:.1%}")
    print(f"   Document Number: {data.document_number}")
    print(f"   Shipper: {data.shipper_name}")
    print(f"   Consignee: {data.consignee_name}")
    print(f"   Driver: {data.driver_name}")
    print(f"   BOL Number: {data.bol_number}")
    print(f"   Items Count: {len(data.items)}")
    if data.items:
        print("   📦 Items:")
        for i, item in enumerate(data.items):
            print(f"      {i+1}. {item.item_description} (Qty: {item.quantity})")
    
    # Create document record manually with ALL the rich data
    document_id = str(uuid.uuid4())
    
    # Convert ExtractedDeliveryData to dictionary 
    extracted_data_dict = data.model_dump()
    
    doc_record = {
        "id": document_id,
        "type": "POD",  # Map document type to enum
        "status": "parsed",
        "confidence": confidence,
        "raw_ocr_data": {"raw_markdown": "Sample markdown"},
        "parsed_data": {
            # ALL the extracted fields
            **extracted_data_dict,
            # Plus metadata
            "extraction_method": "enhanced_marker_sonnet",
            "raw_markdown_length": 0,
            "extraction_timestamp": datetime.utcnow().isoformat()
        }
    }
    
    print(f"\n💾 Storing document in database...")
    print(f"   Document ID: {document_id}")
    print(f"   Parsed data fields: {len(extracted_data_dict)}")
    
    try:
        # Insert document
        doc_response = supabase.table("documents").insert(doc_record).execute()
        print(f"✅ Document stored successfully")
        
        # Verify data was stored
        query_response = supabase.table("documents").select(
            "id, type, confidence, parsed_data->>'document_number' as doc_num, parsed_data->>'shipper_name' as shipper"
        ).eq("id", document_id).execute()
        
        if query_response.data:
            stored_doc = query_response.data[0]
            print(f"✅ Verification successful:")
            print(f"   Stored Doc Number: {stored_doc.get('doc_num')}")
            print(f"   Stored Shipper: {stored_doc.get('shipper')}")
        
    except Exception as e:
        print(f"❌ Database storage failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_single_with_db()) 
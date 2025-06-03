#!/usr/bin/env python3

import asyncio
import json
import uuid
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Load environment
load_dotenv()

# Import what we need
from app.services.enhanced_delivery_extractor import EnhancedDeliveryExtractor

async def process_all_delivery_documents():
    print("🚚 Processing ALL Delivery Documents with Enhanced Extraction")
    print("=" * 60)
    
    # Initialize Supabase
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")  # Use service key
    
    if not (supabase_url and supabase_key):
        print("❌ Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    
    # Initialize extractor
    extractor = EnhancedDeliveryExtractor()
    
    # Define all test documents with correct names
    test_documents = [
        # Delivery Notes (PODs)
        "test_documents/delivery_note/POD1.jpeg",
        "test_documents/delivery_note/POD2.png", 
        "test_documents/delivery_note/POD3.png",
        
        # Packing Lists
        "test_documents/packing_list/PL1.png",
        "test_documents/packing_list/PL2.png"
    ]
    
    successful_extractions = 0
    total_documents = 0
    
    for doc_path in test_documents:
        if not Path(doc_path).exists():
            print(f"⚠️  Skipping missing file: {doc_path}")
            continue
            
        total_documents += 1
        doc_name = Path(doc_path).name
        print(f"\n📄 Processing: {doc_name}")
        
        try:
            # Read file content
            with open(doc_path, 'rb') as f:
                content = f.read()
            
            # Extract data using enhanced extractor
            result = await extractor.extract_delivery_fields_enhanced(content, doc_name)
            data, confidence, needs_review = result
            
            print(f"   📊 Extraction Results:")
            print(f"      Type: {data.document_type}")
            print(f"      Confidence: {confidence:.1%}")
            print(f"      Document #: {data.document_number}")
            print(f"      Shipper: {data.shipper_name}")
            print(f"      Consignee: {data.consignee_name}")
            print(f"      Driver: {data.driver_name}")
            print(f"      BOL: {data.bol_number}")
            print(f"      Items: {len(data.items)}")
            
            if data.items:
                print(f"      📦 First 2 Items:")
                for i, item in enumerate(data.items[:2]):
                    print(f"         {i+1}. {item.item_description} (Qty: {item.quantity})")
            
            # Store in database
            document_id = str(uuid.uuid4())
            
            # Map document type for database
            doc_type_mapping = {
                'delivery_note': 'DELIVERY_NOTE',
                'packing_list': 'PACKING_LIST', 
                'pod': 'POD'
            }
            db_doc_type = doc_type_mapping.get(data.document_type, 'POD')
            
            # Convert ExtractedDeliveryData to dictionary 
            extracted_data_dict = data.model_dump()
            
            # Create comprehensive document record
            doc_record = {
                "id": document_id,
                "type": db_doc_type,
                "status": "parsed",
                "confidence": confidence,
                "raw_ocr_data": {"raw_markdown": "Enhanced marker extraction"},
                "parsed_data": {
                    # ALL the extracted fields
                    **extracted_data_dict,
                    # Plus metadata
                    "extraction_method": "enhanced_marker_sonnet",
                    "file_name": doc_name,
                    "extraction_timestamp": datetime.utcnow().isoformat(),
                    "needs_review": needs_review
                }
            }
            
            # Insert document into Supabase
            doc_response = supabase.table("documents").insert(doc_record).execute()
            
            if doc_response.data:
                successful_extractions += 1
                print(f"   ✅ Stored in database successfully")
            else:
                print(f"   ❌ Database storage failed")
                
        except Exception as e:
            print(f"   ❌ Processing failed: {e}")
    
    print(f"\n🎯 Final Results:")
    print(f"   Documents processed: {total_documents}")
    print(f"   Successful extractions: {successful_extractions}")
    print(f"   Success rate: {successful_extractions/total_documents*100:.1f}%")
    
    # Show final database summary
    print(f"\n📊 Database Summary - Recent Delivery Documents:")
    
    query_response = supabase.table("documents").select(
        """
        id, type, confidence, created_at,
        parsed_data->>'document_number' as doc_number,
        parsed_data->>'shipper_name' as shipper,
        parsed_data->>'consignee_name' as consignee,
        parsed_data->>'driver_name' as driver,
        parsed_data->>'file_name' as file_name,
        (parsed_data->>'total_pieces')::text as pieces,
        jsonb_array_length(COALESCE(parsed_data->'items', '[]'::jsonb)) as item_count
        """
    ).in_("type", ["DELIVERY_NOTE", "PACKING_LIST", "POD"]).order("created_at", desc=True).limit(10).execute()
    
    if query_response.data:
        for doc in query_response.data:
            file_name = doc.get('file_name') or 'Unknown'
            print(f"   📄 {file_name} ({doc['type']}):")
            print(f"      Confidence: {doc['confidence']:.1%}")
            print(f"      Doc #: {doc['doc_number']}")
            print(f"      {doc['shipper']} → {doc['consignee']}")
            print(f"      Driver: {doc['driver']}, Items: {doc['item_count']}, Pieces: {doc['pieces']}")

if __name__ == "__main__":
    asyncio.run(process_all_delivery_documents()) 
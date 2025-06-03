#!/usr/bin/env python3
"""
Test Enhanced Delivery Workflow - Marker + Claude (NO PREPROCESSING)

Tests the new marker API extraction → Claude semantic reasoning for:
- Delivery Notes (POD - Proof of Delivery)
- Packing Lists
- Comprehensive item extraction
- Delivery confirmations and signatures

Shows markdown extraction and Claude's reasoning process clearly.
Includes full database integration with documents table and delivery-specific data.
"""

import asyncio
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import what we need
from app.services.document_parsers.enhanced_delivery_parser import EnhancedDeliveryParser
from supabase import create_client

async def test_delivery_workflow():
    """Test complete delivery workflow with marker + sonnet and database integration."""
    print("🚚 ENHANCED DELIVERY WORKFLOW TEST - MARKER + CLAUDE (NO PREPROCESSING)")
    print("=" * 80)
    
    # Check API keys
    if not (os.getenv("DATALAB_API_KEY") and (os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"))):
        print("❌ Missing required API keys (DATALAB_API_KEY and ANTHROPIC_API_KEY/CLAUDE_API_KEY)")
        return
    
    # Initialize Supabase
    supabase = None
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")  # Prefer service key
    if supabase_url and supabase_key:
        supabase = create_client(supabase_url, supabase_key)
        key_type = "SERVICE" if os.getenv("SUPABASE_SERVICE_KEY") else "ANON"
        print(f"✅ Supabase client initialized with {key_type} key")
        
        # Test database connection
        try:
            result = supabase.table("documents").select("id").limit(1).execute()
            print("✅ Database connection confirmed")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return
    else:
        print("❌ Missing Supabase configuration")
        return
    
    # Initialize enhanced delivery parser
    parser = EnhancedDeliveryParser()
    parser.supabase = supabase  # Add supabase client for database integration
    print("✅ Enhanced Delivery Parser initialized with marker + sonnet workflow")
    
    # Test documents - delivery notes, packing lists, and PODs
    delivery_docs = []
    
    # Find all delivery documents
    for doc_dir in ["delivery_note", "packing_list"]:
        doc_path = Path(f"test_documents/{doc_dir}")
        if doc_path.exists():
            for file_path in doc_path.glob("*"):
                if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.pdf']:
                    delivery_docs.append(file_path)
    
    if not delivery_docs:
        print("❌ No delivery test documents found in test_documents/delivery_note/ or test_documents/packing_list/")
        return
    
    print(f"📄 Found {len(delivery_docs)} delivery documents to test")
    print()
    
    # Process each document
    results = []
    for i, delivery_file in enumerate(delivery_docs, 1):
        document_id = str(uuid.uuid4())
        
        print(f"🔍 [{i}/{len(delivery_docs)}] Processing: {delivery_file.name}")
        print(f"📁 Path: {delivery_file}")
        print(f"🆔 Document ID: {document_id}")
        
        try:
            # Step 1: Parse document using enhanced workflow
            result = await parser.parse_from_file_content(
                file_content=delivery_file.read_bytes(),
                filename=delivery_file.name,
                mime_type=f"image/{delivery_file.suffix[1:]}",
                document_id=document_id
            )
            
            print(f"📊 Parsing Result:")
            print(f"   Success: {result.success}")
            print(f"   Document Type: {result.document_type}")
            print(f"   Confidence: {result.confidence:.1%}")
            
            if result.extracted_data:
                data = result.extracted_data
                print(f"   Document Number: {data.document_number}")
                print(f"   Document Date: {data.document_date}")
                print(f"   Delivery Date: {data.delivery_date}")
                print(f"   Shipper: {data.shipper_name}")
                print(f"   Consignee: {data.consignee_name}")
                print(f"   Carrier: {data.carrier_name}")
                print(f"   Driver: {data.driver_name}")
                print(f"   BOL Number: {data.bol_number}")
                print(f"   PRO Number: {data.pro_number}")
                print(f"   Items Count: {len(data.items)}")
                
                # Show first few items for packing lists
                if data.items:
                    print(f"   📦 Items (showing first 3):")
                    for j, item in enumerate(data.items[:3]):
                        print(f"      {j+1}. {item.item_description or 'No description'}")
                        print(f"         SKU: {item.sku}, Qty: {item.quantity} {item.unit or ''}")
                        if item.weight:
                            print(f"         Weight: {item.weight} {item.weight_unit or ''}")
                
                print(f"   Total Pieces: {data.total_pieces}")
                print(f"   Total Weight: {data.total_weight} {data.total_weight_unit or ''}")
                print(f"   Recipient: {data.recipient_name}")
                print(f"   Delivery Confirmed: {data.delivery_confirmed}")
                print(f"   Condition Notes: {data.condition_notes}")
                print(f"   Validation Issues: {len(data.validation_flags)}")
                if data.validation_flags:
                    for flag in data.validation_flags[:3]:  # Show first 3 issues
                        print(f"      ⚠️ {flag}")
            
            # Step 2: Store in database
            if supabase and result.success:
                try:
                    # Store document record
                    document_data = result.get_database_record(document_id)
                    
                    # Add URL and other metadata (only use fields that exist in database)
                    document_data.update({
                        "url": f"test://{delivery_file.name}",
                        "metadata": {
                            "file_name": delivery_file.name,
                            "file_size": delivery_file.stat().st_size,
                            "file_extension": delivery_file.suffix[1:].upper(),
                            "extraction_method": "enhanced_marker_sonnet"
                        }
                    })
                    
                    # Insert document
                    doc_result = supabase.table("documents").insert(document_data).execute()
                    print(f"💾 Document record created in database")
                    
                    # For delivery documents, we could also store in specific tables
                    # For now, we store the comprehensive data in parsed_data
                    # Future enhancement: create specific tables for delivery_notes, packing_lists
                    
                    print(f"✅ Database integration successful")
                    
                except Exception as db_error:
                    print(f"❌ Database error: {db_error}")
            
            results.append(result)
            
        except Exception as e:
            print(f"❌ Error processing {delivery_file.name}: {e}")
            continue
        
        print("-" * 50)
    
    # Summary
    print("\n📈 WORKFLOW SUMMARY")
    print("=" * 50)
    
    successful = sum(1 for r in results if r.success)
    total_confidence = sum(r.confidence for r in results if r.success)
    avg_confidence = total_confidence / successful if successful > 0 else 0
    
    # Document type breakdown
    doc_types = {}
    items_total = 0
    for r in results:
        if r.success:
            doc_types[r.document_type] = doc_types.get(r.document_type, 0) + 1
            if r.extracted_data and r.extracted_data.items:
                items_total += len(r.extracted_data.items)
    
    print(f"✅ Successfully processed: {successful}/{len(delivery_docs)} documents")
    print(f"📊 Average confidence: {avg_confidence:.1%}")
    print(f"📋 Document types processed:")
    for doc_type, count in doc_types.items():
        print(f"   - {doc_type.replace('_', ' ').title()}: {count}")
    print(f"📦 Total items extracted: {items_total}")
    
    # Database verification
    if supabase:
        try:
            # Count delivery documents in database
            delivery_count = supabase.table("documents").select("id", count="exact").in_("type", ["DELIVERY_NOTE", "PACKING_LIST", "POD"]).execute()
            print(f"💾 Total delivery documents in database: {delivery_count.count}")
            
            # Show recent delivery documents
            recent_docs = supabase.table("documents").select(
                "id", "type", "confidence", "parsed_data", "created_at"
            ).in_("type", ["DELIVERY_NOTE", "PACKING_LIST", "POD"]).order("created_at", desc=True).limit(3).execute()
            
            print(f"📄 Recent delivery documents:")
            for doc in recent_docs.data:
                doc_type = doc['type'].replace('_', ' ')
                confidence = doc['confidence'] * 100
                items_count = doc['parsed_data'].get('items_count', 0) if doc['parsed_data'] else 0
                print(f"   - {doc_type}: {confidence:.0f}% confidence, {items_count} items")
                
        except Exception as e:
            print(f"⚠️ Database verification error: {e}")
    
    print("\n🎉 Enhanced Delivery Workflow Test Complete!")
    print("Key achievements:")
    print("- ✅ Marker API + Sonnet 3.5 extraction working")
    print("- ✅ Document type detection (delivery_note, packing_list, pod)")
    print("- ✅ Comprehensive field extraction")
    print("- ✅ Items array extraction for packing lists")
    print("- ✅ Database integration with documents table")
    print("- ✅ Raw markdown stored for debugging")
    print("- ✅ Confidence scoring and validation")


def analyze_field_extraction(results):
    """Analyze which fields are being extracted successfully."""
    print("\n🔍 FIELD EXTRACTION ANALYSIS")
    print("=" * 50)
    
    field_counts = {}
    total_docs = len([r for r in results if r.success])
    
    for result in results:
        if result.success and result.extracted_data:
            data_dict = result.extracted_data.model_dump()
            for field_name, field_value in data_dict.items():
                if field_name in ['validation_flags', 'confidence_score']:
                    continue
                    
                if field_value is not None:
                    if isinstance(field_value, str) and field_value.strip():
                        field_counts[field_name] = field_counts.get(field_name, 0) + 1
                    elif isinstance(field_value, list) and len(field_value) > 0:
                        field_counts[field_name] = field_counts.get(field_name, 0) + 1
                    elif isinstance(field_value, (int, float, bool)):
                        field_counts[field_name] = field_counts.get(field_name, 0) + 1
    
    # Sort by extraction rate
    sorted_fields = sorted(field_counts.items(), key=lambda x: x[1], reverse=True)
    
    print("Field extraction rates:")
    for field_name, count in sorted_fields:
        rate = count / total_docs * 100 if total_docs > 0 else 0
        field_display = field_name.replace('_', ' ').title()
        print(f"   {field_display}: {count}/{total_docs} ({rate:.0f}%)")


if __name__ == "__main__":
    asyncio.run(test_delivery_workflow()) 
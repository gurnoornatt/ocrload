#!/usr/bin/env python3
"""
Simple test of Enhanced Lumper Parser + Database Integration

Tests the enhanced lumper parser workflow and verifies data is saved to Supabase.
"""

import asyncio
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import what we need
from app.services.document_parsers.enhanced_lumper_parser import EnhancedLumperParser
from supabase import create_client

async def test_lumper_integration():
    """Test lumper parser with database integration."""
    print("🧪 Testing Enhanced Lumper Parser + Database Integration")
    
    # Check API keys
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")):
        print("❌ No Claude API key found!")
        return
    
    # Initialize Supabase
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")
    if not supabase_url or not supabase_key:
        print("❌ Supabase credentials not found!")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    print("✅ Supabase client initialized")
    
    # Initialize parser
    parser = EnhancedLumperParser()
    print("✅ Enhanced Lumper Parser initialized")
    
    # Find test lumper documents
    test_docs = Path("test_documents/lumper")
    lumper_files = list(test_docs.glob("*"))[:1]  # Test just 1 document
    
    if not lumper_files:
        print("❌ No lumper test documents found!")
        return
    
    for lumper_file in lumper_files:
        print(f"\n📄 Testing: {lumper_file.name}")
        
        # Read file
        with open(lumper_file, "rb") as f:
            file_content = f.read()
        
        # Get MIME type
        ext = lumper_file.suffix.lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.png': 'image/png', 
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.gif': 'image/gif'
        }
        mime_type = mime_types.get(ext, 'application/octet-stream')
        
        # Create document ID
        document_id = str(uuid.uuid4())
        
        try:
            # Test parser
            print("🔍 Running enhanced lumper parser...")
            result = await parser.parse_from_file_content(
                file_content=file_content,
                filename=lumper_file.name,
                mime_type=mime_type,
                document_id=document_id
            )
            
            print(f"✅ Parser completed:")
            print(f"   Confidence: {result.confidence:.3f}")
            print(f"   Receipt Number: {result.data.receipt_number}")
            print(f"   Facility: {result.data.facility_name}")
            print(f"   Total Amount: {result.data.total_amount}")
            print(f"   Method: {result.extraction_details.get('extraction_method')}")
            
            # Test database integration
            print("💾 Testing database integration...")
            
            # Create document record
            document_data = {
                "id": document_id,
                "type": "LUMPER_RECEIPT",
                "url": f"test://{lumper_file.name}",
                "status": "parsed",
                "confidence": result.confidence,
                "parsed_data": {
                    "receipt_number": result.data.receipt_number,
                    "facility_name": result.data.facility_name,
                    "total_amount": result.data.total_amount,
                    "extraction_method": "enhanced_marker_sonnet"
                },
                "ocr_engine": "datalab_marker_sonnet",
                "manual_review_required": result.confidence < 0.8
            }
            
            # Insert document
            doc_result = supabase.table("documents").insert(document_data).execute()
            
            if doc_result.data:
                print(f"✅ Document record created: {doc_result.data[0]['id']}")
                
                # Create lumper receipt record
                lumper_dict = {
                    "document_id": document_id,
                    "receipt_number": result.data.receipt_number,
                    "receipt_date": result.data.receipt_date.isoformat() if result.data.receipt_date else None,
                    "facility_name": result.data.facility_name,
                    "facility_address": result.data.facility_address,
                    "driver_name": result.data.driver_name,
                    "carrier_name": result.data.carrier_name,
                    "bol_number": result.data.bol_number,
                    "service_type": result.data.service_type,
                    "labor_hours": result.data.labor_hours,
                    "hourly_rate": float(result.data.hourly_rate) if result.data.hourly_rate else None,
                    "total_amount": float(result.data.total_amount) if result.data.total_amount else None,
                    "equipment_used": result.data.equipment_used,
                    "special_services": result.data.special_services,
                    "notes": result.data.notes
                }
                
                # Remove None values
                lumper_dict = {k: v for k, v in lumper_dict.items() if v is not None}
                
                lumper_result = supabase.table("lumper_receipts").insert(lumper_dict).execute()
                
                if lumper_result.data:
                    print(f"✅ Lumper receipt record created: {lumper_result.data[0]['id']}")
                    print("🎉 INTEGRATION TEST SUCCESSFUL!")
                else:
                    print("❌ Failed to create lumper receipt record")
            else:
                print("❌ Failed to create document record")
                
        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_lumper_integration()) 
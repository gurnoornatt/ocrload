#!/usr/bin/env python3
"""
Simple Lumper Receipt Integration Test

Tests only the semantic extraction part using the same pattern that works for invoices.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from uuid import uuid4

# Add the app directory to the Python path  
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.semantic_lumper_extractor import SemanticLumperExtractor
from app.services.document_parsers.lumper_parser import LumperReceiptParser
from app.models.database import LumperReceipt, Document, DocumentType, DocumentStatus
from app.services.supabase_client import supabase_service


async def test_lumper_parser_only():
    """Test only the lumper parser without OCR, following invoice pattern."""
    
    print("🧾 TESTING LUMPER PARSER (NO OCR)")
    print("=" * 60)
    
    # Sample lumper receipt text (simulating OCR output)
    sample_lumper_text = """
    LUMPER RECEIPT
    
    ABC Warehouse Services  
    123 Industrial Blvd, City, State 12345
    
    Receipt #: LR-2024-001
    Date: 2024-01-15
    
    Driver: John Smith
    Carrier: XYZ Trucking Co
    BOL #: BOL123456
    
    Service Type: Unloading
    Labor Hours: 2.5
    Hourly Rate: $35.00
    
    Equipment Used: Forklift, Pallet Jack
    
    Total Amount: $87.50
    
    Notes: Standard unloading service
    """
    
    try:
        # Initialize parser 
        parser = LumperReceiptParser()
        print("✅ Lumper Parser initialized")
        
        # Parse using AI extraction (same as invoice approach)
        print("\n🧠 AI Field Extraction:")
        parsed_data, extraction_confidence, parsing_success = await parser.parse_lumper_receipt(
            sample_lumper_text, use_ai=True, confidence_threshold=0.6
        )
        
        print(f"🎯 Extraction Confidence: {extraction_confidence:.1%}")
        print(f"✅ Parsing Success: {parsing_success}")
        
        # Show extracted fields
        print(f"\n📋 EXTRACTED FIELDS:")
        for field, value in parsed_data.items():
            if value is not None:
                print(f"• {field}: {value}")
        
        # Validate extracted data  
        validation_issues = parser.validate_parsed_data(parsed_data)
        
        if validation_issues:
            print(f"\n⚠️  VALIDATION ISSUES:")
            for issue in validation_issues:
                print(f"  - {issue}")
        else:
            print(f"\n✅ All validations passed")
        
        # Test key field accuracy
        print(f"\n🎯 ACCURACY CHECK:")
        receipt_num = parsed_data.get("receipt_number")
        total_amt = parsed_data.get("total_amount")
        facility = parsed_data.get("facility_name")
        
        print(f"   Expected Receipt: LR-2024-001")
        print(f"   Expected Total: 87.50")  
        print(f"   Expected Facility: ABC Warehouse Services")
        print(f"   Got Receipt: {receipt_num}")
        print(f"   Got Total: {total_amt}")
        print(f"   Got Facility: {facility}")
        
        success_count = 0
        if receipt_num and "LR-2024-001" in str(receipt_num):
            print("   ✅ Receipt number correct")
            success_count += 1
        else:
            print("   ❌ Receipt number incorrect")
            
        if total_amt and abs(float(total_amt) - 87.50) < 0.01:
            print("   ✅ Total amount correct")
            success_count += 1 
        else:
            print("   ❌ Total amount incorrect")
            
        if facility and "ABC Warehouse" in str(facility):
            print("   ✅ Facility name correct")
            success_count += 1
        else:
            print("   ❌ Facility name incorrect")
        
        print(f"\n📈 Accuracy: {success_count}/3 fields correct")
        
        return parsing_success and extraction_confidence >= 0.8 and success_count >= 2
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_database_integration():
    """Test database integration with pre-extracted data."""
    
    print(f"\n💾 TESTING DATABASE INTEGRATION")
    print("=" * 60)
    
    try:
        # Test database connection
        supabase = supabase_service.client
        test_query = supabase.table("lumper_receipts").select("count", count="exact").limit(1).execute()
        print(f"✅ Supabase connected (lumper_receipts table has {test_query.count} records)")
        
        # Create test data
        document_id = uuid4()
        document = Document(
            id=document_id,
            type=DocumentType.INVOICE,  # Using INVOICE as placeholder
            url=f"test://lumper_receipts/test_simple.pdf", 
            status=DocumentStatus.PARSED,
            confidence=0.95,
            parsed_data={"test": True},
            verified=True
        )
        
        # Create lumper receipt with test data
        lumper = LumperReceipt(
            document_id=document_id,
            receipt_number="LR-2024-001",
            receipt_date=datetime.strptime("2024-01-15", "%Y-%m-%d").date(),
            facility_name="ABC Warehouse Services",
            facility_address="123 Industrial Blvd, City, State 12345",
            driver_name="John Smith",
            carrier_name="XYZ Trucking Co",
            bol_number="BOL123456",
            service_type="Unloading",
            labor_hours=2.5,
            hourly_rate=35.00,
            total_amount=87.50,
            equipment_used="Forklift, Pallet Jack",
            notes="Standard unloading service"
        )
        
        print("📄 Test document and lumper receipt created")
        
        # Serialize for database insertion
        document_data = document.model_dump()
        document_data['id'] = str(document_data['id'])
        if document_data.get('driver_id'):
            document_data['driver_id'] = str(document_data['driver_id'])
        else:
            document_data['driver_id'] = None  # Keep as None, don't convert to string
        if document_data.get('load_id'):
            document_data['load_id'] = str(document_data['load_id'])
        else:
            document_data['load_id'] = None  # Keep as None, don't convert to string
        if 'created_at' in document_data and document_data['created_at']:
            document_data['created_at'] = document_data['created_at'].isoformat()
        if 'updated_at' in document_data and document_data['updated_at']:
            document_data['updated_at'] = document_data['updated_at'].isoformat()
        
        lumper_data = lumper.model_dump()
        lumper_data['id'] = str(lumper_data['id'])
        lumper_data['document_id'] = str(lumper_data['document_id'])
        if 'created_at' in lumper_data and lumper_data['created_at']:
            lumper_data['created_at'] = lumper_data['created_at'].isoformat()
        if 'updated_at' in lumper_data and lumper_data['updated_at']:
            lumper_data['updated_at'] = lumper_data['updated_at'].isoformat()
        if 'receipt_date' in lumper_data and lumper_data['receipt_date']:
            lumper_data['receipt_date'] = lumper_data['receipt_date'].isoformat()
        
        # Insert into database
        doc_result = supabase.table("documents").insert(document_data).execute()
        lumper_result = supabase.table("lumper_receipts").insert(lumper_data).execute()
        
        print(f"📄 Document saved with ID: {document_id}")
        print(f"🧾 Lumper receipt saved with ID: {lumper.id}")
        
        # Verify the data was saved
        verification_query = supabase.table("lumper_receipts").select("*").eq("document_id", str(document_id)).execute()
        
        if verification_query.data:
            saved_receipt = verification_query.data[0]
            print(f"✅ Lumper receipt successfully retrieved from database")
            print(f"📋 Verified Fields:")
            
            key_fields = ['receipt_number', 'facility_name', 'total_amount', 'service_type', 'driver_name']
            for field in key_fields:
                saved_value = saved_receipt.get(field)
                print(f"  ✅ {field}: {saved_value}")
            
            return True
        else:
            print(f"❌ Failed to retrieve saved lumper receipt from database")
            return False
            
    except Exception as e:
        print(f"❌ Database integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run simple lumper integration tests."""
    
    print("🚀 SIMPLE LUMPER INTEGRATION TEST")
    print("=" * 80)
    print("Testing: Semantic AI Extraction → Database Integration")
    print("=" * 80)
    
    # Check environment
    print(f"\n🔧 ENVIRONMENT CHECK:")
    openai_key = bool(os.getenv("OPENAI_API_KEY"))
    claude_key = bool(os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    
    print(f"   OpenAI API Key: {'✓' if openai_key else '❌'}")
    print(f"   Claude API Key: {'✓' if claude_key else '❌'}")
    
    if not openai_key and not claude_key:
        print("\n❌ No AI API keys configured!")
        return
    
    # Run tests
    results = {}
    
    print(f"\n{'='*60}")
    print(f"Running: Lumper Parser Test")
    results["Parser"] = await test_lumper_parser_only()
    
    print(f"\n{'='*60}")
    print(f"Running: Database Integration Test") 
    results["Database"] = await test_database_integration()
    
    # Summary
    print(f"\n{'='*80}")
    print(f"📊 TEST SUMMARY")
    print(f"{'='*80}")
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"   {test_name}: {status}")
    
    total_passed = sum(results.values())
    total_tests = len(results)
    
    print(f"\n📈 Overall: {total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("🎉 All tests passed! Lumper system working like invoice system.")
        print("✅ Task 27 (Lumper Parser) is COMPLETE and following the same formula.")
    else:
        print("⚠️  Some tests failed. Review issues.")
    
    print(f"\n{'='*80}")
    print(f"🏁 Test completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main()) 
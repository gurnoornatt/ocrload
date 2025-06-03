#!/usr/bin/env python3
"""
Simple Lumper Receipt Test

Tests the lumper receipt extraction using the same approach that works for invoices.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.semantic_lumper_extractor import SemanticLumperExtractor


async def test_simple_lumper_extraction():
    """Test lumper receipt extraction with sample text."""
    
    print("🧾 TESTING LUMPER RECEIPT EXTRACTION")
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
        extractor = SemanticLumperExtractor()
        
        print(f"✓ OpenAI available: {bool(extractor.openai_client)}")
        print(f"✓ Anthropic available: {bool(extractor.anthropic_client)}")
        
        if not extractor.openai_client and not extractor.anthropic_client:
            print("❌ No AI APIs configured - check environment variables")
            return False
        
        print("\n🔍 Extracting fields from sample lumper receipt...")
        
        extracted_data, confidence, cross_validation_passed = await extractor.extract_lumper_fields(
            text_content=sample_lumper_text,
            use_cross_validation=True
        )
        
        print(f"\n📊 EXTRACTION RESULTS:")
        print(f"   Confidence: {confidence:.3f}")
        print(f"   Cross Validation Passed: {cross_validation_passed}")
        
        print(f"\n📄 EXTRACTED FIELDS:")
        if hasattr(extracted_data, '__dict__'):
            for field, value in extracted_data.__dict__.items():
                if value is not None and field not in ['confidence_score', 'validation_flags']:
                    print(f"   {field}: {value}")
        
        # Show validation flags if any
        if extracted_data.validation_flags:
            print(f"\n⚠️  VALIDATION FLAGS:")
            for flag in extracted_data.validation_flags:
                print(f"   - {flag}")
        
        # Test key field extraction
        receipt_number = getattr(extracted_data, 'receipt_number', None)
        total_amount = getattr(extracted_data, 'total_amount', None)
        facility_name = getattr(extracted_data, 'facility_name', None)
        
        print(f"\n🎯 ACCURACY CHECK:")
        print(f"   Expected Receipt Number: LR-2024-001")
        print(f"   Expected Total: 87.50")
        print(f"   Expected Facility: ABC Warehouse Services")
        print(f"   Extracted Receipt Number: {receipt_number}")
        print(f"   Extracted Total: {total_amount}")
        print(f"   Extracted Facility: {facility_name}")
        
        success_count = 0
        if receipt_number and "LR-2024-001" in str(receipt_number):
            print("   ✅ CORRECT: Receipt number extracted properly")
            success_count += 1
        else:
            print("   ❌ ERROR: Receipt number not extracted correctly")
            
        if total_amount and abs(float(total_amount) - 87.50) < 0.01:
            print("   ✅ CORRECT: Total amount extracted properly")
            success_count += 1
        else:
            print("   ❌ ERROR: Total amount not extracted correctly")
            
        if facility_name and "ABC Warehouse" in str(facility_name):
            print("   ✅ CORRECT: Facility name extracted properly")
            success_count += 1
        else:
            print("   ❌ ERROR: Facility name not extracted correctly")
        
        print(f"\n📈 Success Rate: {success_count}/3 fields correct")
        
        return confidence >= 0.8 and success_count >= 2
        
    except Exception as e:
        print(f"❌ Lumper extraction test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run the simple lumper test."""
    print("🚀 SIMPLE LUMPER RECEIPT TEST")
    print("=" * 60)
    print("Testing lumper receipt extraction using the same pattern as invoice tests")
    print("=" * 60)
    
    # Check environment
    print("\n🔧 ENVIRONMENT CHECK:")
    openai_key = bool(os.getenv("OPENAI_API_KEY"))
    claude_key = bool(os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    
    print(f"   OpenAI API Key: {'✓' if openai_key else '❌'}")
    print(f"   Claude API Key: {'✓' if claude_key else '❌'}")
    
    if not openai_key and not claude_key:
        print("\n❌ No AI API keys configured!")
        print("   Set OPENAI_API_KEY and/or CLAUDE_API_KEY in your .env file")
        return
    
    # Run test
    try:
        success = await test_simple_lumper_extraction()
        
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        if success:
            print("✅ PASSED: Lumper extraction working correctly!")
            print("🎉 Ready to proceed with database integration test.")
        else:
            print("❌ FAILED: Lumper extraction needs fixes.")
            print("🔧 Review the extraction logic and try again.")
            
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main()) 
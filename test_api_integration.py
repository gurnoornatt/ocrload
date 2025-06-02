#!/usr/bin/env python3
"""
Test script for API integrations - OpenAI and Anthropic
"""

import asyncio
from app.services.semantic_invoice_extractor import SemanticInvoiceExtractor

async def test_integration():
    """Test both OpenAI and Anthropic integrations"""
    
    print("="*60)
    print("🧪 TESTING API INTEGRATIONS")
    print("="*60)
    
    extractor = SemanticInvoiceExtractor()
    
    # Sample invoice text
    sample_text = """
    Invoice #123
    Vendor: ACME Corp
    Date: 2024-01-15
    Due Date: 2024-02-15
    
    Subtotal: $145.00
    Tax: $9.06
    Total: $154.06
    """
    
    print(f"📄 Sample text: {sample_text.strip()}")
    print("\n" + "-"*60)
    
    # Test OpenAI
    print("🤖 Testing OpenAI integration...")
    try:
        result, confidence = extractor.extract_fields_openai(sample_text)
        print(f"✅ OpenAI Success!")
        print(f"   Total Amount: ${result.get('total_amount', 'Not found')}")
        print(f"   Subtotal: ${result.get('subtotal', 'Not found')}")
        print(f"   Tax: ${result.get('tax_amount', 'Not found')}")
        print(f"   Confidence: {confidence:.3f}")
        
        if result.get('total_amount') == 154.06:
            print("   ✅ Correctly extracted total amount!")
        else:
            print(f"   ⚠️  Expected 154.06, got {result.get('total_amount')}")
            
    except Exception as e:
        print(f"❌ OpenAI test failed: {e}")
    
    print("\n" + "-"*60)
    
    # Test Anthropic
    print("🧠 Testing Anthropic integration...")
    try:
        result2, confidence2 = await extractor.extract_fields_anthropic(sample_text)
        print(f"✅ Anthropic Success!")
        print(f"   Total Amount: ${result2.get('total_amount', 'Not found')}")
        print(f"   Subtotal: ${result2.get('subtotal', 'Not found')}")
        print(f"   Tax: ${result2.get('tax_amount', 'Not found')}")
        print(f"   Confidence: {confidence2:.3f}")
        
        if result2.get('total_amount') == 154.06:
            print("   ✅ Correctly extracted total amount!")
        else:
            print(f"   ⚠️  Expected 154.06, got {result2.get('total_amount')}")
            
    except Exception as e:
        print(f"❌ Anthropic test failed: {e}")
    
    print("\n" + "="*60)
    print("🏁 TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_integration()) 
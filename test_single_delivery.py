#!/usr/bin/env python3

import asyncio
from pathlib import Path
from app.services.enhanced_delivery_extractor import EnhancedDeliveryExtractor

async def test_single():
    print("Testing single delivery document extraction...")
    
    extractor = EnhancedDeliveryExtractor()
    
    # Test POD1.jpeg
    with open('test_documents/delivery_note/POD1.jpeg', 'rb') as f:
        content = f.read()
    
    try:
        result = await extractor.extract_delivery_fields_enhanced(content, 'POD1.jpeg')
        data, confidence, needs_review = result
        
        print(f'✅ Extraction successful!')
        print(f'Document Number: {data.document_number}')
        print(f'Document Type: {data.document_type}')
        print(f'Confidence: {confidence:.1%}')
        print(f'Shipper: {data.shipper_name}')
        print(f'Consignee: {data.consignee_name}')
        print(f'Items: {len(data.items)}')
        
        if data.validation_flags:
            print(f'Validation flags: {data.validation_flags}')
    
    except Exception as e:
        print(f'❌ Extraction failed: {e}')

if __name__ == "__main__":
    asyncio.run(test_single()) 
#!/usr/bin/env python3
"""
Detailed Invoice Extraction Analysis
Shows exactly what OCR captures vs what semantic AI extracts
"""

import asyncio
import json
import time
from pathlib import Path
from app.services.ocr_clients.enhanced_datalab_client import EnhancedDatalabClient
from app.services.semantic_invoice_extractor import SemanticInvoiceExtractor

async def analyze_invoice_extraction():
    """Detailed analysis of OCR vs Semantic extraction for each invoice"""
    
    print("🔍 DETAILED INVOICE EXTRACTION ANALYSIS")
    print("=" * 100)
    
    # Find all test documents
    test_dir = Path("test_documents")
    invoice_files = (
        list(test_dir.glob("*.png")) + 
        list(test_dir.glob("*.pdf")) + 
        list(test_dir.glob("*.jpg")) + 
        list(test_dir.glob("*.jpeg")) + 
        list(test_dir.glob("*.gif")) + 
        list(test_dir.glob("*.webp"))
    )
    invoice_files.sort()
    
    if not invoice_files:
        print("❌ No invoice files found")
        return
    
    # Initialize components
    ocr_client = EnhancedDatalabClient()
    semantic_extractor = SemanticInvoiceExtractor()
    
    for i, file_path in enumerate(invoice_files, 1):
        print(f"\n📄 INVOICE {i}: {file_path.name}")
        print("=" * 100)
        
        try:
            # Read file
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            filename = file_path.name
            import mimetypes
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type:
                mime_type = "application/octet-stream"
            
            # ===== STAGE 1: OCR ANALYSIS =====
            print("🔤 OCR EXTRACTION ANALYSIS")
            print("-" * 50)
            
            async with ocr_client as client:
                ocr_results = await client.process_invoice_comprehensive(
                    file_content, filename, mime_type
                )
            
            if ocr_results.get("success"):
                # Show OCR methods used
                methods = ocr_results.get("results", {})
                print(f"OCR Methods Used: {len(methods)}/3")
                
                for method_name, method_result in methods.items():
                    status = "✅ SUCCESS" if method_result.get("success") else "❌ FAILED"
                    print(f"  • {method_name}: {status}")
                    if method_result.get("error"):
                        print(f"    Error: {method_result['error']}")
                
                # Extract and show raw text
                raw_text = ocr_client.extract_text_from_results(ocr_results)
                ocr_confidence = ocr_results.get("confidence", 0.0)
                
                print(f"\nOCR Confidence: {ocr_confidence:.1%}")
                print(f"Text Length: {len(raw_text)} characters")
                print("\n📝 RAW OCR TEXT:")
                print("-" * 30)
                print(repr(raw_text))  # Show with escape sequences
                print("-" * 30)
                print("FORMATTED TEXT:")
                print(raw_text)
                print("-" * 50)
                
            else:
                print(f"❌ OCR Failed: {ocr_results.get('error', 'Unknown error')}")
                continue
            
            # ===== STAGE 2: SEMANTIC AI ANALYSIS =====
            print("\n🧠 SEMANTIC AI EXTRACTION ANALYSIS")
            print("-" * 50)
            
            # Test OpenAI extraction
            print("🤖 OpenAI GPT-4o Extraction:")
            openai_data, openai_confidence = semantic_extractor.extract_fields_openai(raw_text)
            print(f"  Confidence: {openai_confidence:.1%}")
            print("  Extracted Fields:")
            for key, value in openai_data.items():
                if key == "line_items" and isinstance(value, list):
                    print(f"    • {key}: {len(value)} items")
                    for idx, item in enumerate(value, 1):
                        print(f"      {idx}. {item}")
                elif key == "validation_flags" and isinstance(value, list):
                    print(f"    • {key}: {value}")
                else:
                    print(f"    • {key}: {value}")
            
            print("\n🧠 Anthropic Claude Extraction:")
            anthropic_data, anthropic_confidence = await semantic_extractor.extract_fields_anthropic(raw_text)
            print(f"  Confidence: {anthropic_confidence:.1%}")
            print("  Extracted Fields:")
            for key, value in anthropic_data.items():
                if key == "line_items" and isinstance(value, list):
                    print(f"    • {key}: {len(value)} items")
                    for idx, item in enumerate(value, 1):
                        print(f"      {idx}. {item}")
                elif key == "validation_flags" and isinstance(value, list):
                    print(f"    • {key}: {value}")
                else:
                    print(f"    • {key}: {value}")
            
            # ===== STAGE 3: COMPARISON ANALYSIS =====
            print(f"\n⚖️  EXTRACTION COMPARISON")
            print("-" * 50)
            
            # Compare key fields
            key_fields = ["invoice_number", "vendor_name", "invoice_date", "due_date", 
                         "subtotal", "tax_amount", "total_amount", "currency"]
            
            print(f"{'Field':<15} {'OpenAI':<20} {'Anthropic':<20} {'Match':<8}")
            print("-" * 70)
            
            for field in key_fields:
                openai_val = openai_data.get(field, "N/A")
                anthropic_val = anthropic_data.get(field, "N/A")
                
                # Convert to string for comparison
                openai_str = str(openai_val) if openai_val is not None else "None"
                anthropic_str = str(anthropic_val) if anthropic_val is not None else "None"
                
                match = "✅" if openai_str == anthropic_str else "❌"
                
                print(f"{field:<15} {openai_str:<20} {anthropic_str:<20} {match:<8}")
            
            # Line items comparison
            openai_items = openai_data.get("line_items", [])
            anthropic_items = anthropic_data.get("line_items", [])
            
            print(f"\nLine Items:")
            print(f"  OpenAI: {len(openai_items)} items")
            print(f"  Anthropic: {len(anthropic_items)} items")
            
            if openai_items:
                print("  OpenAI Line Items:")
                for idx, item in enumerate(openai_items, 1):
                    print(f"    {idx}. {item}")
            
            if anthropic_items:
                print("  Anthropic Line Items:")
                for idx, item in enumerate(anthropic_items, 1):
                    print(f"    {idx}. {item}")
            
            # ===== STAGE 4: FINANCIAL VALIDATION =====
            print(f"\n💰 FINANCIAL VALIDATION")
            print("-" * 50)
            
            def validate_math(data, model_name):
                subtotal = data.get("subtotal")
                tax = data.get("tax_amount")
                total = data.get("total_amount")
                
                if subtotal is not None and tax is not None and total is not None:
                    expected = subtotal + tax
                    actual = total
                    diff = abs(expected - actual)
                    status = "✅" if diff < 0.01 else "❌"
                    print(f"  {model_name}: {subtotal} + {tax} = {expected} (actual: {actual}) {status}")
                    return diff < 0.01
                else:
                    print(f"  {model_name}: Missing financial data")
                    return False
            
            openai_math_correct = validate_math(openai_data, "OpenAI")
            anthropic_math_correct = validate_math(anthropic_data, "Anthropic")
            
            # ===== STAGE 5: ACCURACY ASSESSMENT =====
            print(f"\n📊 ACCURACY ASSESSMENT")
            print("-" * 50)
            
            # Count matching fields
            matches = sum(1 for field in key_fields 
                         if str(openai_data.get(field, "")) == str(anthropic_data.get(field, "")))
            
            agreement_rate = matches / len(key_fields)
            
            print(f"Field Agreement: {matches}/{len(key_fields)} ({agreement_rate:.1%})")
            print(f"Math Validation: OpenAI: {'✅' if openai_math_correct else '❌'}, "
                  f"Anthropic: {'✅' if anthropic_math_correct else '❌'}")
            print(f"Confidence Scores: OpenAI: {openai_confidence:.1%}, Anthropic: {anthropic_confidence:.1%}")
            
            # Overall assessment
            if agreement_rate >= 0.8 and (openai_math_correct or anthropic_math_correct):
                assessment = "🎉 EXCELLENT"
            elif agreement_rate >= 0.6:
                assessment = "✅ GOOD"
            else:
                assessment = "⚠️ NEEDS REVIEW"
            
            print(f"Overall Assessment: {assessment}")
            
        except Exception as e:
            print(f"❌ ERROR processing {file_path.name}: {e}")
        
        print("\n" + "=" * 100)

if __name__ == "__main__":
    asyncio.run(analyze_invoice_extraction()) 
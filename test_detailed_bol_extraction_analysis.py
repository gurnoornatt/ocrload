#!/usr/bin/env python3
"""
Detailed Bill of Lading (BOL) Extraction Analysis
Shows exactly what OCR captures vs what semantic AI extracts for BOL documents
"""

import asyncio
import json
import time
from pathlib import Path
from app.services.ocr_clients.enhanced_datalab_client import EnhancedDatalabClient
from app.services.semantic_bol_extractor import SemanticBOLExtractor

async def analyze_bol_extraction():
    """Detailed analysis of OCR vs Semantic extraction for each BOL document"""
    
    print("🔍 DETAILED BOL EXTRACTION ANALYSIS")
    print("=" * 100)
    
    # Find all test documents
    test_dir = Path("test_documents")
    bol_files = (
        list(test_dir.glob("*bol*")) + 
        list(test_dir.glob("*BOL*")) + 
        list(test_dir.glob("*lading*")) + 
        list(test_dir.glob("*.png")) + 
        list(test_dir.glob("*.pdf")) + 
        list(test_dir.glob("*.jpg")) + 
        list(test_dir.glob("*.jpeg")) + 
        list(test_dir.glob("*.gif")) + 
        list(test_dir.glob("*.webp"))
    )
    
    # Remove duplicates and sort
    bol_files = list(set(bol_files))
    bol_files.sort()
    
    if not bol_files:
        print("❌ No BOL files found")
        print("   Please add BOL documents to test_documents/ directory")
        print("   Supported formats: PNG, PDF, JPG, JPEG, GIF, WEBP")
        return
    
    print(f"📁 Found {len(bol_files)} test documents:")
    for file_path in bol_files:
        print(f"   - {file_path.name}")
    
    # Initialize components
    ocr_client = EnhancedDatalabClient()
    semantic_extractor = SemanticBOLExtractor()
    
    for i, file_path in enumerate(bol_files, 1):
        print(f"\n📄 BOL DOCUMENT {i}: {file_path.name}")
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
                # Use the comprehensive method for BOL documents
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
                if key == "validation_flags" and isinstance(value, list):
                    print(f"    • {key}: {value}")
                else:
                    print(f"    • {key}: {value}")
            
            print("\n🧠 Anthropic Claude Extraction:")
            anthropic_data, anthropic_confidence = await semantic_extractor.extract_fields_anthropic(raw_text)
            print(f"  Confidence: {anthropic_confidence:.1%}")
            print("  Extracted Fields:")
            for key, value in anthropic_data.items():
                if key == "validation_flags" and isinstance(value, list):
                    print(f"    • {key}: {value}")
                else:
                    print(f"    • {key}: {value}")
            
            # ===== STAGE 3: COMPARISON ANALYSIS =====
            print(f"\n⚖️  EXTRACTION COMPARISON")
            print("-" * 50)
            
            # Compare key fields
            key_fields = ["bol_number", "pro_number", "tracking_number", "ship_date", "delivery_date",
                         "shipper_name", "consignee_name", "carrier_name", "carrier_scac",
                         "freight_description", "weight", "weight_unit", "pieces", "freight_charges"]
            
            print(f"{'Field':<20} {'OpenAI':<25} {'Anthropic':<25} {'Match':<8}")
            print("-" * 85)
            
            for field in key_fields:
                openai_val = openai_data.get(field, "N/A")
                anthropic_val = anthropic_data.get(field, "N/A")
                
                # Convert to string for comparison
                openai_str = str(openai_val) if openai_val is not None else "None"
                anthropic_str = str(anthropic_val) if anthropic_val is not None else "None"
                
                # Truncate long strings for display
                openai_display = openai_str[:22] + "..." if len(openai_str) > 22 else openai_str
                anthropic_display = anthropic_str[:22] + "..." if len(anthropic_str) > 22 else anthropic_str
                
                match = "✅" if openai_str == anthropic_str else "❌"
                
                print(f"{field:<20} {openai_display:<25} {anthropic_display:<25} {match:<8}")
            
            # ===== STAGE 4: BOL-SPECIFIC VALIDATION =====
            print(f"\n📋 BOL-SPECIFIC VALIDATION")
            print("-" * 50)
            
            def validate_bol_data(data, model_name):
                """Validate BOL-specific business logic"""
                issues = []
                
                # Check for required BOL fields
                required_fields = ["bol_number", "shipper_name", "consignee_name", "carrier_name"]
                missing = [field for field in required_fields if not data.get(field)]
                if missing:
                    issues.append(f"Missing required fields: {missing}")
                
                # Validate weight is positive
                weight = data.get("weight")
                if weight is not None:
                    try:
                        weight_val = float(weight)
                        if weight_val <= 0:
                            issues.append("Invalid weight (must be positive)")
                    except (ValueError, TypeError):
                        issues.append("Invalid weight format")
                
                # Validate pieces count
                pieces = data.get("pieces")
                if pieces is not None:
                    try:
                        pieces_val = int(pieces)
                        if pieces_val <= 0:
                            issues.append("Invalid pieces count (must be positive)")
                    except (ValueError, TypeError):
                        issues.append("Invalid pieces format")
                
                # Validate freight charges
                charges = data.get("freight_charges")
                if charges is not None:
                    try:
                        charges_val = float(charges)
                        if charges_val < 0:
                            issues.append("Invalid freight charges (cannot be negative)")
                    except (ValueError, TypeError):
                        issues.append("Invalid freight charges format")
                
                # Check address completeness
                for addr_field in ["shipper_address", "consignee_address"]:
                    addr = data.get(addr_field)
                    if addr and len(str(addr).strip()) < 10:
                        issues.append(f"Incomplete {addr_field}")
                
                status = "✅ VALID" if not issues else f"⚠️ ISSUES: {'; '.join(issues)}"
                print(f"  {model_name}: {status}")
                return len(issues) == 0
            
            openai_valid = validate_bol_data(openai_data, "OpenAI")
            anthropic_valid = validate_bol_data(anthropic_data, "Anthropic")
            
            # ===== STAGE 5: LOGISTICS FIELD ANALYSIS =====
            print(f"\n🚛 LOGISTICS FIELD ANALYSIS")
            print("-" * 50)
            
            # Analyze logistics-specific fields
            logistics_fields = {
                "BOL Number": ["bol_number"],
                "Pro Number": ["pro_number"], 
                "Tracking": ["tracking_number"],
                "Shipper Info": ["shipper_name", "shipper_address"],
                "Consignee Info": ["consignee_name", "consignee_address"],
                "Carrier Info": ["carrier_name", "carrier_scac"],
                "Freight Details": ["freight_description", "weight", "weight_unit", "pieces"],
                "Charges": ["freight_charges"],
                "Dates": ["ship_date", "delivery_date"],
                "Instructions": ["special_instructions"]
            }
            
            print("Category Analysis:")
            for category, fields in logistics_fields.items():
                openai_count = sum(1 for field in fields if openai_data.get(field))
                anthropic_count = sum(1 for field in fields if anthropic_data.get(field))
                total_fields = len(fields)
                
                openai_pct = (openai_count / total_fields) * 100
                anthropic_pct = (anthropic_count / total_fields) * 100
                
                print(f"  {category:<15}: OpenAI {openai_count}/{total_fields} ({openai_pct:.0f}%), "
                      f"Anthropic {anthropic_count}/{total_fields} ({anthropic_pct:.0f}%)")
            
            # ===== STAGE 6: ACCURACY ASSESSMENT =====
            print(f"\n📊 ACCURACY ASSESSMENT")
            print("-" * 50)
            
            # Count matching fields
            matches = sum(1 for field in key_fields 
                         if str(openai_data.get(field, "")) == str(anthropic_data.get(field, "")))
            
            agreement_rate = matches / len(key_fields)
            
            print(f"Field Agreement: {matches}/{len(key_fields)} ({agreement_rate:.1%})")
            print(f"Data Validation: OpenAI: {'✅' if openai_valid else '❌'}, "
                  f"Anthropic: {'✅' if anthropic_valid else '❌'}")
            print(f"Confidence Scores: OpenAI: {openai_confidence:.1%}, Anthropic: {anthropic_confidence:.1%}")
            
            # Overall assessment
            if agreement_rate >= 0.8 and (openai_valid or anthropic_valid):
                assessment = "🎉 EXCELLENT"
            elif agreement_rate >= 0.6:
                assessment = "✅ GOOD"
            else:
                assessment = "⚠️ NEEDS REVIEW"
            
            print(f"Overall Assessment: {assessment}")
            
            # ===== STAGE 7: COMPREHENSIVE BOL EXTRACTION =====
            print(f"\n🔧 COMPREHENSIVE BOL EXTRACTION TEST")
            print("-" * 50)
            
            # Test the main extraction method
            extracted_data, confidence, needs_review = await semantic_extractor.extract_bol_fields(
                raw_text, use_cross_validation=True
            )
            
            print(f"Final Extraction Results:")
            print(f"  Confidence: {confidence:.1%}")
            print(f"  Needs Review: {needs_review}")
            print(f"  Validation Flags: {extracted_data.validation_flags}")
            
            # Show final extracted data
            print(f"\n📋 FINAL EXTRACTED BOL DATA:")
            extracted_dict = extracted_data.dict()
            for key, value in extracted_dict.items():
                if key not in ["confidence_score", "validation_flags"]:
                    print(f"  • {key}: {value}")
            
        except Exception as e:
            print(f"❌ ERROR processing {file_path.name}: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 100)

if __name__ == "__main__":
    asyncio.run(analyze_bol_extraction()) 
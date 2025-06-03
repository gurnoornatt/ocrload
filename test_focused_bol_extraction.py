#!/usr/bin/env python3
"""
Focused BOL Extraction Test

Clear workflow demonstration:
Document Name → Marker API → Sonnet 3.5 → Results

Only processes real BOL documents (not templates or air waybills).
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Configure clean logging
logging.basicConfig(level=logging.WARNING)

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.enhanced_bol_extractor import EnhancedBOLExtractor
from app.services.ocr_clients.datalab_marker_client import DatalabMarkerClient


def is_real_bol(markdown_content: str) -> bool:
    """Check if the document contains actual BOL data (not a template)."""
    if not markdown_content:
        return False
    
    # Look for BOL indicators
    bol_indicators = ['bill of lading', 'bol', 'shipper', 'consignee', 'carrier']
    air_indicators = ['air waybill', 'hawb', 'awb', 'aircraft', 'etihad', 'airline']
    
    content_lower = markdown_content.lower()
    
    # Exclude air waybills
    if any(indicator in content_lower for indicator in air_indicators):
        return False
    
    # Check for BOL content and actual data (not just form fields)
    has_bol_content = any(indicator in content_lower for indicator in bol_indicators)
    
    # Look for actual data (company names, numbers, etc.)
    has_data = (
        any(word in content_lower for word in ['llc', 'inc', 'corp', 'company', 'ltd']) or
        any(char.isdigit() for char in markdown_content if char not in '|-:')
    )
    
    return has_bol_content and has_data


async def test_single_bol(file_path: Path) -> dict:
    """Test a single BOL file with clear step documentation."""
    
    print(f"\n{'='*60}")
    print(f"📄 PROCESSING: {file_path.name}")
    print(f"{'='*60}")
    
    # Step 1: Read document
    print(f"🔄 STEP 1: Reading document...")
    try:
        with open(file_path, "rb") as f:
            file_content = f.read()
        print(f"   ✅ Document loaded: {len(file_content):,} bytes")
    except Exception as e:
        print(f"   ❌ Failed to read document: {e}")
        return {"success": False, "error": f"Read failed: {e}"}
    
    # Step 2: Marker API processing
    print(f"🔄 STEP 2: Marker API processing...")
    try:
        async with DatalabMarkerClient() as marker_client:
            marker_result = await marker_client.process_document(
                file_content=file_content,
                filename=file_path.name,
                mime_type="image/jpeg",
                language="English",
                force_ocr=True,
                use_llm=True,
                output_format="markdown"
            )
        
        if marker_result.success:
            print(f"   ✅ Marker API success: {marker_result.content_length:,} chars")
            print(f"   📊 Tables detected: {len(marker_result.get_tables())}")
            
            # Check if this is a real BOL
            if not is_real_bol(marker_result.markdown_content):
                print(f"   ⚠️  Document appears to be template/air waybill - SKIPPING")
                return {"success": False, "skip_reason": "Not a real BOL document"}
                
        else:
            print(f"   ❌ Marker API failed: {marker_result.error}")
            return {"success": False, "error": f"Marker failed: {marker_result.error}"}
            
    except Exception as e:
        print(f"   ❌ Marker API error: {e}")
        return {"success": False, "error": f"Marker error: {e}"}
    
    # Step 3: Sonnet 3.5 extraction
    print(f"🔄 STEP 3: Sonnet 3.5 extraction...")
    try:
        extractor = EnhancedBOLExtractor()
        
        # Use the enhanced extraction method
        extracted_data, confidence, needs_review = await extractor.extract_bol_fields_enhanced(
            file_content=file_content,
            filename=file_path.name,
            mime_type="image/jpeg"
        )
        
        print(f"   ✅ Sonnet 3.5 completed")
        print(f"   📈 Confidence: {confidence:.1%}")
        print(f"   🔍 Review needed: {needs_review}")
        
    except Exception as e:
        print(f"   ❌ Sonnet 3.5 error: {e}")
        return {"success": False, "error": f"Sonnet error: {e}"}
    
    # Step 4: Analyze results
    print(f"🔄 STEP 4: Analyzing results...")
    
    extracted_dict = extracted_data.model_dump()
    
    # Core BOL fields
    core_fields = {
        "bol_number": "BOL Number",
        "pro_number": "Pro Number", 
        "shipper_name": "Shipper",
        "consignee_name": "Consignee",
        "carrier_name": "Carrier"
    }
    
    print(f"   📋 CORE BOL FIELDS:")
    extracted_core = 0
    for field, label in core_fields.items():
        value = extracted_dict.get(field)
        if value:
            print(f"      ✅ {label}: {value}")
            extracted_core += 1
        else:
            print(f"      ❌ {label}: Missing")
    
    # Additional fields
    additional_fields = {
        "pickup_date": "Pickup Date",
        "delivery_date": "Delivery Date",
        "commodity_description": "Commodity",
        "weight": "Weight",
        "pieces": "Pieces",
        "freight_charges": "Charges"
    }
    
    print(f"   📋 ADDITIONAL FIELDS:")
    extracted_additional = 0
    for field, label in additional_fields.items():
        value = extracted_dict.get(field)
        if value:
            print(f"      ✅ {label}: {value}")
            extracted_additional += 1
        else:
            print(f"      ⭕ {label}: Not found")
    
    # Validation issues
    if extracted_data.validation_flags:
        print(f"   ⚠️  VALIDATION ISSUES:")
        for flag in extracted_data.validation_flags:
            print(f"      • {flag}")
    
    # Summary
    total_extracted = extracted_core + extracted_additional
    total_possible = len(core_fields) + len(additional_fields)
    completeness = total_extracted / total_possible
    
    print(f"\n📊 EXTRACTION SUMMARY:")
    print(f"   Core fields: {extracted_core}/{len(core_fields)} ({extracted_core/len(core_fields):.1%})")
    print(f"   Additional: {extracted_additional}/{len(additional_fields)} ({extracted_additional/len(additional_fields):.1%})")
    print(f"   Overall: {total_extracted}/{total_possible} ({completeness:.1%})")
    print(f"   Confidence: {confidence:.1%}")
    print(f"   Quality: {'🟢 Good' if confidence > 0.7 else '🟡 Fair' if confidence > 0.4 else '🔴 Poor'}")
    
    return {
        "success": True,
        "filename": file_path.name,
        "confidence": confidence,
        "needs_review": needs_review,
        "core_extracted": extracted_core,
        "core_total": len(core_fields),
        "additional_extracted": extracted_additional,
        "additional_total": len(additional_fields),
        "total_extracted": total_extracted,
        "total_possible": total_possible,
        "completeness": completeness,
        "validation_issues": len(extracted_data.validation_flags),
        "extracted_data": extracted_dict
    }


async def main():
    """Run focused BOL extraction testing."""
    
    # Check API keys
    datalab_key = os.getenv("DATALAB_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    
    missing_keys = []
    if not datalab_key:
        missing_keys.append("DATALAB_API_KEY")
    if not anthropic_key:
        missing_keys.append("ANTHROPIC_API_KEY")
    
    if missing_keys:
        print(f"❌ Missing required API keys: {', '.join(missing_keys)}")
        return
    
    print("🚀 FOCUSED BOL EXTRACTION TEST")
    print("=" * 60)
    print("Workflow: Document → Marker API → Sonnet 3.5 → Results")
    print("Target: Real BOL documents only (no templates/air waybills)")
    
    # Find BOL test documents
    test_dir = Path("test_documents/bol")
    if not test_dir.exists():
        print(f"❌ BOL test directory not found: {test_dir}")
        return
    
    bol_files = list(test_dir.glob("*.jpg"))
    if not bol_files:
        print("❌ No BOL files found")
        return
    
    print(f"📁 Found {len(bol_files)} BOL files")
    
    # Test each BOL file
    results = []
    successful_tests = 0
    
    for bol_file in bol_files:
        result = await test_single_bol(bol_file)
        results.append(result)
        
        if result.get("success"):
            successful_tests += 1
        elif result.get("skip_reason"):
            print(f"   ⏭️  Skipped: {result['skip_reason']}")
        else:
            print(f"   💥 Failed: {result.get('error', 'Unknown error')}")
    
    # Final summary
    print(f"\n\n🎯 FINAL ASSESSMENT")
    print("=" * 60)
    
    if successful_tests > 0:
        successful_results = [r for r in results if r.get("success")]
        
        avg_confidence = sum(r["confidence"] for r in successful_results) / len(successful_results)
        avg_completeness = sum(r["completeness"] for r in successful_results) / len(successful_results)
        total_core = sum(r["core_extracted"] for r in successful_results)
        total_core_possible = sum(r["core_total"] for r in successful_results)
        
        print(f"✅ Successfully processed: {successful_tests}/{len(bol_files)} BOL documents")
        print(f"📈 Average confidence: {avg_confidence:.1%}")
        print(f"📋 Average completeness: {avg_completeness:.1%}")
        print(f"🎯 Core field extraction: {total_core}/{total_core_possible} ({total_core/total_core_possible:.1%})")
        
        print(f"\n🔍 PER-DOCUMENT BREAKDOWN:")
        for result in successful_results:
            quality = "🟢" if result["confidence"] > 0.7 else "🟡" if result["confidence"] > 0.4 else "🔴"
            print(f"   {quality} {result['filename']}: {result['confidence']:.1%} confidence, {result['completeness']:.1%} complete")
        
        if avg_confidence > 0.6:
            print(f"\n✅ WORKFLOW IS WORKING WELL!")
        else:
            print(f"\n⚠️  WORKFLOW NEEDS IMPROVEMENT")
            
    else:
        print("❌ No successful extractions")
        print("🔧 Check: Document quality, API keys, or BOL content")


if __name__ == "__main__":
    asyncio.run(main()) 
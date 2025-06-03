#!/usr/bin/env python3
"""
Detailed BOL Extraction Analysis

Analyzes the actual Claude responses and extracted data quality 
to understand which workflow performs better:

OLD: Raw OCR Text → Sonnet 3.5
NEW: Marker API (structured) → Sonnet 3.5

Shows raw responses, extracted fields, and quality metrics.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Configure logging to show what Claude actually returns
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.enhanced_bol_extractor import EnhancedBOLExtractor
from app.services.ocr_clients.datalab_marker_client import DatalabMarkerClient


async def analyze_single_document(filepath: Path):
    """Detailed analysis of a single document with both workflows."""
    
    print(f"\n" + "="*80)
    print(f"📄 DETAILED ANALYSIS: {filepath.name}")
    print("="*80)
    
    # Read document
    with open(filepath, 'rb') as f:
        file_content = f.read()
    print(f"📂 Document: {len(file_content):,} bytes\n")
    
    # Initialize
    extractor = EnhancedBOLExtractor()
    
    # ================== OLD WORKFLOW ==================
    print("🔴 OLD WORKFLOW: Raw OCR Text → Sonnet 3.5")
    print("-" * 50)
    
    async with DatalabMarkerClient() as marker:
        old_result = await marker.process_document(
            file_content=file_content,
            filename=filepath.name,
            mime_type="image/jpeg",
            language="English",
            force_ocr=True,
            use_llm=False,  # RAW OCR only
            output_format="markdown"
        )
    
    if old_result.success:
        print(f"📊 Raw OCR: {len(old_result.markdown_content):,} chars")
        print(f"📋 Preview: {old_result.markdown_content[:150]}...")
        
        # Extract with Sonnet 3.5
        old_extracted, old_confidence = await extractor.extract_fields_from_markdown(
            markdown_content=old_result.markdown_content,
            marker_metadata={"workflow": "old"}
        )
        
        print(f"🎯 OLD Results:")
        print(f"   Confidence: {old_confidence:.1%}")
        print(f"   BOL Number: {old_extracted.get('bol_number', 'Missing')}")
        print(f"   Shipper: {old_extracted.get('shipper_name', 'Missing')}")
        print(f"   Consignee: {old_extracted.get('consignee_name', 'Missing')}")
        print(f"   Carrier: {old_extracted.get('carrier_name', 'Missing')}")
        print(f"   Weight: {old_extracted.get('weight', 'Missing')}")
        
        # Count extracted fields
        old_filled = sum(1 for v in old_extracted.values() if v and v != "Missing")
        print(f"   Fields extracted: {old_filled}/18")
    else:
        print("❌ OLD workflow failed")
        old_extracted, old_confidence = {}, 0.0
        old_filled = 0
    
    print()
    
    # ================== NEW WORKFLOW ==================
    print("🟢 NEW WORKFLOW: Marker API (structured) → Sonnet 3.5")
    print("-" * 50)
    
    async with DatalabMarkerClient() as marker:
        new_result = await marker.process_document(
            file_content=file_content,
            filename=filepath.name,
            mime_type="image/jpeg",
            language="English",
            force_ocr=True,
            use_llm=True,  # ENHANCED with LLM structure
            output_format="markdown"
        )
    
    if new_result.success:
        print(f"📊 Enhanced markdown: {len(new_result.markdown_content):,} chars")
        print(f"📋 Tables detected: {len(new_result.get_tables())}")
        print(f"📋 Preview: {new_result.markdown_content[:150]}...")
        
        # Extract with Sonnet 3.5
        new_extracted, new_confidence = await extractor.extract_fields_from_markdown(
            markdown_content=new_result.markdown_content,
            marker_metadata={"workflow": "new"}
        )
        
        print(f"🎯 NEW Results:")
        print(f"   Confidence: {new_confidence:.1%}")
        print(f"   BOL Number: {new_extracted.get('bol_number', 'Missing')}")
        print(f"   Shipper: {new_extracted.get('shipper_name', 'Missing')}")
        print(f"   Consignee: {new_extracted.get('consignee_name', 'Missing')}")
        print(f"   Carrier: {new_extracted.get('carrier_name', 'Missing')}")
        print(f"   Weight: {new_extracted.get('weight', 'Missing')}")
        
        # Count extracted fields
        new_filled = sum(1 for v in new_extracted.values() if v and v != "Missing")
        print(f"   Fields extracted: {new_filled}/18")
    else:
        print("❌ NEW workflow failed")
        new_extracted, new_confidence = {}, 0.0
        new_filled = 0
    
    print()
    
    # ================== COMPARISON ==================
    print("⚖️  DETAILED COMPARISON")
    print("-" * 50)
    
    print(f"📈 Confidence Scores:")
    print(f"   OLD: {old_confidence:.1%}")
    print(f"   NEW: {new_confidence:.1%}")
    conf_winner = "NEW" if new_confidence > old_confidence else "OLD" if old_confidence > new_confidence else "TIE"
    print(f"   Winner: {conf_winner}")
    
    print(f"\n📊 Data Completeness:")
    print(f"   OLD: {old_filled}/18 fields")
    print(f"   NEW: {new_filled}/18 fields")
    data_winner = "NEW" if new_filled > old_filled else "OLD" if old_filled > new_filled else "TIE"
    print(f"   Winner: {data_winner}")
    
    # Field-by-field comparison
    print(f"\n🔍 Field-by-Field Analysis:")
    key_fields = ['bol_number', 'shipper_name', 'consignee_name', 'carrier_name', 'weight', 'pieces']
    for field in key_fields:
        old_val = str(old_extracted.get(field, "Missing"))[:30]
        new_val = str(new_extracted.get(field, "Missing"))[:30]
        
        if old_val != "Missing" and new_val != "Missing":
            status = "✅ Both"
        elif new_val != "Missing":
            status = "🟢 NEW only"
        elif old_val != "Missing":
            status = "🔴 OLD only"
        else:
            status = "❌ Neither"
            
        print(f"   {field:>16}: {status}")
    
    # Overall assessment
    print(f"\n🏆 OVERALL ASSESSMENT:")
    if new_confidence > old_confidence and new_filled >= old_filled:
        verdict = "🟢 NEW WORKFLOW SUPERIOR"
    elif old_confidence > new_confidence and old_filled >= new_filled:
        verdict = "🔴 OLD WORKFLOW SUPERIOR"
    elif new_filled > old_filled:
        verdict = "🟢 NEW WORKFLOW SUPERIOR (More Data)"
    elif old_filled > new_filled:
        verdict = "🔴 OLD WORKFLOW SUPERIOR (More Data)"
    else:
        verdict = "🟡 WORKFLOWS EQUIVALENT"
    
    print(f"   {verdict}")
    
    return {
        'filename': filepath.name,
        'old_confidence': old_confidence,
        'new_confidence': new_confidence,
        'old_fields': old_filled,
        'new_fields': new_filled,
        'verdict': verdict
    }


async def main():
    """Run detailed analysis on key BOL documents."""
    
    print("🔍 DETAILED BOL EXTRACTION ANALYSIS")
    print("="*80)
    print("Analyzing actual Claude responses and data quality")
    print("OLD: Raw OCR → Sonnet 3.5")
    print("NEW: Marker API → Sonnet 3.5")
    
    # Analyze key documents
    bol_dir = Path("test_documents/bol")
    test_files = [
        "BOL2.jpg",  # Known good document
        "BOL9.jpg",  # Another good document  
        "BOL4.jpg"   # International document
    ]
    
    results = []
    for filename in test_files:
        filepath = bol_dir / filename
        if filepath.exists():
            result = await analyze_single_document(filepath)
            results.append(result)
        else:
            print(f"⚠️  File not found: {filename}")
    
    # Summary
    if results:
        print(f"\n" + "="*80)
        print("📊 SUMMARY ANALYSIS")
        print("="*80)
        
        new_wins = sum(1 for r in results if "NEW" in r['verdict'])
        old_wins = sum(1 for r in results if "OLD" in r['verdict'])
        ties = sum(1 for r in results if "EQUIVALENT" in r['verdict'])
        
        avg_old_conf = sum(r['old_confidence'] for r in results) / len(results)
        avg_new_conf = sum(r['new_confidence'] for r in results) / len(results)
        avg_old_fields = sum(r['old_fields'] for r in results) / len(results)
        avg_new_fields = sum(r['new_fields'] for r in results) / len(results)
        
        print(f"🏆 VERDICT BREAKDOWN:")
        print(f"   🟢 NEW workflow wins: {new_wins}")
        print(f"   🔴 OLD workflow wins: {old_wins}")
        print(f"   🟡 Equivalent: {ties}")
        
        print(f"\n📊 AVERAGE PERFORMANCE:")
        print(f"   Confidence - OLD: {avg_old_conf:.1%}, NEW: {avg_new_conf:.1%}")
        print(f"   Data Fields - OLD: {avg_old_fields:.1f}, NEW: {avg_new_fields:.1f}")
        
        if new_wins > old_wins:
            print(f"\n🎉 CONCLUSION: NEW WORKFLOW IS BETTER")
            print(f"   The enhanced Marker API approach delivers superior results")
        elif old_wins > new_wins:
            print(f"\n🤔 CONCLUSION: OLD WORKFLOW IS BETTER") 
            print(f"   Raw OCR approach is currently more effective")
        else:
            print(f"\n🤝 CONCLUSION: WORKFLOWS ARE EQUIVALENT")
            print(f"   Both approaches deliver similar results")


if __name__ == "__main__":
    asyncio.run(main()) 
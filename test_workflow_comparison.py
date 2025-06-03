#!/usr/bin/env python3
"""
BOL Workflow Comparison: OLD vs NEW

Direct comparison between:
OLD WORKFLOW: Raw OCR Text → Sonnet 3.5
NEW WORKFLOW: Marker API (structured markdown) → Sonnet 3.5

Shows which approach delivers better extraction results.
"""

import asyncio
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


def calculate_extraction_score(data_dict: dict) -> tuple[int, int, float]:
    """Calculate extraction completeness score."""
    core_fields = ['bol_number', 'shipper_name', 'consignee_name', 'carrier_name', 'pro_number']
    additional_fields = ['pickup_date', 'delivery_date', 'commodity_description', 'weight', 'pieces', 'freight_charges']
    
    core_filled = sum(1 for field in core_fields if data_dict.get(field))
    additional_filled = sum(1 for field in additional_fields if data_dict.get(field))
    total_filled = core_filled + additional_filled
    total_possible = len(core_fields) + len(additional_fields)
    
    completeness = (total_filled / total_possible) * 100 if total_possible > 0 else 0
    return core_filled, additional_filled, completeness


async def extract_with_raw_ocr_workflow(file_content: bytes, filename: str) -> tuple[dict, float]:
    """OLD WORKFLOW: Extract using raw OCR text + Sonnet 3.5."""
    try:
        extractor = EnhancedBOLExtractor()
        
        # Step 1: Get raw OCR text (simulated - using Marker without use_llm)
        async with DatalabMarkerClient() as marker:
            ocr_result = await marker.process_document(
                file_content=file_content,
                filename=filename,
                mime_type="image/jpeg",
                language="English",
                force_ocr=True,
                use_llm=False,  # RAW OCR only - no LLM structure enhancement
                output_format="markdown"
            )
        
        if not ocr_result.success:
            return {}, 0.0
            
        # Step 2: Send raw text to Sonnet 3.5 
        raw_text = ocr_result.markdown_content
        extracted_dict, confidence = await extractor.extract_fields_from_markdown(
            markdown_content=raw_text,
            marker_metadata={"workflow": "raw_ocr"}
        )
        
        return extracted_dict, confidence
        
    except Exception as e:
        print(f"   ❌ OLD workflow failed: {e}")
        return {}, 0.0


async def extract_with_enhanced_workflow(file_content: bytes, filename: str) -> tuple[dict, float]:
    """NEW WORKFLOW: Extract using Marker API + Sonnet 3.5."""
    try:
        extractor = EnhancedBOLExtractor()
        
        # Complete enhanced workflow
        extracted_data, confidence, needs_review = await extractor.extract_bol_fields_enhanced(
            file_content=file_content,
            filename=filename,
            mime_type="image/jpeg"
        )
        
        # Convert to dict for comparison
        extracted_dict = extracted_data.dict() if hasattr(extracted_data, 'dict') else extracted_data.__dict__
        
        return extracted_dict, confidence
        
    except Exception as e:
        print(f"   ❌ NEW workflow failed: {e}")
        return {}, 0.0


async def compare_single_document(filepath: Path):
    """Compare both workflows on a single document."""
    
    print(f"\n" + "="*70)
    print(f"📄 COMPARING: {filepath.name}")
    print("="*70)
    
    # Read document
    try:
        with open(filepath, 'rb') as f:
            file_content = f.read()
        print(f"📂 Document loaded: {len(file_content):,} bytes")
    except Exception as e:
        print(f"❌ Failed to read {filepath.name}: {e}")
        return None
    
    # Run both workflows in parallel
    print("\n🔄 RUNNING BOTH WORKFLOWS...")
    old_task = extract_with_raw_ocr_workflow(file_content, filepath.name)
    new_task = extract_with_enhanced_workflow(file_content, filepath.name)
    
    old_result, new_result = await asyncio.gather(old_task, new_task, return_exceptions=True)
    
    # Handle any exceptions
    if isinstance(old_result, Exception):
        print(f"   ❌ OLD workflow error: {old_result}")
        old_result = ({}, 0.0)
    if isinstance(new_result, Exception):
        print(f"   ❌ NEW workflow error: {new_result}")
        new_result = ({}, 0.0)
        
    old_data, old_confidence = old_result
    new_data, new_confidence = new_result
    
    # Calculate scores
    old_core, old_additional, old_completeness = calculate_extraction_score(old_data)
    new_core, new_additional, new_completeness = calculate_extraction_score(new_data)
    
    # Display comparison
    print(f"\n📊 WORKFLOW COMPARISON RESULTS:")
    print(f"┌{'─'*34}┬{'─'*16}┬{'─'*16}┐")
    print(f"│{'Metric':<34}│{'OLD (Raw OCR)':<16}│{'NEW (Enhanced)':<16}│")
    print(f"├{'─'*34}┼{'─'*16}┼{'─'*16}┤")
    print(f"│{'Confidence Score':<34}│{old_confidence*100:>13.1f}%│{new_confidence*100:>13.1f}%│")
    print(f"│{'Core Fields (5 total)':<34}│{old_core:>13}/5│{new_core:>13}/5│")
    print(f"│{'Additional Fields (6 total)':<34}│{old_additional:>13}/6│{new_additional:>13}/6│")
    print(f"│{'Overall Completeness':<34}│{old_completeness:>13.1f}%│{new_completeness:>13.1f}%│")
    print(f"└{'─'*34}┴{'─'*16}┴{'─'*16}┘")
    
    # Determine winner
    old_score = old_confidence * 0.5 + (old_completeness / 100) * 0.5
    new_score = new_confidence * 0.5 + (new_completeness / 100) * 0.5
    
    if new_score > old_score:
        winner = "🟢 NEW WORKFLOW WINS!"
        improvement = ((new_score - old_score) / old_score * 100) if old_score > 0 else float('inf')
        print(f"\n🏆 {winner}")
        if improvement != float('inf'):
            print(f"   📈 Improvement: {improvement:.1f}% better overall performance")
        else:
            print(f"   📈 Massive improvement from baseline")
    elif old_score > new_score:
        winner = "🔴 OLD WORKFLOW WINS"
        decline = ((old_score - new_score) / old_score * 100) if old_score > 0 else 0
        print(f"\n🏆 {winner}")
        print(f"   📉 Decline: {decline:.1f}% worse performance")
    else:
        winner = "🟡 TIE"
        print(f"\n🏆 {winner} - Both workflows performed equally")
    
    # Field-by-field comparison for key fields
    key_fields = ['bol_number', 'shipper_name', 'consignee_name', 'carrier_name', 'weight']
    print(f"\n🔍 KEY FIELD COMPARISON:")
    for field in key_fields:
        old_val = old_data.get(field, "❌ Missing")
        new_val = new_data.get(field, "❌ Missing")
        
        if old_val and new_val and old_val != "❌ Missing" and new_val != "❌ Missing":
            status = "✅ Both found"
        elif new_val and new_val != "❌ Missing":
            status = "🟢 NEW found"
        elif old_val and old_val != "❌ Missing":
            status = "🔴 OLD found"
        else:
            status = "❌ Both missed"
            
        print(f"   {field:>16}: {status}")
    
    return {
        'filename': filepath.name,
        'old_confidence': old_confidence,
        'new_confidence': new_confidence,
        'old_completeness': old_completeness,
        'new_completeness': new_completeness,
        'old_score': old_score,
        'new_score': new_score,
        'winner': winner
    }


async def main():
    """Run the complete workflow comparison."""
    
    print("🔄 BOL WORKFLOW COMPARISON TEST")
    print("="*70)
    print("Comparing extraction performance:")
    print("  OLD: Raw OCR Text → Sonnet 3.5")
    print("  NEW: Marker API (structured) → Sonnet 3.5")
    print()
    
    # Find BOL files 
    bol_dir = Path("test_documents/bol")
    if not bol_dir.exists():
        print(f"❌ BOL directory not found: {bol_dir}")
        return
        
    bol_files = list(bol_dir.glob("*.jpg")) + list(bol_dir.glob("*.png")) + list(bol_dir.glob("*.pdf"))
    bol_files = [f for f in bol_files if f.name.startswith('BOL')]
    
    if not bol_files:
        print(f"❌ No BOL files found in {bol_dir}")
        return
        
    print(f"📁 Found {len(bol_files)} BOL files to compare")
    
    # Compare each document
    results = []
    for bol_file in sorted(bol_files):
        result = await compare_single_document(bol_file)
        if result:
            results.append(result)
    
    # Overall summary
    if results:
        print(f"\n" + "="*70)
        print("🎯 OVERALL COMPARISON SUMMARY")
        print("="*70)
        
        old_avg_conf = sum(r['old_confidence'] for r in results) / len(results)
        new_avg_conf = sum(r['new_confidence'] for r in results) / len(results)
        old_avg_comp = sum(r['old_completeness'] for r in results) / len(results)
        new_avg_comp = sum(r['new_completeness'] for r in results) / len(results)
        
        new_wins = sum(1 for r in results if "NEW" in r['winner'])
        old_wins = sum(1 for r in results if "OLD" in r['winner'])
        ties = sum(1 for r in results if "TIE" in r['winner'])
        
        print(f"\n📊 AGGREGATE PERFORMANCE:")
        print(f"┌{'─'*34}┬{'─'*16}┬{'─'*16}┐")
        print(f"│{'Average Metrics':<34}│{'OLD Workflow':<16}│{'NEW Workflow':<16}│")
        print(f"├{'─'*34}┼{'─'*16}┼{'─'*16}┤")
        print(f"│{'Confidence Score':<34}│{old_avg_conf*100:>13.1f}%│{new_avg_conf*100:>13.1f}%│")
        print(f"│{'Completeness':<34}│{old_avg_comp:>13.1f}%│{new_avg_comp:>13.1f}%│")
        print(f"└{'─'*34}┴{'─'*16}┴{'─'*16}┘")
        
        print(f"\n🏆 WIN/LOSS RECORD:")
        print(f"   🟢 NEW Workflow Wins: {new_wins}/{len(results)}")
        print(f"   🔴 OLD Workflow Wins: {old_wins}/{len(results)}")
        print(f"   🟡 Ties: {ties}/{len(results)}")
        
        if new_wins > old_wins:
            print(f"\n🎉 CONCLUSION: NEW WORKFLOW IS SUPERIOR!")
            conf_improvement = ((new_avg_conf - old_avg_conf) / old_avg_conf * 100) if old_avg_conf > 0 else 0
            comp_improvement = ((new_avg_comp - old_avg_comp) / old_avg_comp * 100) if old_avg_comp > 0 else 0
            print(f"   📈 Average confidence improvement: {conf_improvement:+.1f}%")
            print(f"   📈 Average completeness improvement: {comp_improvement:+.1f}%")
        elif old_wins > new_wins:
            print(f"\n🤔 CONCLUSION: OLD WORKFLOW PERFORMED BETTER")
            print(f"   Consider reviewing the new workflow implementation")
        else:
            print(f"\n🤝 CONCLUSION: BOTH WORKFLOWS EQUAL")
            print(f"   No significant difference detected")


if __name__ == "__main__":
    asyncio.run(main()) 
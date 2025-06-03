#!/usr/bin/env python3
"""
Lumper2 Workflow Comparison: OLD vs NEW

Focused comparison on lumper2 document between:
OLD WORKFLOW: Raw OCR Text → Sonnet 3.5
NEW WORKFLOW: Marker API (structured markdown) → Sonnet 3.5

Shows which approach delivers better lumper receipt extraction results.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Configure clean logging 
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.enhanced_lumper_extractor import EnhancedLumperExtractor
from app.services.ocr_clients.datalab_marker_client import DatalabMarkerClient


def calculate_lumper_score(data_dict: dict) -> tuple[int, int, float]:
    """Calculate lumper extraction completeness score."""
    core_fields = ['receipt_number', 'facility_name', 'driver_name', 'total_amount', 'service_date']
    additional_fields = ['trailer_number', 'carrier_name', 'po_number', 'start_time', 'end_time', 'hours_worked']
    
    core_filled = sum(1 for field in core_fields if data_dict.get(field))
    additional_filled = sum(1 for field in additional_fields if data_dict.get(field))
    total_filled = core_filled + additional_filled
    total_possible = len(core_fields) + len(additional_fields)
    
    completeness = (total_filled / total_possible) * 100 if total_possible > 0 else 0
    return core_filled, additional_filled, completeness


async def extract_with_old_workflow(file_content: bytes, filename: str, mime_type: str) -> tuple[dict, float]:
    """OLD WORKFLOW: Extract using raw OCR text + Sonnet 3.5."""
    try:
        extractor = EnhancedLumperExtractor()
        
        # Step 1: Get raw OCR text (using Marker without use_llm)
        async with DatalabMarkerClient() as marker:
            ocr_result = await marker.process_document(
                file_content=file_content,
                filename=filename,
                mime_type=mime_type,  # Use determined MIME type
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
            marker_metadata={"workflow": "old"}
        )
        
        return extracted_dict, confidence
        
    except Exception as e:
        print(f"   ❌ OLD workflow failed: {e}")
        return {}, 0.0


async def extract_with_new_workflow(file_content: bytes, filename: str, mime_type: str) -> tuple[dict, float]:
    """NEW WORKFLOW: Extract using Marker API + Sonnet 3.5."""
    try:
        extractor = EnhancedLumperExtractor()
        
        # Complete enhanced workflow
        extracted_data, confidence, needs_review = await extractor.extract_lumper_fields_enhanced(
            file_content=file_content,
            filename=filename,
            mime_type=mime_type  # Use determined MIME type
        )
        
        # Convert to dict for comparison
        extracted_dict = extracted_data.model_dump() if hasattr(extracted_data, 'model_dump') else extracted_data.__dict__
        
        return extracted_dict, confidence
        
    except Exception as e:
        print(f"   ❌ NEW workflow failed: {e}")
        return {}, 0.0


async def analyze_lumper2_detailed():
    """Detailed analysis of lumper2 document with both workflows."""
    
    print("🚛 LUMPER2 WORKFLOW COMPARISON ANALYSIS")
    print("="*80)
    print("Testing both workflows on lumper2 document:")
    print("  OLD: Raw OCR Text → Sonnet 3.5")
    print("  NEW: Marker API (structured) → Sonnet 3.5")
    print()
    
    # Find lumper2 document
    lumper_file = Path("test_documents/lumper/lumper2.webp")
    if not lumper_file.exists():
        # Try different extensions
        for ext in ['.jpg', '.png', '.pdf', '.jpeg']:
            alt_file = lumper_file.with_name(f"lumper2{ext}")
            if alt_file.exists():
                lumper_file = alt_file
                break
        else:
            print(f"❌ Lumper2 file not found. Tried: {lumper_file}")
            return
    
    print(f"📁 Found document: {lumper_file.name}")
    
    # Determine MIME type based on file extension
    if lumper_file.suffix.lower() == '.webp':
        mime_type = "image/webp"
    elif lumper_file.suffix.lower() in ['.jpg', '.jpeg']:
        mime_type = "image/jpeg"
    elif lumper_file.suffix.lower() == '.png':
        mime_type = "image/png"
    elif lumper_file.suffix.lower() == '.pdf':
        mime_type = "application/pdf"
    else:
        mime_type = "image/jpeg"  # fallback
    
    print(f"📂 MIME type: {mime_type}")
    
    # Read document
    with open(lumper_file, 'rb') as f:
        file_content = f.read()
    print(f"📂 Document loaded: {len(file_content):,} bytes\n")
    
    # ================== OLD WORKFLOW ANALYSIS ==================
    print("🔴 OLD WORKFLOW: Raw OCR Text → Sonnet 3.5")
    print("-" * 60)
    
    # Process with raw OCR
    async with DatalabMarkerClient() as marker:
        old_ocr_result = await marker.process_document(
            file_content=file_content,
            filename=lumper_file.name,
            mime_type=mime_type,
            language="English",
            force_ocr=True,
            use_llm=False,  # RAW OCR only
            output_format="markdown"
        )
    
    if old_ocr_result.success:
        print(f"📊 Raw OCR Result:")
        print(f"   Content length: {len(old_ocr_result.markdown_content):,} chars")
        print(f"   Tables detected: {len(old_ocr_result.get_tables())}")
        print(f"   Content preview: {old_ocr_result.markdown_content[:200]}...")
        
        # Extract with Sonnet 3.5
        extractor = EnhancedLumperExtractor()
        old_extracted, old_confidence = await extractor.extract_fields_from_markdown(
            markdown_content=old_ocr_result.markdown_content,
            marker_metadata={"workflow": "old"}
        )
        
        print(f"\n🎯 OLD Workflow Results:")
        print(f"   Confidence: {old_confidence:.1%}")
        print(f"   Receipt Number: {old_extracted.get('receipt_number', 'Missing')}")
        print(f"   Facility: {old_extracted.get('facility_name', 'Missing')}")
        print(f"   Driver: {old_extracted.get('driver_name', 'Missing')}")
        print(f"   Total Amount: {old_extracted.get('total_amount', 'Missing')}")
        print(f"   Service Date: {old_extracted.get('service_date', 'Missing')}")
        print(f"   Trailer: {old_extracted.get('trailer_number', 'Missing')}")
        
        # Calculate completeness
        old_core, old_additional, old_completeness = calculate_lumper_score(old_extracted)
        print(f"   Core fields: {old_core}/5 ({old_core/5*100:.1f}%)")
        print(f"   Additional fields: {old_additional}/6 ({old_additional/6*100:.1f}%)")
        print(f"   Overall completeness: {old_completeness:.1f}%")
    else:
        print(f"❌ OLD workflow failed: {old_ocr_result.error}")
        old_extracted, old_confidence = {}, 0.0
        old_core, old_additional, old_completeness = 0, 0, 0.0
    
    print()
    
    # ================== NEW WORKFLOW ANALYSIS ==================
    print("🟢 NEW WORKFLOW: Marker API (structured) → Sonnet 3.5")
    print("-" * 60)
    
    # Process with enhanced Marker API
    async with DatalabMarkerClient() as marker:
        new_ocr_result = await marker.process_document(
            file_content=file_content,
            filename=lumper_file.name,
            mime_type=mime_type,  # Use determined MIME type
            language="English",
            force_ocr=True,
            use_llm=True,  # ENHANCED with LLM structure
            output_format="markdown"
        )
    
    if new_ocr_result.success:
        print(f"📊 Enhanced Marker Result:")
        print(f"   Content length: {len(new_ocr_result.markdown_content):,} chars")
        print(f"   Tables detected: {len(new_ocr_result.get_tables())}")
        print(f"   Content preview: {new_ocr_result.markdown_content[:200]}...")
        
        # Extract with Sonnet 3.5
        extractor = EnhancedLumperExtractor()
        new_extracted, new_confidence = await extractor.extract_fields_from_markdown(
            markdown_content=new_ocr_result.markdown_content,
            marker_metadata={"workflow": "new"}
        )
        
        print(f"\n🎯 NEW Workflow Results:")
        print(f"   Confidence: {new_confidence:.1%}")
        print(f"   Receipt Number: {new_extracted.get('receipt_number', 'Missing')}")
        print(f"   Facility: {new_extracted.get('facility_name', 'Missing')}")
        print(f"   Driver: {new_extracted.get('driver_name', 'Missing')}")
        print(f"   Total Amount: {new_extracted.get('total_amount', 'Missing')}")
        print(f"   Service Date: {new_extracted.get('service_date', 'Missing')}")
        print(f"   Trailer: {new_extracted.get('trailer_number', 'Missing')}")
        
        # Calculate completeness
        new_core, new_additional, new_completeness = calculate_lumper_score(new_extracted)
        print(f"   Core fields: {new_core}/5 ({new_core/5*100:.1f}%)")
        print(f"   Additional fields: {new_additional}/6 ({new_additional/6*100:.1f}%)")
        print(f"   Overall completeness: {new_completeness:.1f}%")
    else:
        print(f"❌ NEW workflow failed: {new_ocr_result.error}")
        new_extracted, new_confidence = {}, 0.0
        new_core, new_additional, new_completeness = 0, 0, 0.0
    
    print()
    
    # ================== DETAILED COMPARISON ==================
    print("⚖️  DETAILED WORKFLOW COMPARISON")
    print("="*80)
    
    # Comparison table
    print(f"📊 PERFORMANCE METRICS:")
    print(f"┌{'─'*35}┬{'─'*18}┬{'─'*18}┬{'─'*10}┐")
    print(f"│{'Metric':<35}│{'OLD Workflow':<18}│{'NEW Workflow':<18}│{'Winner':<10}│")
    print(f"├{'─'*35}┼{'─'*18}┼{'─'*18}┼{'─'*10}┤")
    
    # Confidence comparison
    conf_winner = "🟢 NEW" if new_confidence > old_confidence else "🔴 OLD" if old_confidence > new_confidence else "🟡 TIE"
    print(f"│{'Confidence Score':<35}│{old_confidence*100:>15.1f}%│{new_confidence*100:>15.1f}%│{conf_winner:<10}│")
    
    # Core fields comparison
    core_winner = "🟢 NEW" if new_core > old_core else "🔴 OLD" if old_core > new_core else "🟡 TIE"
    print(f"│{'Core Fields (5 total)':<35}│{old_core:>15}/5│{new_core:>15}/5│{core_winner:<10}│")
    
    # Additional fields comparison
    add_winner = "🟢 NEW" if new_additional > old_additional else "🔴 OLD" if old_additional > new_additional else "🟡 TIE"
    print(f"│{'Additional Fields (6 total)':<35}│{old_additional:>15}/6│{new_additional:>15}/6│{add_winner:<10}│")
    
    # Overall completeness comparison
    comp_winner = "🟢 NEW" if new_completeness > old_completeness else "🔴 OLD" if old_completeness > new_completeness else "🟡 TIE"
    print(f"│{'Overall Completeness':<35}│{old_completeness:>15.1f}%│{new_completeness:>15.1f}%│{comp_winner:<10}│")
    
    print(f"└{'─'*35}┴{'─'*18}┴{'─'*18}┴{'─'*10}┘")
    
    # Field-by-field analysis
    print(f"\n🔍 FIELD-BY-FIELD ANALYSIS:")
    key_fields = ['receipt_number', 'facility_name', 'driver_name', 'total_amount', 'service_date', 'trailer_number']
    
    for field in key_fields:
        old_val = old_extracted.get(field, "Missing")
        new_val = new_extracted.get(field, "Missing")
        
        if old_val != "Missing" and new_val != "Missing":
            if str(old_val) == str(new_val):
                status = "✅ Both (same)"
            else:
                status = "⚡ Both (differ)"
        elif new_val != "Missing":
            status = "🟢 NEW only"
        elif old_val != "Missing":
            status = "🔴 OLD only"
        else:
            status = "❌ Both missed"
            
        print(f"   {field:>15}: {status}")
        if old_val != "Missing" or new_val != "Missing":
            print(f"                    OLD: {old_val}")
            print(f"                    NEW: {new_val}")
    
    # Calculate overall score
    old_score = old_confidence * 0.6 + (old_completeness / 100) * 0.4
    new_score = new_confidence * 0.6 + (new_completeness / 100) * 0.4
    
    print(f"\n🏆 OVERALL ASSESSMENT:")
    print(f"   OLD workflow score: {old_score:.3f} (confidence: {old_confidence:.1%}, completeness: {old_completeness:.1f}%)")
    print(f"   NEW workflow score: {new_score:.3f} (confidence: {new_confidence:.1%}, completeness: {new_completeness:.1f}%)")
    
    if new_score > old_score:
        improvement = ((new_score - old_score) / old_score * 100) if old_score > 0 else float('inf')
        print(f"\n🎉 WINNER: NEW WORKFLOW!")
        if improvement != float('inf'):
            print(f"   📈 Performance improvement: {improvement:.1f}%")
        else:
            print(f"   📈 Massive improvement from baseline")
        
        print(f"\n✨ KEY ADVANTAGES OF NEW WORKFLOW:")
        if new_confidence > old_confidence:
            print(f"   • Higher confidence: {new_confidence:.1%} vs {old_confidence:.1%}")
        if new_completeness > old_completeness:
            print(f"   • Better data extraction: {new_completeness:.1f}% vs {old_completeness:.1f}%")
        if new_core > old_core:
            print(f"   • More core fields found: {new_core} vs {old_core}")
            
    elif old_score > new_score:
        decline = ((old_score - new_score) / old_score * 100) if old_score > 0 else 0
        print(f"\n🤔 WINNER: OLD WORKFLOW")
        print(f"   📉 NEW workflow declined by: {decline:.1f}%")
        
        print(f"\n🔍 WHY OLD WORKFLOW PERFORMED BETTER:")
        if old_confidence > new_confidence:
            print(f"   • Higher confidence: {old_confidence:.1%} vs {new_confidence:.1%}")
        if old_completeness > new_completeness:
            print(f"   • Better data extraction: {old_completeness:.1f}% vs {new_completeness:.1f}%")
        if old_core > new_core:
            print(f"   • More core fields found: {old_core} vs {new_core}")
    else:
        print(f"\n🤝 RESULT: TIE")
        print(f"   Both workflows performed equally well")
    
    print(f"\n📋 RECOMMENDATION:")
    if new_score > old_score:
        print(f"   ✅ Use the NEW workflow (Marker API + Sonnet 3.5) for lumper processing")
        print(f"   📈 Expected benefits: Higher accuracy and more complete data extraction")
    elif old_score > new_score:
        print(f"   ⚠️  Consider sticking with OLD workflow or investigating NEW workflow issues")
        print(f"   🔧 May need prompt tuning or parameter adjustment for lumper documents")
    else:
        print(f"   🔄 Both workflows are equivalent - choose based on other factors (speed, cost, etc.)")


if __name__ == "__main__":
    asyncio.run(analyze_lumper2_detailed()) 
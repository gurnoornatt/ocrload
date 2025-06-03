#!/usr/bin/env python3
"""
Image Preprocessing Test

Demonstrates the image preprocessing capabilities:
- Loads a test document
- Shows preprocessing steps applied
- Compares before/after file sizes and quality metrics
- Tests the complete enhanced workflow with preprocessing
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.image_preprocessor import ImagePreprocessor
from app.services.ocr_clients.datalab_marker_client import DatalabMarkerClient
from app.services.enhanced_bol_extractor import EnhancedBOLExtractor


async def test_image_preprocessing():
    """Test image preprocessing on sample documents."""
    
    print("🖼️  IMAGE PREPROCESSING TEST")
    print("="*60)
    
    # Find a test document
    test_file = None
    test_dirs = ["test_documents/bol", "test_documents/lumper", "test_documents/invoices"]
    
    for test_dir in test_dirs:
        test_path = Path(test_dir)
        if test_path.exists():
            for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                files = list(test_path.glob(ext))
                if files:
                    test_file = files[0]
                    break
            if test_file:
                break
    
    if not test_file:
        print("❌ No test image files found")
        return
    
    print(f"📁 Found test document: {test_file.name}")
    
    # Load the original image
    with open(test_file, 'rb') as f:
        original_bytes = f.read()
    
    original_size = len(original_bytes)
    print(f"📊 Original file size: {original_size:,} bytes")
    
    # Determine MIME type
    if test_file.suffix.lower() in ['.jpg', '.jpeg']:
        mime_type = "image/jpeg"
    elif test_file.suffix.lower() == '.png':
        mime_type = "image/png"
    elif test_file.suffix.lower() == '.webp':
        mime_type = "image/webp"
    else:
        mime_type = "image/jpeg"
    
    print(f"📂 MIME type: {mime_type}")
    print()
    
    # ================== TEST 1: PREPROCESSING DISABLED ==================
    print("🔴 TEST 1: Preprocessing DISABLED")
    print("-" * 40)
    
    # Create preprocessor with preprocessing disabled
    config_disabled = {'enabled': False}
    preprocessor_disabled = ImagePreprocessor(config_disabled)
    
    processed_bytes_disabled, metadata_disabled = preprocessor_disabled.preprocess_image(
        image_bytes=original_bytes,
        filename=test_file.name,
        mime_type=mime_type
    )
    
    print(f"📊 Result: {metadata_disabled}")
    print(f"📏 Size: {len(processed_bytes_disabled):,} bytes (same as original)")
    print()
    
    # ================== TEST 2: PREPROCESSING ENABLED ==================
    print("🟢 TEST 2: Preprocessing ENABLED")
    print("-" * 40)
    
    # Create preprocessor with full preprocessing enabled
    config_enabled = {
        'enabled': True,
        'deskew': True,
        'color_correction': True,
        'noise_reduction': True,
        'sharpening': True,
        'contrast_enhancement': True,
        'resolution_enhancement': True,
        'shadow_removal': True,
        'target_dpi': 300,
        'max_dimension': 3000,
        'quality': 95
    }
    
    preprocessor_enabled = ImagePreprocessor(config_enabled)
    
    processed_bytes_enabled, metadata_enabled = preprocessor_enabled.preprocess_image(
        image_bytes=original_bytes,
        filename=test_file.name,
        mime_type=mime_type
    )
    
    print(f"📊 Processing steps applied:")
    if 'processing_steps' in metadata_enabled:
        for step in metadata_enabled['processing_steps']:
            print(f"   ✓ {step}")
    
    print(f"\n📏 Size comparison:")
    print(f"   Original: {original_size:,} bytes")
    print(f"   Processed: {len(processed_bytes_enabled):,} bytes")
    
    if 'size_reduction' in metadata_enabled:
        ratio = metadata_enabled['size_reduction']
        if ratio > 1:
            print(f"   📉 Compressed by {((ratio-1)*100):.1f}%")
        elif ratio < 1:
            print(f"   📈 Enlarged by {((1-ratio)*100):.1f}%")
        else:
            print(f"   ➡️  Size unchanged")
    
    print(f"\n📐 Resolution enhancement:")
    if 'original_size' in metadata_enabled and 'final_size' in metadata_enabled:
        orig_w, orig_h = metadata_enabled['original_size']
        final_w, final_h = metadata_enabled['final_size']
        print(f"   Original: {orig_w}×{orig_h} pixels")
        print(f"   Enhanced: {final_w}×{final_h} pixels")
        
        if final_w > orig_w or final_h > orig_h:
            scale = max(final_w/orig_w, final_h/orig_h)
            print(f"   📈 Upscaled by {scale:.2f}x for better OCR")
    
    print()
    
    # ================== TEST 3: INTEGRATED WORKFLOW ==================
    print("🔄 TEST 3: Complete Enhanced Workflow with Preprocessing")
    print("-" * 40)
    
    # Test with DatalabMarkerClient that has preprocessing enabled
    async with DatalabMarkerClient(preprocessing_enabled=True) as marker_client:
        print("🚀 Processing with enhanced Marker API + preprocessing...")
        
        result = await marker_client.process_document(
            file_content=original_bytes,
            filename=test_file.name,
            mime_type=mime_type,
            language="English",
            force_ocr=True,
            use_llm=True,
            output_format="markdown"
        )
        
        if result.success:
            print(f"✅ Enhanced processing successful!")
            print(f"📄 Content length: {len(result.markdown_content):,} characters")
            print(f"📊 Tables detected: {len(result.get_tables())}")
            print(f"⏱️  Processing time: {result.processing_time:.2f} seconds")
            
            # Check if preprocessing metadata is included
            if 'image_preprocessing' in result.metadata:
                preprocessing_info = result.metadata['image_preprocessing']
                print(f"🖼️  Image preprocessing applied: {preprocessing_info.get('preprocessing', 'unknown')}")
                
                if 'processing_steps' in preprocessing_info:
                    print(f"   Steps: {len(preprocessing_info['processing_steps'])}")
                    for step in preprocessing_info['processing_steps']:
                        print(f"      • {step}")
            
            # Show content preview
            print(f"\n📋 Content preview:")
            preview = result.markdown_content[:300].replace('\n', ' ')
            print(f"   {preview}...")
            
        else:
            print(f"❌ Enhanced processing failed: {result.error}")
    
    print()
    
    # ================== TEST 4: WORKFLOW COMPARISON ==================
    print("⚖️  TEST 4: Preprocessing Impact on OCR Quality")
    print("-" * 40)
    
    print("🔄 Testing OCR with and without preprocessing...")
    
    # Test without preprocessing
    async with DatalabMarkerClient(preprocessing_enabled=False) as marker_no_prep:
        result_no_prep = await marker_no_prep.process_document(
            file_content=original_bytes,
            filename=test_file.name,
            mime_type=mime_type,
            language="English",
            force_ocr=True,
            use_llm=True,
            output_format="markdown"
        )
    
    # Test with preprocessing 
    async with DatalabMarkerClient(preprocessing_enabled=True) as marker_with_prep:
        result_with_prep = await marker_with_prep.process_document(
            file_content=original_bytes,
            filename=test_file.name,
            mime_type=mime_type,
            language="English",
            force_ocr=True,
            use_llm=True,
            output_format="markdown"
        )
    
    # Compare results
    print(f"\n📊 OCR QUALITY COMPARISON:")
    print(f"┌{'─'*25}┬{'─'*15}┬{'─'*15}┬{'─'*10}┐")
    print(f"│{'Metric':<25}│{'No Preprocess':<15}│{'With Preprocess':<15}│{'Winner':<10}│")
    print(f"├{'─'*25}┼{'─'*15}┼{'─'*15}┼{'─'*10}┤")
    
    # Content length comparison
    len_no_prep = len(result_no_prep.markdown_content) if result_no_prep.success else 0
    len_with_prep = len(result_with_prep.markdown_content) if result_with_prep.success else 0
    winner_length = "🟢 Prep" if len_with_prep > len_no_prep else "🔴 No Prep" if len_no_prep > len_with_prep else "🟡 Tie"
    print(f"│{'Content Length':<25}│{len_no_prep:>12,}│{len_with_prep:>12,}│{winner_length:<10}│")
    
    # Tables detected comparison
    tables_no_prep = len(result_no_prep.get_tables()) if result_no_prep.success else 0
    tables_with_prep = len(result_with_prep.get_tables()) if result_with_prep.success else 0
    winner_tables = "🟢 Prep" if tables_with_prep > tables_no_prep else "🔴 No Prep" if tables_no_prep > tables_with_prep else "🟡 Tie"
    print(f"│{'Tables Detected':<25}│{tables_no_prep:>15}│{tables_with_prep:>15}│{winner_tables:<10}│")
    
    # Processing time comparison
    time_no_prep = result_no_prep.processing_time if result_no_prep.success else 0
    time_with_prep = result_with_prep.processing_time if result_with_prep.success else 0
    winner_time = "🟢 Prep" if time_with_prep < time_no_prep else "🔴 No Prep" if time_no_prep < time_with_prep else "🟡 Tie"
    print(f"│{'Processing Time (s)':<25}│{time_no_prep:>15.2f}│{time_with_prep:>15.2f}│{winner_time:<10}│")
    
    print(f"└{'─'*25}┴{'─'*15}┴{'─'*15}┴{'─'*10}┘")
    
    # Overall recommendation
    improvements = []
    if len_with_prep > len_no_prep:
        improvements.append(f"Content extraction improved by {((len_with_prep/len_no_prep-1)*100):.1f}%")
    if tables_with_prep > tables_no_prep:
        improvements.append(f"Table detection improved by {tables_with_prep-tables_no_prep} tables")
    
    print(f"\n🏆 PREPROCESSING IMPACT:")
    if improvements:
        print(f"   ✅ Positive impact detected:")
        for improvement in improvements:
            print(f"      • {improvement}")
        print(f"   📈 Recommendation: Keep preprocessing ENABLED")
    else:
        print(f"   ➡️  Minimal impact on this document")
        print(f"   🤔 Consider testing on more challenging documents")
    
    print(f"\n✨ PREPROCESSING FEATURES APPLIED:")
    print(f"   🔄 Auto-rotation and deskewing")
    print(f"   🌈 Color correction and contrast enhancement") 
    print(f"   🔇 Noise reduction")
    print(f"   ✨ Image sharpening")
    print(f"   📐 Resolution enhancement to 300 DPI")
    print(f"   💡 Shadow removal and lighting correction")


if __name__ == "__main__":
    asyncio.run(test_image_preprocessing()) 
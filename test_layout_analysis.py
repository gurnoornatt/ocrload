#!/usr/bin/env python3
"""
Layout Analysis Integration Test

Demonstrates the Datalab Layout API integration for semantic document structure detection.
Shows how layout understanding enhances OCR results for freight documents.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.ocr_clients.datalab_layout_client import DatalabLayoutClient
from app.services.ocr_clients.unified_ocr_client import UnifiedOCRClient


def print_layout_analysis(layout_result):
    """Print layout analysis results in a structured format."""
    
    print(f"\n📐 LAYOUT ANALYSIS RESULTS")
    print("=" * 50)
    print(f"✅ Success: {layout_result.success}")
    print(f"📄 Pages: {layout_result.page_count}")
    print(f"⏱️  Processing Time: {layout_result.processing_time:.2f}s")
    
    if layout_result.error:
        print(f"❌ Error: {layout_result.error}")
        return
    
    for i, page in enumerate(layout_result.pages):
        print(f"\n📄 PAGE {page.page}")
        print("-" * 30)
        print(f"🔍 Regions Detected: {len(page.bboxes)}")
        
        # Group regions by type
        region_types = {}
        for bbox in page.bboxes:
            if bbox.label not in region_types:
                region_types[bbox.label] = []
            region_types[bbox.label].append(bbox)
        
        # Display region summary
        for region_type, bboxes in region_types.items():
            print(f"   {region_type}: {len(bboxes)} regions")
        
        # Show reading order
        print(f"\n📖 READING ORDER:")
        for bbox in page.get_reading_order():
            x1, y1, x2, y2 = bbox.bbox
            width = x2 - x1
            height = y2 - y1
            print(f"   {bbox.position:2d}. {bbox.label:15s} [{width:4.0f}x{height:4.0f}] at ({x1:4.0f},{y1:4.0f})")
        
        # Highlight important regions
        tables = page.get_regions_by_type("Table")
        headers = [bbox for bbox in page.bboxes if bbox.label in ["Section-header", "Title"]]
        
        if tables:
            print(f"\n📊 TABLES DETECTED: {len(tables)}")
            for i, table in enumerate(tables):
                x1, y1, x2, y2 = table.bbox
                print(f"   Table {i+1}: {x2-x1:.0f}x{y2-y1:.0f} at ({x1:.0f},{y1:.0f})")
        
        if headers:
            print(f"\n📋 HEADERS DETECTED: {len(headers)}")
            for i, header in enumerate(headers):
                x1, y1, x2, y2 = header.bbox
                print(f"   {header.label}: {x2-x1:.0f}x{y2-y1:.0f} at ({x1:.0f},{y1:.0f})")


async def test_layout_analysis():
    """Test layout analysis on a real lumper receipt document."""
    
    print("🧾 TESTING LAYOUT ANALYSIS ON LUMPER RECEIPTS")
    print("=" * 60)
    
    # Find test documents
    test_dir = Path("test_documents/lumper")
    if not test_dir.exists():
        print(f"❌ Test directory not found: {test_dir}")
        return
    
    # Get PNG files
    png_files = list(test_dir.glob("*.png"))
    if not png_files:
        print(f"❌ No PNG files found in {test_dir}")
        return
    
    # Test with first PNG file
    test_file = png_files[0]
    print(f"📄 Testing with: {test_file.name}")
    
    # Read file content
    with open(test_file, "rb") as f:
        file_content = f.read()
    
    print(f"📦 File size: {len(file_content):,} bytes")
    
    # Test Layout Analysis
    try:
        async with DatalabLayoutClient() as layout_client:
            print(f"\n🔄 Running layout analysis...")
            layout_result = await layout_client.analyze_layout(
                file_content=file_content,
                filename=test_file.name,
                mime_type="image/png"
            )
            
            print_layout_analysis(layout_result)
            
    except Exception as e:
        print(f"💥 Layout analysis failed: {e}")
        return layout_result
    
    return layout_result


async def test_combined_ocr_layout():
    """Test combined OCR + Layout analysis to show enhanced understanding."""
    
    print(f"\n\n🔬 TESTING COMBINED OCR + LAYOUT ANALYSIS")
    print("=" * 60)
    
    # Find test documents
    test_dir = Path("test_documents/lumper")
    png_files = list(test_dir.glob("*.png"))
    if not png_files:
        return
    
    test_file = png_files[0]
    
    # Read file content
    with open(test_file, "rb") as f:
        file_content = f.read()
    
    print(f"📄 Processing: {test_file.name}")
    
    # Initialize clients
    layout_client = DatalabLayoutClient()
    ocr_client = UnifiedOCRClient()
    
    try:
        # Run both analyses concurrently
        print(f"🔄 Running OCR + Layout analysis in parallel...")
        
        layout_task = layout_client.analyze_layout(
            file_content=file_content,
            filename=test_file.name, 
            mime_type="image/png"
        )
        
        ocr_task = ocr_client.process_file_content(
            file_content=file_content,
            filename=test_file.name,
            mime_type="image/png"
        )
        
        async with layout_client, ocr_client:
            layout_result, ocr_result = await asyncio.gather(layout_task, ocr_task)
        
        # Display combined results
        print(f"\n📊 COMBINED ANALYSIS RESULTS")
        print("=" * 50)
        
        # OCR Summary
        print(f"🔍 OCR Results:")
        print(f"   Text extracted: {len(ocr_result.get('full_text', ''))} characters")
        print(f"   Confidence: {ocr_result.get('average_confidence', 0):.1%}")
        print(f"   Lines: {sum(len(page.get('text_lines', [])) for page in ocr_result.get('pages', []))}")
        
        # Layout Summary 
        print(f"\n📐 Layout Results:")
        print(f"   Regions detected: {sum(len(page.bboxes) for page in layout_result.pages)}")
        print(f"   Tables: {len(layout_result.get_all_tables())}")
        print(f"   Headers: {len(layout_result.get_all_headers())}")
        
        # Show layout structure
        if layout_result.success and layout_result.pages:
            page = layout_result.pages[0]
            region_counts = {}
            for bbox in page.bboxes:
                region_counts[bbox.label] = region_counts.get(bbox.label, 0) + 1
            
            print(f"\n🏗️  Document Structure:")
            for label, count in sorted(region_counts.items()):
                print(f"   {label}: {count}")
        
        # Demonstrate enhanced extraction potential
        print(f"\n💡 ENHANCED EXTRACTION OPPORTUNITIES:")
        
        tables = layout_result.get_all_tables()
        if tables:
            print(f"   ✅ {len(tables)} table(s) detected - can extract structured data")
        else:
            print(f"   ℹ️  No tables detected - standard text extraction")
        
        headers = layout_result.get_all_headers()  
        if headers:
            print(f"   ✅ {len(headers)} header(s) detected - can identify document sections")
        else:
            print(f"   ℹ️  No headers detected - document may be unstructured")
        
        # Show specific region information for freight documents
        if layout_result.pages:
            page = layout_result.pages[0]
            
            # Look for patterns relevant to freight documents
            list_items = page.get_regions_by_type("List-item")
            if list_items:
                print(f"   ✅ {len(list_items)} list item(s) - potential service details or charges")
            
            figures = page.get_regions_by_type("Figure")
            if figures:
                print(f"   ✅ {len(figures)} figure(s) - potential signatures or stamps")
            
            captions = page.get_regions_by_type("Caption")
            if captions:
                print(f"   ✅ {len(captions)} caption(s) - potential labels or instructions")
        
        return layout_result, ocr_result
        
    except Exception as e:
        print(f"💥 Combined analysis failed: {e}")
        return None, None


async def main():
    """Run layout analysis tests."""
    
    # Check API key
    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ DATALAB_API_KEY not found in environment")
        print("   Set your API key to test layout analysis")
        return
    
    print("🚀 DATALAB LAYOUT API INTEGRATION TEST")
    print("=" * 60)
    print("This test demonstrates semantic layout detection for freight documents")
    print("showing how layout understanding enhances OCR extraction.\n")
    
    # Test 1: Basic layout analysis
    layout_result = await test_layout_analysis()
    
    # Test 2: Combined OCR + Layout
    await test_combined_ocr_layout()
    
    print(f"\n🎯 INTEGRATION ASSESSMENT")
    print("=" * 40)
    
    if layout_result and layout_result.success:
        print("✅ Layout API integration successful!")
        print("✅ Ready to enhance document processing pipeline")
        
        regions_count = sum(len(page.bboxes) for page in layout_result.pages)
        tables_count = len(layout_result.get_all_tables())
        headers_count = len(layout_result.get_all_headers())
        
        print(f"\n📈 Value Assessment:")
        print(f"   📊 Structural understanding: {regions_count} regions detected")
        if tables_count > 0:
            print(f"   ✅ Table detection: {tables_count} tables found (critical for invoices/BOLs)")
        if headers_count > 0:
            print(f"   ✅ Header detection: {headers_count} headers found (document organization)")
        
        print(f"\n🔮 Next Steps:")
        print(f"   1. Integrate with existing OCR pipeline")
        print(f"   2. Use layout context to improve AI field extraction")
        print(f"   3. Implement region-specific processing strategies")
        print(f"   4. Add layout-aware confidence scoring")
        
    else:
        print("❌ Layout API integration needs attention")
        print("   Check API key and network connectivity")


if __name__ == "__main__":
    asyncio.run(main()) 
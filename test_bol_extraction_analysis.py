#!/usr/bin/env python3
"""
BOL Layout Analysis Test

Tests the Datalab Layout API on complex Bill of Lading documents to demonstrate 
semantic layout understanding for freight document processing.
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


def analyze_bol_layout(layout_result, filename):
    """Analyze layout results specifically for BOL document patterns."""
    
    print(f"\n📋 BOL LAYOUT ANALYSIS: {filename}")
    print("=" * 60)
    
    if not layout_result.success:
        print(f"❌ Layout analysis failed: {layout_result.error}")
        return
    
    print(f"✅ Successfully analyzed in {layout_result.processing_time:.2f}s")
    print(f"📄 Pages: {layout_result.page_count}")
    
    total_regions = sum(len(page.bboxes) for page in layout_result.pages)
    print(f"🔍 Total regions detected: {total_regions}")
    
    # Analyze document structure for BOL-specific patterns
    tables = layout_result.get_all_tables()
    headers = layout_result.get_all_headers()
    
    print(f"\n🏗️  DOCUMENT STRUCTURE ANALYSIS:")
    
    # Group all regions by type across all pages
    all_regions = {}
    for page in layout_result.pages:
        for bbox in page.bboxes:
            if bbox.label not in all_regions:
                all_regions[bbox.label] = []
            all_regions[bbox.label].append(bbox)
    
    # Display region summary
    for label, regions in sorted(all_regions.items()):
        print(f"   {label}: {len(regions)} regions")
    
    # BOL-specific analysis
    print(f"\n📊 BOL-SPECIFIC INSIGHTS:")
    
    if tables:
        print(f"   ✅ {len(tables)} TABLE(S) DETECTED")
        print(f"      → Critical for: Shipment details, charges, item descriptions")
        for i, table in enumerate(tables):
            x1, y1, x2, y2 = table.bbox
            area = (x2 - x1) * (y2 - y1)
            print(f"      → Table {i+1}: {x2-x1:.0f}×{y2-y1:.0f} (area: {area:,.0f})")
    else:
        print(f"   ⚠️  NO TABLES DETECTED - May indicate:")
        print(f"      → Non-standard BOL format")
        print(f"      → Image quality issues")
        print(f"      → Document may be primarily text-based")
    
    if headers:
        print(f"\n   ✅ {len(headers)} HEADER(S) DETECTED")
        print(f"      → Key for: Carrier info, document title, section divisions")
        for i, header in enumerate(headers):
            x1, y1, x2, y2 = header.bbox
            print(f"      → Header {i+1}: {header.label} at ({x1:.0f},{y1:.0f})")
    
    # Look for other BOL-relevant regions
    list_items = []
    figures = []
    text_blocks = []
    
    for page in layout_result.pages:
        list_items.extend(page.get_regions_by_type("List-item"))
        figures.extend(page.get_regions_by_type("Figure"))
        text_blocks.extend(page.get_regions_by_type("Text"))
    
    if list_items:
        print(f"\n   ✅ {len(list_items)} LIST ITEM(S) DETECTED")
        print(f"      → Potential: Service codes, special instructions, freight classifications")
    
    if figures:
        print(f"\n   ✅ {len(figures)} FIGURE(S) DETECTED")
        print(f"      → Potential: Signatures, stamps, logos, barcodes")
    
    if text_blocks:
        print(f"\n   ℹ️  {len(text_blocks)} TEXT BLOCK(S)")
        print(f"      → Standard text regions for addresses, terms, etc.")
    
    # Reading order analysis for BOLs
    print(f"\n📖 READING ORDER ANALYSIS:")
    for page_num, page in enumerate(layout_result.pages):
        print(f"\n   PAGE {page.page}:")
        reading_order = page.get_reading_order()
        
        # Show key regions in reading order
        for i, bbox in enumerate(reading_order[:10]):  # Show first 10 regions
            x1, y1, x2, y2 = bbox.bbox
            print(f"      {bbox.position:2d}. {bbox.label:15s} at ({x1:4.0f},{y1:4.0f}) - {x2-x1:.0f}×{y2-y1:.0f}")
        
        if len(reading_order) > 10:
            print(f"      ... and {len(reading_order) - 10} more regions")
    
    # BOL Processing Strategy Recommendations
    print(f"\n🎯 PROCESSING STRATEGY RECOMMENDATIONS:")
    
    if tables:
        print(f"   📊 TABLE-FOCUSED EXTRACTION:")
        print(f"      → Use table regions for structured data (shipment details, charges)")
        print(f"      → Apply table-specific AI prompts")
        print(f"      → Validate numerical data in table regions")
    
    if headers:
        print(f"   📋 HEADER-GUIDED ORGANIZATION:")
        print(f"      → Use headers to identify document sections")
        print(f"      → Context-aware field extraction per section")
        print(f"      → Improved carrier/shipper identification")
    
    print(f"   🔄 READING ORDER PROCESSING:")
    print(f"      → Process regions in detected sequence")
    print(f"      → Maintain document flow context")
    print(f"      → Better relationship understanding")
    
    return {
        "total_regions": total_regions,
        "tables": len(tables),
        "headers": len(headers),
        "list_items": len(list_items),
        "figures": len(figures),
        "text_blocks": len(text_blocks),
        "processing_time": layout_result.processing_time
    }


async def test_bol_layout_analysis():
    """Test layout analysis on all available BOL documents."""
    
    print("🚛 TESTING LAYOUT ANALYSIS ON BILL OF LADING DOCUMENTS")
    print("=" * 70)
    
    # Find BOL test documents
    test_dir = Path("test_documents/bol")
    if not test_dir.exists():
        print(f"❌ BOL test directory not found: {test_dir}")
        return []
    
    # Get BOL files
    bol_files = list(test_dir.glob("*.jpg")) + list(test_dir.glob("*.png"))
    if not bol_files:
        print(f"❌ No BOL files found in {test_dir}")
        return []
    
    print(f"📄 Found {len(bol_files)} BOL documents to analyze")
    
    results = []
    
    async with DatalabLayoutClient() as layout_client:
        for i, bol_file in enumerate(bol_files):
            print(f"\n🔄 Processing BOL {i+1}/{len(bol_files)}: {bol_file.name}")
            print("-" * 50)
            
            try:
                # Read file content
                with open(bol_file, "rb") as f:
                    file_content = f.read()
                
                print(f"📦 File size: {len(file_content):,} bytes")
                
                # Run layout analysis
                layout_result = await layout_client.analyze_layout(
                    file_content=file_content,
                    filename=bol_file.name,
                    mime_type="image/jpeg"
                )
                
                # Analyze results
                analysis = analyze_bol_layout(layout_result, bol_file.name)
                if analysis:
                    analysis["filename"] = bol_file.name
                    analysis["file_size"] = len(file_content)
                    results.append(analysis)
                
            except Exception as e:
                print(f"💥 Layout analysis failed for {bol_file.name}: {e}")
                continue
    
    return results


async def test_combined_bol_processing():
    """Test combined OCR + Layout analysis on a complex BOL."""
    
    print(f"\n\n🔬 COMBINED OCR + LAYOUT ANALYSIS ON COMPLEX BOL")
    print("=" * 70)
    
    # Find the largest BOL file (likely most complex)
    test_dir = Path("test_documents/bol")
    bol_files = list(test_dir.glob("*.jpg"))
    
    if not bol_files:
        return None, None
    
    # Sort by file size to get the most complex one
    bol_files.sort(key=lambda f: f.stat().st_size, reverse=True)
    complex_bol = bol_files[0]
    
    print(f"📄 Processing most complex BOL: {complex_bol.name}")
    print(f"📦 File size: {complex_bol.stat().st_size:,} bytes")
    
    # Read file content
    with open(complex_bol, "rb") as f:
        file_content = f.read()
    
    # Initialize clients
    layout_client = DatalabLayoutClient()
    ocr_client = UnifiedOCRClient()
    
    try:
        # Run both analyses in parallel
        print(f"🔄 Running parallel OCR + Layout analysis...")
        
        layout_task = layout_client.analyze_layout(
            file_content=file_content,
            filename=complex_bol.name,
            mime_type="image/jpeg"
        )
        
        ocr_task = ocr_client.process_file_content(
            file_content=file_content,
            filename=complex_bol.name,
            mime_type="image/jpeg"
        )
        
        async with layout_client, ocr_client:
            layout_result, ocr_result = await asyncio.gather(layout_task, ocr_task)
        
        # Comprehensive analysis
        print(f"\n📊 COMPREHENSIVE BOL ANALYSIS")
        print("=" * 50)
        
        # OCR Results
        ocr_text = ocr_result.get('full_text', '')
        ocr_confidence = ocr_result.get('average_confidence', 0)
        ocr_lines = sum(len(page.get('text_lines', [])) for page in ocr_result.get('pages', []))
        
        print(f"🔍 OCR RESULTS:")
        print(f"   Characters extracted: {len(ocr_text):,}")
        print(f"   Text lines: {ocr_lines}")
        print(f"   Average confidence: {ocr_confidence:.1%}")
        print(f"   Extraction method: {ocr_result.get('extraction_method', 'unknown')}")
        
        # Layout Results
        total_regions = sum(len(page.bboxes) for page in layout_result.pages)
        tables = layout_result.get_all_tables()
        headers = layout_result.get_all_headers()
        
        print(f"\n📐 LAYOUT RESULTS:")
        print(f"   Total regions: {total_regions}")
        print(f"   Tables detected: {len(tables)}")
        print(f"   Headers detected: {len(headers)}")
        print(f"   Processing time: {layout_result.processing_time:.2f}s")
        
        # Show first few lines of extracted text
        if ocr_text:
            print(f"\n📝 SAMPLE EXTRACTED TEXT:")
            text_lines = ocr_text.split('\n')[:10]
            for i, line in enumerate(text_lines):
                if line.strip():
                    print(f"   {i+1:2d}: {line.strip()[:80]}")
            if len(text_lines) > 10:
                print(f"   ... and {len(text_lines) - 10} more lines")
        
        # Enhanced extraction potential
        print(f"\n💡 ENHANCED EXTRACTION POTENTIAL:")
        
        if tables and ocr_text:
            print(f"   ✅ STRUCTURED DATA EXTRACTION:")
            print(f"      → {len(tables)} table(s) detected with {len(ocr_text)} chars of text")
            print(f"      → Can apply table-specific parsing")
            print(f"      → Enhanced shipment detail extraction")
        
        if headers and ocr_confidence > 0.8:
            print(f"   ✅ SECTION-AWARE PROCESSING:")
            print(f"      → {len(headers)} header(s) with {ocr_confidence:.1%} confidence")
            print(f"      → Can organize extraction by document sections")
            print(f"      → Improved carrier/shipper field accuracy")
        
        if total_regions > 10:
            print(f"   ✅ COMPLEX DOCUMENT HANDLING:")
            print(f"      → {total_regions} regions provide rich structure")
            print(f"      → Reading order processing available")
            print(f"      → Context-aware field validation possible")
        
        return layout_result, ocr_result
        
    except Exception as e:
        print(f"💥 Combined analysis failed: {e}")
        return None, None


async def summarize_bol_analysis(results):
    """Summarize the BOL layout analysis results."""
    
    if not results:
        print("❌ No results to summarize")
        return
    
    print(f"\n📈 BOL LAYOUT ANALYSIS SUMMARY")
    print("=" * 50)
    print(f"📄 Documents analyzed: {len(results)}")
    
    # Calculate statistics
    total_regions = sum(r["total_regions"] for r in results)
    total_tables = sum(r["tables"] for r in results)
    total_headers = sum(r["headers"] for r in results)
    avg_processing_time = sum(r["processing_time"] for r in results) / len(results)
    
    print(f"🔍 Total regions detected: {total_regions}")
    print(f"📊 Total tables detected: {total_tables}")
    print(f"📋 Total headers detected: {total_headers}")
    print(f"⏱️  Average processing time: {avg_processing_time:.2f}s")
    
    # Success rates
    docs_with_tables = sum(1 for r in results if r["tables"] > 0)
    docs_with_headers = sum(1 for r in results if r["headers"] > 0)
    
    print(f"\n📊 DETECTION RATES:")
    print(f"   Tables: {docs_with_tables}/{len(results)} documents ({docs_with_tables/len(results)*100:.1f}%)")
    print(f"   Headers: {docs_with_headers}/{len(results)} documents ({docs_with_headers/len(results)*100:.1f}%)")
    
    # Individual document breakdown
    print(f"\n📋 INDIVIDUAL DOCUMENT ANALYSIS:")
    for result in results:
        print(f"   {result['filename']:15s} → Regions: {result['total_regions']:2d}, Tables: {result['tables']:2d}, Headers: {result['headers']:2d}")
    
    # Recommendations
    print(f"\n🎯 INTEGRATION RECOMMENDATIONS:")
    
    if docs_with_tables / len(results) > 0.5:
        print(f"   ✅ HIGH TABLE DETECTION RATE ({docs_with_tables/len(results)*100:.1f}%)")
        print(f"      → Integrate table-specific extraction strategies")
        print(f"      → Use layout context for structured data parsing")
    
    if docs_with_headers / len(results) > 0.5:
        print(f"   ✅ HIGH HEADER DETECTION RATE ({docs_with_headers/len(results)*100:.1f}%)")
        print(f"      → Implement section-aware field extraction")
        print(f"      → Use headers for document organization")
    
    if avg_processing_time < 15:
        print(f"   ✅ ACCEPTABLE PROCESSING TIME ({avg_processing_time:.1f}s avg)")
        print(f"      → Layout analysis viable for production use")
    
    print(f"\n🚀 READY FOR PIPELINE INTEGRATION!")


async def main():
    """Run comprehensive BOL layout analysis."""
    
    # Check API key
    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ DATALAB_API_KEY not found in environment")
        return
    
    print("🚛 COMPREHENSIVE BOL LAYOUT ANALYSIS")
    print("=" * 70)
    print("Testing Datalab Layout API on complex Bill of Lading documents")
    print("to demonstrate enhanced freight document processing capabilities.\n")
    
    # Test 1: Layout analysis on all BOLs
    results = await test_bol_layout_analysis()
    
    # Test 2: Combined OCR + Layout on complex BOL
    await test_combined_bol_processing()
    
    # Test 3: Summarize findings
    await summarize_bol_analysis(results)


if __name__ == "__main__":
    asyncio.run(main()) 
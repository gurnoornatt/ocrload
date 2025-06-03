#!/usr/bin/env python3
"""
Real Performance Test: BOL9 & Lumper2
                                         
Comprehensive evaluation of image preprocessing impact on actual document processing:
- BOL9: Bill of Lading analysis  
- Lumper2: Lumper receipt analysis
- Direct comparison of extraction quality with/without preprocessing
- Claude-powered analysis of extracted data (totals, deliveries, etc.)
- Actionable recommendations on preprocessing effectiveness
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Configure logging for clean output
logging.basicConfig(level=logging.WARNING)

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent / "app"))

from app.services.enhanced_bol_extractor import EnhancedBOLExtractor
from app.services.enhanced_lumper_extractor import EnhancedLumperExtractor
from app.services.ocr_clients.datalab_marker_client import DatalabMarkerClient

async def analyze_document_with_claude(document_type: str, extracted_data: dict, confidence: float, markdown_content: str, preprocessing_enabled: bool) -> str:
    """Use Claude to analyze and summarize the extracted document data."""
    
    # Create an extractor to access Claude
    if document_type == "BOL":
        extractor = EnhancedBOLExtractor()
    else:
        extractor = EnhancedLumperExtractor()
    
    if not extractor.client if hasattr(extractor, 'client') else not extractor.anthropic_client:
        return "Claude analysis unavailable - no Anthropic client"
    
    try:
        # Create analysis prompt
        analysis_prompt = f"""
Analyze this {document_type} extraction result and provide a comprehensive summary:

EXTRACTION CONFIDENCE: {confidence:.1%}
PREPROCESSING: {"✓ Enabled" if preprocessing_enabled else "✗ Disabled"}

EXTRACTED DATA:
{json.dumps(extracted_data, indent=2)}

MARKDOWN CONTENT PREVIEW:
{markdown_content[:1000]}...

Please provide:

1. **DATA QUALITY ASSESSMENT** 
   - Overall extraction accuracy
   - Key fields successfully captured
   - Missing or questionable data

2. **FINANCIAL/LOGISTICS SUMMARY**
   - For BOL: Shipper, consignee, freight details, weights, charges
   - For Lumper: Services performed, costs, facility details

3. **EXTRACTION STRENGTHS & WEAKNESSES**
   - What was extracted well
   - What needs improvement
   - Data completeness score (0-100%)

4. **ACTIONABLE INSIGHTS**
   - Business-relevant information
   - Potential issues or flags
   - Processing recommendations

Provide a concise but thorough analysis in professional language.
"""

        # Get Claude's analysis
        client = extractor.client if hasattr(extractor, 'client') else extractor.anthropic_client
        response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1500,
            temperature=0.1,
            system="You are an expert freight document analyst providing concise, accurate assessments of document extraction quality and business data.",
            messages=[{
                "role": "user",
                "content": analysis_prompt
            }]
        )
        
        return response.content[0].text
        
    except Exception as e:
        return f"Claude analysis failed: {str(e)}"

async def test_document_performance(doc_path: str, doc_type: str, extractor_class):
    """Test a document with and without preprocessing."""
    
    print(f"📋 {doc_path.upper()} PERFORMANCE ANALYSIS")
    print("="*60)
    
    # Find document
    doc_file = None
    for ext in ['.jpg', '.jpeg', '.png', '.webp', '.pdf']:
        test_file = Path(f"{doc_path}{ext}")
        if test_file.exists():
            doc_file = test_file
            break
    
    if not doc_file:
        print(f"❌ {doc_path} document not found")
        return None
    
    print(f"📁 Found: {doc_file.name}")
    
    # Load document
    with open(doc_file, 'rb') as f:
        file_content = f.read()
    
    # Determine MIME type
    if doc_file.suffix.lower() in ['.jpg', '.jpeg']:
        mime_type = "image/jpeg"
    elif doc_file.suffix.lower() == '.png':
        mime_type = "image/png"
    elif doc_file.suffix.lower() == '.webp':
        mime_type = "image/webp"
    elif doc_file.suffix.lower() == '.pdf':
        mime_type = "application/pdf"
    else:
        mime_type = "image/jpeg"
    
    print(f"📂 MIME type: {mime_type}")
    print(f"📏 File size: {len(file_content):,} bytes")
    print()
    
    # Initialize extractor
    extractor = extractor_class()
    
    results = {}
    
    # Test both preprocessing modes
    for prep_enabled, label, color in [(False, "WITHOUT PREPROCESSING", "🔴"), (True, "WITH PREPROCESSING", "🟢")]:
        print(f"{color} PROCESSING {label}")
        print("-" * 50)
        
        async with DatalabMarkerClient(preprocessing_enabled=prep_enabled) as marker:
            # Get OCR result
            ocr_result = await marker.process_document(
                file_content=file_content,
                filename=doc_file.name,
                mime_type=mime_type,
                language="English",
                force_ocr=True,
                use_llm=True,
                output_format="markdown"
            )
            
            if ocr_result.success:
                print(f"✅ Marker API successful")
                print(f"📄 Content length: {len(ocr_result.markdown_content):,} characters")
                print(f"⏱️  Processing time: {ocr_result.processing_time:.2f} seconds")
                
                # Show preprocessing steps if available
                if prep_enabled and 'image_preprocessing' in ocr_result.metadata:
                    preprocessing_info = ocr_result.metadata['image_preprocessing']
                    if 'processing_steps' in preprocessing_info:
                        print(f"🖼️  Preprocessing steps: {len(preprocessing_info['processing_steps'])}")
                        for step in preprocessing_info['processing_steps'][:3]:  # Show first 3
                            print(f"   • {step}")
                        if len(preprocessing_info['processing_steps']) > 3:
                            print(f"   • ... and {len(preprocessing_info['processing_steps'])-3} more")
                
                # Extract data with Claude
                extracted, confidence = await extractor.extract_fields_from_markdown(
                    markdown_content=ocr_result.markdown_content,
                    marker_metadata={"workflow": f"{'with' if prep_enabled else 'no'}_preprocessing"}
                )
                
                print(f"🤖 Claude extraction confidence: {confidence:.1%}")
                
                results[f"{'with' if prep_enabled else 'no'}_prep"] = {
                    'extracted': extracted,
                    'confidence': confidence,
                    'content_length': len(ocr_result.markdown_content),
                    'processing_time': ocr_result.processing_time,
                    'markdown_content': ocr_result.markdown_content
                }
                
            else:
                print(f"❌ Marker API failed: {ocr_result.error}")
                results[f"{'with' if prep_enabled else 'no'}_prep"] = {
                    'extracted': {},
                    'confidence': 0.0,
                    'content_length': 0,
                    'processing_time': 0,
                    'markdown_content': ""
                }
        
        print()
    
    # ================== DETAILED ANALYSIS ==================
    print(f"📊 DETAILED {doc_path.upper()} ANALYSIS")
    print("-" * 50)
    
    # Get Claude analysis for both
    print("🤖 Generating Claude analysis...")
    
    for prep_key, label, color in [("no_prep", "WITHOUT PREPROCESSING", "🔴"), ("with_prep", "WITH PREPROCESSING", "🟢")]:
        if prep_key in results:
            analysis = await analyze_document_with_claude(
                doc_type, 
                results[prep_key]['extracted'], 
                results[prep_key]['confidence'],
                results[prep_key]['markdown_content'],
                preprocessing_enabled=(prep_key == "with_prep")
            )
            
            results[prep_key]['analysis'] = analysis
            
            print(f"\n{color} ANALYSIS: {label}")
            print("-" * 40)
            print(analysis)
    
    return results

async def generate_final_summary(bol_results: dict, lumper_results: dict):
    """Generate comprehensive final summary using Claude."""
    
    # Use BOL extractor to access Claude
    extractor = EnhancedBOLExtractor()
    
    if not extractor.client if hasattr(extractor, 'client') else not extractor.anthropic_client:
        return "❌ Final summary unavailable - no Anthropic client"
    
    try:
        summary_prompt = f"""
Generate a comprehensive executive summary of image preprocessing impact on document processing:

BOL9 RESULTS:
Without Preprocessing:
- Confidence: {bol_results['no_prep']['confidence']:.1%}
- Content Length: {bol_results['no_prep']['content_length']:,} chars
- Processing Time: {bol_results['no_prep']['processing_time']:.2f}s

With Preprocessing:
- Confidence: {bol_results['with_prep']['confidence']:.1%}
- Content Length: {bol_results['with_prep']['content_length']:,} chars
- Processing Time: {bol_results['with_prep']['processing_time']:.2f}s

LUMPER2 RESULTS:
Without Preprocessing:
- Confidence: {lumper_results['no_prep']['confidence']:.1%}
- Content Length: {lumper_results['no_prep']['content_length']:,} chars
- Processing Time: {lumper_results['no_prep']['processing_time']:.2f}s

With Preprocessing:
- Confidence: {lumper_results['with_prep']['confidence']:.1%}
- Content Length: {lumper_results['with_prep']['content_length']:,} chars
- Processing Time: {lumper_results['with_prep']['processing_time']:.2f}s

EXTRACTED DATA SAMPLES:
BOL9 No Prep: {json.dumps(bol_results['no_prep']['extracted'], indent=2)}
BOL9 With Prep: {json.dumps(bol_results['with_prep']['extracted'], indent=2)}

Lumper2 No Prep: {json.dumps(lumper_results['no_prep']['extracted'], indent=2)}
Lumper2 With Prep: {json.dumps(lumper_results['with_prep']['extracted'], indent=2)}

Provide:

1. **PREPROCESSING EFFECTIVENESS VERDICT**
   - Clear yes/no on whether preprocessing helps
   - Quantified improvements (if any)
   - Document type differences

2. **DATA QUALITY COMPARISON**
   - Accuracy of key business data (amounts, dates, names)
   - Completeness improvements
   - Error reduction

3. **PERFORMANCE IMPACT**
   - Processing time changes
   - Resource usage considerations
   - Cost/benefit analysis

4. **BUSINESS RECOMMENDATIONS**
   - Should preprocessing be enabled in production?
   - For which document types?
   - Configuration suggestions

5. **TECHNICAL INSIGHTS**
   - What specific preprocessing steps provide value
   - Document quality factors that matter
   - Optimization opportunities

Make this actionable for a freight audit platform team.
"""

        client = extractor.client if hasattr(extractor, 'client') else extractor.anthropic_client
        response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            temperature=0.1,
            system="You are a senior technical consultant providing executive-level recommendations on document processing optimization for freight audit platforms.",
            messages=[{
                "role": "user",
                "content": summary_prompt
            }]
        )
        
        return response.content[0].text
        
    except Exception as e:
        return f"❌ Final summary generation failed: {str(e)}"

async def main():
    """Run comprehensive performance analysis."""
    
    print("🚀 REAL PERFORMANCE ANALYSIS: BOL9 & LUMPER2")
    print("=" * 80)
    print("Testing image preprocessing impact on freight document processing")
    print("=" * 80)
    
    # Test both documents
    bol_results = await test_document_performance(
        "test_documents/bol/BOL9", 
        "BOL", 
        EnhancedBOLExtractor
    )
    
    lumper_results = await test_document_performance(
        "test_documents/lumper/lumper2", 
        "LUMPER", 
        EnhancedLumperExtractor
    )
    
    if bol_results and lumper_results:
        # Generate final summary
        print("\n\n🎯 EXECUTIVE SUMMARY")
        print("=" * 60)
        
        final_summary = await generate_final_summary(bol_results, lumper_results)
        print(final_summary)
        
        # Quick metrics table
        print("\n\n📈 QUICK METRICS COMPARISON")
        print("-" * 60)
        
        print(f"┌{'─'*15}┬{'─'*12}┬{'─'*12}┬{'─'*12}┬{'─'*12}┐")
        print(f"│{'Document':<15}│{'Metric':<12}│{'No Prep':<12}│{'With Prep':<12}│{'Winner':<12}│")
        print(f"├{'─'*15}┼{'─'*12}┼{'─'*12}┼{'─'*12}┼{'─'*12}┤")
        
        # BOL9 confidence
        bol_conf_no = bol_results['no_prep']['confidence']
        bol_conf_with = bol_results['with_prep']['confidence']
        bol_conf_winner = "🟢 Prep" if bol_conf_with > bol_conf_no else "🔴 No Prep" if bol_conf_no > bol_conf_with else "🟡 Tie"
        print(f"│{'BOL9':<15}│{'Confidence':<12}│{bol_conf_no:<12.1%}│{bol_conf_with:<12.1%}│{bol_conf_winner:<12}│")
        
        # Lumper2 confidence
        lump_conf_no = lumper_results['no_prep']['confidence']
        lump_conf_with = lumper_results['with_prep']['confidence']
        lump_conf_winner = "🟢 Prep" if lump_conf_with > lump_conf_no else "🔴 No Prep" if lump_conf_no > lump_conf_with else "🟡 Tie"
        print(f"│{'Lumper2':<15}│{'Confidence':<12}│{lump_conf_no:<12.1%}│{lump_conf_with:<12.1%}│{lump_conf_winner:<12}│")
        
        print(f"└{'─'*15}┴{'─'*12}┴{'─'*12}┴{'─'*12}┴{'─'*12}┘")
        
        # Overall recommendation
        overall_improvements = 0
        if bol_conf_with > bol_conf_no:
            overall_improvements += 1
        if lump_conf_with > lump_conf_no:
            overall_improvements += 1
        
        print(f"\n🏆 FINAL VERDICT:")
        if overall_improvements >= 1:
            print(f"   ✅ Preprocessing shows measurable benefits")
            print(f"   📈 Recommendation: ENABLE preprocessing in production")
        else:
            print(f"   ➡️  Mixed or minimal preprocessing benefits")
            print(f"   🤔 Recommendation: Consider document-specific preprocessing")
    
    else:
        print("❌ Could not complete analysis - missing test documents")

if __name__ == "__main__":
    asyncio.run(main())

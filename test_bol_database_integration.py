#!/usr/bin/env python3
"""
BOL Database Integration Test
Tests the complete BOL processing pipeline: OCR → Semantic Extraction → Database Storage
"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from app.services.ocr_clients.enhanced_datalab_client import EnhancedDatalabClient
from app.services.semantic_bol_extractor import SemanticBOLExtractor
from app.services.document_service import DocumentService
from app.services.supabase_client import supabase_service
from app.models.database import Document, DocumentType, DocumentStatus

async def test_bol_database_integration():
    """Complete BOL processing pipeline test with database integration"""
    
    print("🚛 BOL DATABASE INTEGRATION TEST")
    print("=" * 100)
    
    # Find BOL documents
    bol_dir = Path("test_documents/bol")
    if not bol_dir.exists():
        print("❌ BOL directory not found: test_documents/bol/")
        return
    
    bol_files = list(bol_dir.glob("BOL*.*"))[:3]  # Test first 3 files
    bol_files.sort()
    
    if not bol_files:
        print("❌ No BOL files found in test_documents/bol/")
        return
    
    print(f"📁 Testing {len(bol_files)} BOL documents with database integration:")
    for file_path in bol_files:
        print(f"   - {file_path.name}")
    
    # Initialize services
    ocr_client = EnhancedDatalabClient()
    bol_extractor = SemanticBOLExtractor()
    doc_service = DocumentService()
    
    # Test database connectivity
    print(f"\n🔗 Testing Database Connectivity...")
    try:
        health = await supabase_service.health_check()
        db_status = health["database"]["status"]
        print(f"   Database: {db_status} - {health['database']['message']}")
        
        if db_status != "healthy":
            print("❌ Database not healthy, skipping database integration")
            return
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return
    
    # Process each BOL document
    successful_saves = 0
    
    for i, file_path in enumerate(bol_files, 1):
        print(f"\n📄 BOL {i}: {file_path.name}")
        print("-" * 100)
        
        document_id = uuid4()
        
        try:
            # Step 1: Read file
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            filename = file_path.name
            import mimetypes
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if not mime_type:
                mime_type = "application/octet-stream"
            
            print(f"📋 File Info: {filename} ({len(file_content)} bytes, {mime_type})")
            
            # Step 2: OCR Processing
            print("🔤 Step 1: OCR Extraction...")
            async with ocr_client as client:
                ocr_results = await client.process_invoice_comprehensive(
                    file_content, filename, mime_type
                )
            
            if not ocr_results.get("success"):
                print(f"❌ OCR Failed: {ocr_results.get('error', 'Unknown error')}")
                continue
            
            raw_text = ocr_client.extract_text_from_results(ocr_results)
            ocr_confidence = ocr_results.get("confidence", 0.0)
            
            print(f"✅ OCR Success - Confidence: {ocr_confidence:.1%}")
            print(f"   Text Length: {len(raw_text)} characters")
            
            # Step 3: Semantic Extraction
            print(f"🧠 Step 2: Semantic BOL Extraction...")
            
            extracted_data, confidence, needs_review = await bol_extractor.extract_bol_fields(
                raw_text, use_cross_validation=True
            )
            
            print(f"✅ Extraction Complete")
            print(f"   Confidence: {confidence:.1%}")
            print(f"   Needs Review: {needs_review}")
            print(f"   Validation Issues: {len(extracted_data.validation_flags)}")
            
            # Show key extracted fields
            extracted_dict = extracted_data.model_dump()
            key_fields = ["bol_number", "pro_number", "shipper_name", "consignee_name", "carrier_name"]
            print(f"\n📊 Key Extracted Fields:")
            for field in key_fields:
                value = extracted_dict.get(field)
                status = "✅" if value else "❌"
                print(f"   {status} {field}: {value}")
            
            # Step 4: Create Document Record
            print(f"\n💾 Step 3: Database Integration...")
            
            # Create document record first
            document = Document(
                id=document_id,
                type=DocumentType.INVOICE,  # Using INVOICE as BOL type doesn't exist in enum yet
                url=f"file://{file_path}",  # Fake URL for testing
                status=DocumentStatus.PARSED,
                confidence=confidence / 100.0,  # Convert percentage to decimal
                parsed_data=extracted_dict,
                metadata={
                    "original_filename": filename,
                    "file_size": len(file_content),
                    "content_type": mime_type,
                    "ocr_confidence": ocr_confidence,
                    "semantic_confidence": confidence,
                    "needs_review": needs_review,
                    "validation_issues": len(extracted_data.validation_flags)
                }
            )
            
            print(f"   Creating document record...")
            try:
                # Convert to dict for database insertion
                doc_data = document.model_dump()
                doc_data["id"] = str(doc_data["id"])
                if doc_data.get("created_at"):
                    doc_data["created_at"] = doc_data["created_at"].isoformat()
                if doc_data.get("updated_at"):
                    doc_data["updated_at"] = doc_data["updated_at"].isoformat()
                
                created_doc = await supabase_service.create_document_raw(doc_data)
                print(f"   ✅ Document record created: {created_doc.id}")
                
                # Step 5: Save BOL-specific data
                print(f"   Creating BOL-specific record...")
                bol_saved = await doc_service.save_bol_data(
                    document_id=document_id,
                    bol_data=extracted_data
                )
                
                if bol_saved:
                    print(f"   ✅ BOL data saved to database")
                    successful_saves += 1
                    
                    # Verify the data was saved
                    print(f"   🔍 Verifying database record...")
                    try:
                        # Query the bills_of_lading table to verify
                        result = supabase_service.client.table("bills_of_lading").select("*").eq("document_id", str(document_id)).execute()
                        if result.data:
                            bol_record = result.data[0]
                            print(f"   ✅ BOL record verified in database:")
                            print(f"      BOL Number: {bol_record.get('bol_number')}")
                            print(f"      Shipper: {bol_record.get('shipper_name')}")
                            print(f"      Consignee: {bol_record.get('consignee_name')}")
                            print(f"      Weight: {bol_record.get('weight')}")
                        else:
                            print(f"   ⚠️ BOL record not found in database")
                    except Exception as e:
                        print(f"   ⚠️ Could not verify BOL record: {e}")
                else:
                    print(f"   ❌ Failed to save BOL data")
                
            except Exception as e:
                print(f"   ❌ Database operation failed: {e}")
                import traceback
                traceback.print_exc()
            
            # Overall assessment
            filled_fields = sum(1 for v in extracted_dict.values() 
                              if v is not None and v != "" and v != [])
            total_fields = len([k for k in extracted_dict.keys() 
                              if k not in ["confidence_score", "validation_flags"]])
            completeness = filled_fields / total_fields
            
            print(f"\n📈 DOCUMENT SUMMARY:")
            print(f"   Field Completeness: {filled_fields}/{total_fields} ({completeness:.1%})")
            print(f"   Extraction Confidence: {confidence:.1%}")
            print(f"   Database Status: {'✅ Saved' if bol_saved else '❌ Failed'}")
            print(f"   Ready for Production: {'✅' if bol_saved and confidence >= 80 else '⚠️'}")
            
        except Exception as e:
            print(f"❌ ERROR processing {file_path.name}: {e}")
            import traceback
            traceback.print_exc()
        
        print("-" * 100)
    
    # Final Summary
    print(f"\n🎯 FINAL RESULTS:")
    print(f"   Documents Processed: {len(bol_files)}")
    print(f"   Successfully Saved to DB: {successful_saves}")
    print(f"   Success Rate: {successful_saves}/{len(bol_files)} ({successful_saves/len(bol_files)*100:.1f}%)")
    
    if successful_saves > 0:
        print(f"\n✅ Database integration working! BOL documents are being:")
        print(f"   • Processed via OCR ✅")
        print(f"   • Extracted via AI ✅") 
        print(f"   • Stored in Database ✅")
        print(f"   • Available in Supabase bills_of_lading table ✅")
    else:
        print(f"\n❌ Database integration needs attention")

if __name__ == "__main__":
    asyncio.run(test_bol_database_integration()) 
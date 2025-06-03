#!/usr/bin/env python3
"""
Simple test of Marker + Claude workflow (NO PREPROCESSING)

Tests marker API extraction → Claude semantic reasoning for:
- 2 Invoices 
- 2 BOLs
- 2 Lumper receipts

Shows markdown extraction and Claude's reasoning process clearly.
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import the clients we need
from app.services.ocr_clients.datalab_marker_client import DatalabMarkerClient
from anthropic import AsyncAnthropic

class SimpleWorkflowTester:
    """Simple test of marker + claude with no preprocessing."""
    
    def __init__(self):
        # Initialize marker client (NO preprocessing!)
        self.marker_client = DatalabMarkerClient(preprocessing_enabled=False)
        
        # Initialize Claude
        self.claude = AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        )
        
        self.test_docs = Path("test_documents")

    async def test_document(self, file_path: Path, doc_type: str):
        """Test a single document through the marker + claude workflow."""
        print(f"\n{'='*60}")
        print(f"🧪 TESTING {doc_type.upper()}: {file_path.name}")
        print(f"{'='*60}")
        
        # Step 1: Read file
        with open(file_path, "rb") as f:
            file_content = f.read()
        
        print(f"📄 File size: {len(file_content):,} bytes")
        
        # Step 2: Extract with Marker API (NO PREPROCESSING)
        print("🔍 Extracting with Marker API (force_ocr=True, use_llm=False)...")
        
        try:
            # Get MIME type
            ext = file_path.suffix.lower()
            mime_types = {
                '.pdf': 'application/pdf',
                '.png': 'image/png', 
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.webp': 'image/webp',
                '.gif': 'image/gif'
            }
            mime_type = mime_types.get(ext, 'application/octet-stream')
            
            # Use context manager to properly handle the client
            async with self.marker_client:
                marker_result = await self.marker_client.process_document(
                    file_content=file_content,
                    filename=file_path.name,
                    mime_type=mime_type,
                    force_ocr=True,    # Force OCR - no preprocessing 
                    use_llm=False      # No LLM preprocessing
                )
            
            if marker_result.success:
                markdown_text = marker_result.markdown_content or ""
                print(f"✅ Marker extraction successful: {len(markdown_text)} characters")
                
                # Show first 500 chars of markdown
                print(f"\n📝 MARKDOWN PREVIEW:")
                print("-" * 40)
                print(markdown_text[:500] + "..." if len(markdown_text) > 500 else markdown_text)
                print("-" * 40)
            else:
                print(f"❌ Marker extraction failed: {marker_result.error}")
                return
        
        except Exception as e:
            print(f"❌ Marker extraction failed: {e}")
            return
        
        # Step 3: Claude semantic reasoning
        print(f"\n🤖 Sending to Claude 3.5 Sonnet for semantic reasoning...")
        
        # Create appropriate prompt based on document type
        if doc_type == "invoice":
            prompt = self._get_invoice_prompt(markdown_text)
        elif doc_type == "bol":
            prompt = self._get_bol_prompt(markdown_text) 
        elif doc_type == "lumper":
            prompt = self._get_lumper_prompt(markdown_text)
        else:
            print(f"❌ Unknown document type: {doc_type}")
            return
            
        try:
            response = await self.claude.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            claude_response = response.content[0].text
            print(f"✅ Claude processing successful: {len(claude_response)} characters")
            
            # Show Claude's reasoning and extraction
            print(f"\n🧠 CLAUDE'S SEMANTIC REASONING & EXTRACTION:")
            print("-" * 50)
            print(claude_response)
            print("-" * 50)
            
        except Exception as e:
            print(f"❌ Claude processing failed: {e}")
            return
            
        print(f"✅ {doc_type.upper()} TEST COMPLETED SUCCESSFULLY")

    def _get_invoice_prompt(self, markdown_text: str) -> str:
        return f"""
I need you to analyze this freight/transportation invoice document and extract key information using semantic reasoning.

DOCUMENT MARKDOWN:
{markdown_text}

Please analyze this document and provide:

1. **DOCUMENT SUMMARY**: Brief summary of what this invoice is for
2. **KEY EXTRACTED DATA**: 
   - Invoice Number
   - Invoice Date  
   - Due Date
   - Vendor/Company Name
   - Customer Name
   - Total Amount
   - Currency
   - Payment Terms
   - Line Items (services/freight charges)

3. **CONFIDENCE ASSESSMENT**: 
   - Overall confidence score (0.0-1.0)
   - Accuracy score for key fields (0.0-1.0)
   - Any fields that need manual review

4. **REASONING**: Explain your semantic reasoning process and any challenges in extraction.

Format your response clearly with sections and confidence scores.
"""

    def _get_bol_prompt(self, markdown_text: str) -> str:
        return f"""
I need you to analyze this Bill of Lading (BOL) document and extract key information using semantic reasoning.

DOCUMENT MARKDOWN:
{markdown_text}

Please analyze this document and provide:

1. **DOCUMENT SUMMARY**: Brief summary of this shipment
2. **KEY EXTRACTED DATA**:
   - BOL Number
   - PRO Number  
   - Pickup Date
   - Delivery Date
   - Shipper Name & Address
   - Consignee Name & Address
   - Carrier Name
   - Driver Name
   - Equipment Type & Number
   - Commodity Description
   - Weight & Pieces
   - Freight Charges
   - Special Instructions

3. **CONFIDENCE ASSESSMENT**:
   - Overall confidence score (0.0-1.0)
   - Accuracy score for key fields (0.0-1.0)
   - Any fields that need manual review

4. **REASONING**: Explain your semantic reasoning process and any challenges in extraction.

Format your response clearly with sections and confidence scores.
"""

    def _get_lumper_prompt(self, markdown_text: str) -> str:
        return f"""
I need you to analyze this lumper receipt document and extract key information using semantic reasoning.

DOCUMENT MARKDOWN:
{markdown_text}

Please analyze this document and provide:

1. **DOCUMENT SUMMARY**: Brief summary of the lumper services provided
2. **KEY EXTRACTED DATA**:
   - Receipt Number
   - Receipt Date
   - Facility/Warehouse Name & Address
   - Driver Name
   - Carrier Name
   - Load/BOL Number
   - Service Type (loading/unloading)
   - Labor Hours
   - Hourly Rate
   - Total Charges
   - Equipment Used
   - Special Services
   - Notes/Comments

3. **CONFIDENCE ASSESSMENT**:
   - Overall confidence score (0.0-1.0)
   - Accuracy score for key fields (0.0-1.0)
   - Any fields that need manual review

4. **REASONING**: Explain your semantic reasoning process and any challenges in extraction.

Format your response clearly with sections and confidence scores.
"""

    async def run_tests(self):
        """Run tests on 2 documents of each type."""
        print("🚀 SIMPLE MARKER + CLAUDE WORKFLOW TEST")
        print("NO PREPROCESSING - Pure marker OCR → Claude semantic reasoning")
        
        # Test 2 invoices
        print(f"\n🧾 TESTING INVOICES")
        invoice_files = list(self.test_docs.glob("invoices/*"))[:2]
        for inv_file in invoice_files:
            await self.test_document(inv_file, "invoice")
        
        # Test 2 BOLs  
        print(f"\n📋 TESTING BILLS OF LADING")
        bol_files = list(self.test_docs.glob("bol/*"))[:2]
        for bol_file in bol_files:
            await self.test_document(bol_file, "bol")
            
        # Test 2 lumper receipts
        print(f"\n🏗️ TESTING LUMPER RECEIPTS") 
        lumper_files = list(self.test_docs.glob("lumper/*"))[:2]
        for lumper_file in lumper_files:
            await self.test_document(lumper_file, "lumper")
            
        print(f"\n✅ ALL TESTS COMPLETED!")
        print("📊 Review the Claude responses above to see extraction quality and confidence scores.")


async def main():
    """Run the simple workflow test."""
    # Check API keys
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")):
        print("❌ No Claude API key found!")
        return
        
    if not os.getenv("DATALAB_API_KEY"):
        print("❌ No Datalab API key found!")
        return
        
    print("✅ API keys found - proceeding with tests")
    
    tester = SimpleWorkflowTester()
    await tester.run_tests()


if __name__ == "__main__":
    asyncio.run(main()) 
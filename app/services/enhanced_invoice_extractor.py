"""
Enhanced Invoice Extractor with Marker API + Sonnet 3.5

New improved workflow for freight invoices:
1. Datalab Marker API processes document with force_ocr=True, use_llm=False (no preprocessing)
2. Structured markdown output fed directly to Sonnet 3.5 for semantic reasoning
3. Much better extraction results due to cleaner, organized input
4. Replaces the old OCR + regex/rules → sometimes GPT workflow

This replaces the old raw OCR text approach with structured markdown processing.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

from app.config.settings import settings
from .ocr_clients.datalab_marker_client import DatalabMarkerClient, MarkerResult

# Anthropic import for Sonnet 3.5
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

logger = logging.getLogger(__name__)


class ExtractedInvoiceData(BaseModel):
    """Structured invoice data with validation - optimized for freight invoices."""
    
    # Core invoice identifiers
    invoice_number: Optional[str] = Field(None, description="Invoice number or ID")
    invoice_date: Optional[str] = Field(None, description="Invoice date in YYYY-MM-DD format")
    due_date: Optional[str] = Field(None, description="Due date in YYYY-MM-DD format")
    
    # Vendor/carrier information
    vendor_name: Optional[str] = Field(None, description="Vendor/carrier company name")
    vendor_address: Optional[str] = Field(None, description="Vendor address")
    
    # Customer/shipper information
    customer_name: Optional[str] = Field(None, description="Customer/shipper company name")
    customer_address: Optional[str] = Field(None, description="Customer address")
    
    # Freight details
    bol_number: Optional[str] = Field(None, description="BOL number reference")
    pro_number: Optional[str] = Field(None, description="PRO number reference")
    pickup_date: Optional[str] = Field(None, description="Pickup date in YYYY-MM-DD format")
    delivery_date: Optional[str] = Field(None, description="Delivery date in YYYY-MM-DD format")
    
    # Financial details
    subtotal: Optional[float] = Field(None, description="Subtotal amount before charges")
    freight_charges: Optional[float] = Field(None, description="Base freight charges")
    fuel_surcharge: Optional[float] = Field(None, description="Fuel surcharge amount")
    accessorial_charges: Optional[float] = Field(None, description="Accessorial charges")
    tax_amount: Optional[float] = Field(None, description="Tax amount")
    total_amount: Optional[float] = Field(None, description="Total invoice amount")
    currency: Optional[str] = Field("USD", description="Currency code")
    
    # Payment terms
    payment_terms: Optional[str] = Field(None, description="Payment terms")
    payment_method: Optional[str] = Field(None, description="Payment method")
    
    # Line items for detailed charges
    line_items: List[Dict[str, Any]] = Field(default_factory=list, description="Detailed line items")
    
    # Confidence and validation
    confidence_score: float = Field(0.0, description="Confidence in extraction accuracy (0.0-1.0)")
    validation_flags: List[str] = Field(default_factory=list, description="Validation issues found")


class EnhancedInvoiceExtractor:
    """
    Enhanced invoice extractor using Marker API + Sonnet 3.5.
    
    NEW WORKFLOW (no preprocessing):
    1. Uses Datalab Marker API (force_ocr=True, use_llm=False) for structured markdown
    2. Feeds clean markdown directly to Sonnet 3.5 for semantic reasoning
    3. Achieves better extraction through organized input structure
    4. No preprocessing or regex/rules - pure AI extraction
    """
    
    def __init__(self):
        """Initialize the enhanced extractor."""
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        self.client = None
        
        if self.anthropic_api_key and ANTHROPIC_AVAILABLE:
            try:
                self.client = anthropic.AsyncAnthropic(api_key=self.anthropic_api_key)
                logger.info("Anthropic (Sonnet 3.5) async client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client: {e}")
        elif not ANTHROPIC_AVAILABLE:
            logger.warning("Anthropic package not available. Install with: pip install anthropic")
        else:
            logger.warning("ANTHROPIC_API_KEY not found - Invoice extraction will not be available")
        
        # Marker API client for structured preprocessing
        self.marker_client = DatalabMarkerClient()
        
        logger.info(f"Enhanced Invoice Extractor initialized - Sonnet 3.5: {'✓' if self.client else '✗'}, Marker API: {'✓' if self.marker_client.api_key else '✗'}")
    
    async def extract_fields_from_markdown(
        self, 
        markdown_content: str,
        marker_metadata: Dict[str, Any] = None,
        model: str = "claude-3-5-sonnet-20241022"
    ) -> Tuple[Dict[str, Any], float]:
        """
        Extract invoice fields from structured markdown using Sonnet 3.5.
        
        This is the core extraction that works with clean, organized markdown
        instead of raw OCR text, leading to much better results.
        """
        if not self.client:
            logger.error("Anthropic client not available")
            return {}, 0.0
        
        try:
            # Enhanced prompt optimized for structured markdown input
            system_prompt = """You are an expert freight invoice data extraction specialist working with structured markdown input.

The input is pre-processed, structured markdown from an advanced OCR system with layout understanding. This gives you clean, organized content with proper formatting, tables, and sections.

Extract freight invoice data with 99-100% accuracy. Focus on:

CORE IDENTIFIERS:
- Invoice numbers: Look for "Invoice", "Invoice #", "Invoice Number", "Bill Number"
- Dates: "Invoice Date", "Date", "Due Date", "Payment Due"

COMPANY INFORMATION:
- Vendor/Carrier: "From", "Bill From", "Vendor", "Carrier", "Transportation Company"
- Customer/Shipper: "To", "Bill To", "Customer", "Shipper", "Ship To"
- Addresses: Complete addresses including city, state, zip

FREIGHT REFERENCES:
- BOL: "Bill of Lading", "BOL", "B/L", "BOL Number"
- PRO: "Pro Number", "PRO#", "Progressive", "Tracking"
- Dates: "Pickup Date", "Delivery Date", "Ship Date"

FINANCIAL DETAILS:
- Base freight: "Freight Charges", "Base Rate", "Line Haul"
- Fuel surcharge: "Fuel Surcharge", "FSC", "Fuel Charge"
- Accessorials: "Detention", "Lumper", "Extra Stops", "Accessorial"
- Taxes: "Tax", "Sales Tax", "GST"
- Totals: "Total", "Amount Due", "Invoice Total"

PAYMENT INFORMATION:
- Terms: "Terms", "Payment Terms", "Net 30", "Due on Receipt"
- Method: "Payment Method", "Remit To"

MARKDOWN ADVANTAGES:
- Tables are properly formatted with | separators
- Headers and sections are clearly marked with #
- Lists are properly bulleted
- Key-value pairs are well-structured
- Financial data is often in organized tables

Use the markdown structure to understand document organization and extract fields with context.

Return a JSON object with the exact field names specified. Set confidence_score based on data completeness and clarity."""

            user_prompt = f"""Extract all freight invoice data from this structured markdown content:

{markdown_content}

Return valid JSON with these exact fields:
- invoice_number, invoice_date, due_date (dates in YYYY-MM-DD format)
- vendor_name, vendor_address
- customer_name, customer_address
- bol_number, pro_number, pickup_date, delivery_date (dates in YYYY-MM-DD format)
- subtotal, freight_charges, fuel_surcharge, accessorial_charges, tax_amount, total_amount (numeric values only, no currency symbols)
- currency, payment_terms, payment_method
- line_items (array of objects with description, quantity, unit_price, total)
- confidence_score (0.0-1.0), validation_flags (array)

IMPORTANT: 
- All monetary amounts must be numbers (e.g., 1250.00, not "$1,250.00" or "As Agreed")
- If you cannot determine a numeric value, use null
- Dates must be in YYYY-MM-DD format
- Extract line items from tables if present"""
            
            logger.info(f"Sending structured markdown to Sonnet 3.5 ({len(markdown_content)} chars)")
            
            # Make the API call to Sonnet 3.5
            response = await self.client.messages.create(
                model=model,
                max_tokens=4000,
                temperature=0.1,
                system=system_prompt,
                messages=[{
                    "role": "user", 
                    "content": user_prompt
                }]
            )
            
            # Extract response content
            response_content = response.content[0].text
            logger.info(f"Received Sonnet 3.5 response ({len(response_content)} chars)")
            
            # Parse JSON response
            try:
                # Claude often includes explanatory text around the JSON
                json_content = response_content.strip()
                
                # Try to find JSON content if wrapped in explanation
                if json_content.startswith('```json'):
                    json_content = json_content[7:]  # Remove ```json
                if json_content.endswith('```'):
                    json_content = json_content[:-3]  # Remove ```
                
                # Find JSON object bounds
                start_idx = json_content.find('{')
                end_idx = json_content.rfind('}') + 1
                
                if start_idx != -1 and end_idx > start_idx:
                    json_content = json_content[start_idx:end_idx]
                
                extracted_data = json.loads(json_content)
                logger.info("✓ JSON parsing successful")
                
                # Validate and calculate confidence
                confidence = extracted_data.get('confidence_score', 0.0)
                
                # Additional validation
                validation_confidence = self._validate_invoice_data(extracted_data)
                final_confidence = (confidence + validation_confidence) / 2
                
                # Update confidence in the data
                extracted_data['confidence_score'] = final_confidence
                
                logger.info(f"✓ Invoice extraction completed - confidence: {final_confidence:.3f}")
                return extracted_data, final_confidence
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing failed: {e}")
                logger.error(f"Response content: {response_content[:500]}...")
                return {}, 0.0
                
        except Exception as e:
            logger.error(f"Sonnet extraction failed: {e}")
            return {}, 0.0
    
    def _validate_invoice_data(self, data: Dict[str, Any]) -> float:
        """Validate extracted invoice data and return confidence score."""
        score = 0.0
        total_checks = 8
        
        # Check for required invoice fields
        if data.get('invoice_number'):
            score += 1.0
        if data.get('vendor_name'):
            score += 1.0
        if data.get('invoice_date'):
            score += 1.0
        if data.get('total_amount') is not None:
            score += 1.0
            
        # Check financial consistency
        if data.get('total_amount') and data.get('subtotal'):
            # Basic sanity check
            if data['total_amount'] >= data['subtotal']:
                score += 1.0
                
        # Check for freight-specific fields
        if data.get('bol_number') or data.get('pro_number'):
            score += 1.0
            
        # Check for complete company info
        if data.get('customer_name'):
            score += 1.0
            
        # Check for payment terms
        if data.get('payment_terms'):
            score += 1.0
        
        return score / total_checks
    
    async def extract_invoice_fields_enhanced(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str = "application/pdf"
    ) -> Tuple[ExtractedInvoiceData, float, bool]:
        """
        Enhanced invoice extraction workflow.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            mime_type: File MIME type
            
        Returns:
            Tuple of (extracted_data, confidence, needs_review)
        """
        logger.info(f"Starting enhanced invoice extraction: {filename}")
        
        try:
            # Step 1: Process with Marker API (no preprocessing)
            async with self.marker_client as client:
                marker_result = await client.process_document(
                    file_content=file_content,
                    filename=filename,
                    mime_type=mime_type,
                    language="English",
                    force_ocr=True,
                    use_llm=False,  # NO PREPROCESSING - raw structure only
                    output_format="markdown"
                )
            
            if not marker_result.success:
                logger.error(f"Marker API failed: {marker_result.error}")
                return ExtractedInvoiceData(), 0.0, True
            
            # Step 2: Extract with Sonnet 3.5
            extracted_dict, confidence = await self.extract_fields_from_markdown(
                markdown_content=marker_result.markdown_content,
                marker_metadata={"source": "enhanced_workflow"}
            )
            
            if not extracted_dict:
                logger.error("Sonnet extraction failed")
                return ExtractedInvoiceData(), 0.0, True
            
            # Step 3: Create validated data object
            try:
                extracted_data = ExtractedInvoiceData(**extracted_dict)
            except ValidationError as e:
                logger.error(f"Data validation failed: {e}")
                # Try to create with available fields
                safe_dict = {}
                for field_name, field_info in ExtractedInvoiceData.__fields__.items():
                    if field_name in extracted_dict:
                        try:
                            safe_dict[field_name] = extracted_dict[field_name]
                        except:
                            continue
                extracted_data = ExtractedInvoiceData(**safe_dict)
            
            # Step 4: Determine if human review needed
            needs_review = confidence < 0.8 or len(extracted_data.validation_flags) > 0
            
            logger.info(f"✓ Enhanced invoice extraction completed - confidence: {confidence:.3f}, needs_review: {needs_review}")
            
            return extracted_data, confidence, needs_review
            
        except Exception as e:
            logger.error(f"Enhanced invoice extraction failed: {e}")
            return ExtractedInvoiceData(), 0.0, True
    
    async def extract_invoice_fields(
        self,
        text_content: str,
        use_cross_validation: bool = False  # Not used in new approach
    ) -> Tuple[ExtractedInvoiceData, float, bool]:
        """
        Legacy method for compatibility.
        
        Note: This bypasses the enhanced Marker workflow and works with raw text.
        For best results, use extract_invoice_fields_enhanced() instead.
        """
        logger.warning("Using legacy text-based extraction. Consider using extract_invoice_fields_enhanced() for better results.")
        
        # Create a minimal markdown structure from text
        markdown_content = f"# Invoice Document\n\n{text_content}"
        
        extracted_dict, confidence = await self.extract_fields_from_markdown(
            markdown_content=markdown_content,
            marker_metadata={"source": "legacy_text"}
        )
        
        if not extracted_dict:
            return ExtractedInvoiceData(), 0.0, True
        
        try:
            extracted_data = ExtractedInvoiceData(**extracted_dict)
        except ValidationError as e:
            logger.error(f"Data validation failed: {e}")
            extracted_data = ExtractedInvoiceData()
        
        needs_review = confidence < 0.8
        return extracted_data, confidence, needs_review 
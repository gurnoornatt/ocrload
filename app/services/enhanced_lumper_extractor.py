"""
Enhanced Lumper Extractor with Marker API + Sonnet 3.5

New improved workflow for lumper receipts:
1. Datalab Marker API processes document with force_ocr=True, use_llm=True
2. Structured markdown output fed to Sonnet 3.5 for semantic reasoning
3. Much better extraction results due to cleaner, organized input

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


class ExtractedLumperData(BaseModel):
    """Structured lumper receipt data with validation - same schema as before."""
    
    # Core receipt identifiers
    receipt_number: Optional[str] = Field(None, description="Lumper receipt number")
    receipt_date: Optional[str] = Field(None, description="Receipt date in YYYY-MM-DD format")
    
    # Facility information
    facility_name: Optional[str] = Field(None, description="Warehouse/facility name")
    facility_address: Optional[str] = Field(None, description="Facility address")
    
    # Service details
    service_type: Optional[str] = Field(None, description="Type of lumper service")
    labor_hours: Optional[float] = Field(None, description="Total labor hours")
    hourly_rate: Optional[float] = Field(None, description="Hourly rate charged")
    
    # Equipment and load information
    trailer_number: Optional[str] = Field(None, description="Trailer/equipment number")
    load_number: Optional[str] = Field(None, description="Load/shipment number")
    carrier_name: Optional[str] = Field(None, description="Carrier/trucking company")
    driver_name: Optional[str] = Field(None, description="Driver name")
    
    # Charges and payment
    total_charges: Optional[float] = Field(None, description="Total lumper charges")
    tax_amount: Optional[float] = Field(None, description="Tax amount")
    payment_method: Optional[str] = Field(None, description="Payment method used")
    
    # Special services
    special_services: List[str] = Field(default_factory=list, description="List of special services provided")
    
    # Additional details
    notes: Optional[str] = Field(None, description="Additional notes or comments")
    
    # Confidence and validation
    confidence_score: float = Field(0.0, description="Confidence in extraction accuracy (0.0-1.0)")
    validation_flags: List[str] = Field(default_factory=list, description="Validation issues found")


class EnhancedLumperExtractor:
    """
    Enhanced lumper extractor using Marker API + Sonnet 3.5.
    
    NEW WORKFLOW:
    1. Uses Datalab Marker API (force_ocr=True, use_llm=True) for structured markdown
    2. Feeds clean markdown to Sonnet 3.5 for semantic reasoning
    3. Achieves better extraction through organized input structure
    """
    
    def __init__(self):
        """Initialize the enhanced extractor."""
        # Only Sonnet 3.5 - no more GPT-4o
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        self.anthropic_client = None
        
        if self.anthropic_api_key and ANTHROPIC_AVAILABLE:
            try:
                self.anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
                logger.info("Anthropic (Sonnet 3.5) client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client: {e}")
        elif not ANTHROPIC_AVAILABLE:
            logger.warning("Anthropic package not available. Install with: pip install anthropic")
        else:
            logger.warning("ANTHROPIC_API_KEY not found - Lumper extraction will not be available")
        
        # Marker API client for structured preprocessing
        self.marker_client = DatalabMarkerClient(preprocessing_enabled=False)
        
        logger.info(f"Enhanced Lumper Extractor initialized - Sonnet 3.5: {'✓' if self.anthropic_client else '✗'}, Marker API: {'✓' if self.marker_client.api_key else '✗'}")
    
    async def extract_fields_from_markdown(
        self, 
        markdown_content: str,
        marker_metadata: Dict[str, Any] = None,
        model: str = "claude-3-5-sonnet-20241022"
    ) -> Tuple[Dict[str, Any], float]:
        """
        Extract lumper fields from structured markdown using Sonnet 3.5.
        
        This is the core extraction that works with clean, organized markdown
        instead of raw OCR text, leading to much better results.
        """
        if not self.anthropic_client:
            logger.error("Anthropic client not available")
            return {}, 0.0
        
        try:
            # Enhanced prompt optimized for structured markdown input
            system_prompt = """You are an expert lumper receipt data extraction specialist working with structured markdown input.

The input is pre-processed, structured markdown from an advanced OCR system with layout understanding. This gives you clean, organized content with proper formatting, tables, and sections.

Extract lumper receipt data with 99-100% accuracy. Focus on:

CORE IDENTIFIERS:
- Receipt numbers: Look for "Receipt", "Receipt #", "Receipt Number", "Lumper Receipt"
- Receipt dates: Look for "Date", "Receipt Date", "Service Date"

FACILITY INFORMATION:
- Facility: "Warehouse", "Facility", "Location", "Terminal", "DC"
- Address: Complete facility address including city, state, zip

SERVICE DETAILS:
- Service type: "Loading", "Unloading", "Lumper Service", "Labor"
- Hours: "Hours", "Labor Hours", "Time", "Duration"
- Rate: "Rate", "Hourly Rate", "$/Hour", "Per Hour"

EQUIPMENT & LOAD:
- Trailer: "Trailer", "Unit", "Equipment", "Trailer #"
- Load: "Load", "Load #", "Shipment", "BOL"
- Carrier: "Carrier", "Trucking", "Transportation"
- Driver: "Driver", "Driver Name"

CHARGES & PAYMENT:
- Total: "Total", "Amount", "Charges", "Cost"
- Tax: "Tax", "Sales Tax", "GST"
- Payment: "Payment", "Paid By", "Method"

SPECIAL SERVICES:
- Look for additional services like "Detention", "Waiting Time", "Extra Labor"

MARKDOWN ADVANTAGES:
- Tables are properly formatted with | separators
- Headers and sections are clearly marked with #
- Lists are properly bulleted
- Key-value pairs are well-structured

Use the markdown structure to understand document organization and extract fields with context.

Return a JSON object with the exact field names specified. Set confidence_score based on data completeness and clarity."""

            user_prompt = f"""Extract all lumper receipt data from this structured markdown content:

{markdown_content}

Return valid JSON with these exact fields:
- receipt_number, receipt_date (YYYY-MM-DD format)
- facility_name, facility_address
- service_type, labor_hours, hourly_rate
- trailer_number, load_number, carrier_name, driver_name
- total_charges, tax_amount, payment_method
- special_services (array), notes
- confidence_score (0.0-1.0), validation_flags (array)"""
            
            logger.info(f"Sending structured markdown to Sonnet 3.5 ({len(markdown_content)} chars)")
            
            # Make API call to Sonnet 3.5
            response = self.anthropic_client.messages.create(
                model=model,
                max_tokens=4000,
                temperature=0.1,  # Low temperature for accuracy
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": user_prompt
                }]
            )
            
            # Extract and parse response
            response_content = response.content[0].text
            logger.info(f"Received Sonnet 3.5 response ({len(response_content)} chars)")
            
            # Parse JSON response
            try:
                # Claude often includes explanatory text around the JSON
                json_content = response_content.strip()
                
                # Method 1: Look for JSON in markdown code blocks
                if '```json' in json_content:
                    start = json_content.find('```json') + 7
                    end = json_content.find('```', start)
                    if end != -1:
                        json_content = json_content[start:end].strip()
                elif '```' in json_content and '{' in json_content:
                    # Generic code block
                    lines = json_content.split('\n')
                    json_lines = []
                    in_code_block = False
                    for line in lines:
                        if line.strip().startswith('```'):
                            in_code_block = not in_code_block
                            continue
                        if in_code_block:
                            json_lines.append(line)
                    json_content = '\n'.join(json_lines).strip()
                
                # Method 2: Extract JSON object if no code blocks found
                if not json_content.startswith('{') and '{' in json_content:
                    start = json_content.find('{')
                    end = json_content.rfind('}') + 1
                    if start != -1 and end > start:
                        json_content = json_content[start:end]
                
                extracted_data = json.loads(json_content)
                confidence = extracted_data.get('confidence_score', 0.8)
                
                logger.info(f"Sonnet 3.5 extraction successful - confidence: {confidence:.1%}")
                return extracted_data, confidence
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Sonnet 3.5 JSON response: {e}")
                
                # Final attempt: Try to find and extract the JSON object
                if '{' in response_content and '}' in response_content:
                    try:
                        # Find the largest JSON object in the response
                        start = response_content.find('{')
                        brace_count = 0
                        end = start
                        
                        for i in range(start, len(response_content)):
                            if response_content[i] == '{':
                                brace_count += 1
                            elif response_content[i] == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    end = i + 1
                                    break
                        
                        if end > start:
                            json_part = response_content[start:end]
                            extracted_data = json.loads(json_part)
                            confidence = extracted_data.get('confidence_score', 0.5)
                            logger.info(f"Successfully extracted JSON from response - confidence: {confidence:.1%}")
                            return extracted_data, confidence
                    except Exception as parse_error:
                        logger.error(f"Final JSON extraction attempt failed: {parse_error}")
                
                logger.error(f"Raw response sample: {response_content[:500]}...")
                return {}, 0.0
        
        except Exception as e:
            logger.error(f"Sonnet 3.5 extraction failed: {e}")
            return {}, 0.0
    
    def _validate_lumper_data(self, data: ExtractedLumperData) -> float:
        """Validate extracted lumper data and return validation score."""
        validation_score = 1.0
        issues = []
        
        # Core field validation
        critical_fields = [
            ('receipt_number', 'Receipt number missing'),
            ('facility_name', 'Facility name missing'),
            ('service_type', 'Service type missing')
        ]
        
        for field, message in critical_fields:
            if not getattr(data, field):
                issues.append(message)
                validation_score -= 0.15
        
        # Date validation
        if data.receipt_date:
            try:
                datetime.strptime(data.receipt_date, '%Y-%m-%d')
            except ValueError:
                issues.append('Invalid receipt_date format')
                validation_score -= 0.1
        
        # Numerical validation
        for field, field_name in [
            ('labor_hours', 'labor hours'),
            ('hourly_rate', 'hourly rate'),
            ('total_charges', 'total charges'),
            ('tax_amount', 'tax amount')
        ]:
            value = getattr(data, field)
            if value is not None and value < 0:
                issues.append(f'Invalid {field_name} value')
                validation_score -= 0.05
        
        # Business logic validation
        if data.labor_hours and data.hourly_rate and data.total_charges:
            expected_total = data.labor_hours * data.hourly_rate
            if abs(expected_total - data.total_charges) > (data.total_charges * 0.2):  # 20% tolerance
                issues.append('Total charges inconsistent with hours × rate')
                validation_score -= 0.1
        
        # Update validation flags
        data.validation_flags = issues
        
        return max(0.0, validation_score)
    
    async def extract_lumper_fields_enhanced(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str = "image/jpeg"
    ) -> Tuple[ExtractedLumperData, float, bool]:
        """
        Complete enhanced lumper extraction using new Marker API + Sonnet 3.5 workflow.
        
        NEW IMPROVED FLOW:
        1. Datalab Marker API (force_ocr=True, use_llm=True) → structured markdown
        2. Sonnet 3.5 semantic reasoning on clean markdown → extracted fields
        
        Args:
            file_content: Document file content as bytes
            filename: Original filename
            mime_type: File MIME type
            
        Returns:
            Tuple of (extracted_data, confidence, needs_review)
        """
        logger.info(f"Starting enhanced lumper extraction for {filename}")
        
        try:
            # Step 1: Process with Marker API for structured markdown
            async with self.marker_client as marker:
                marker_result = await marker.process_document(
                    file_content=file_content,
                    filename=filename,
                    mime_type=mime_type,
                    language="English",
                    force_ocr=True,      # Force OCR as specified
                    use_llm=False,       # NO PREPROCESSING as requested
                    output_format="markdown"
                )
            
            if not marker_result.success or not marker_result.markdown_content:
                logger.error(f"Marker API failed for {filename}: {marker_result.error}")
                # Return empty result
                empty_data = ExtractedLumperData()
                empty_data.validation_flags = [f"Marker API failed: {marker_result.error}"]
                return empty_data, 0.0, True
            
            logger.info(f"Marker API success: {marker_result.content_length} chars, {len(marker_result.get_tables())} tables detected")
            
            # Step 2: Extract fields from structured markdown using Sonnet 3.5
            extracted_dict, ai_confidence = await self.extract_fields_from_markdown(
                markdown_content=marker_result.markdown_content,
                marker_metadata=marker_result.metadata
            )
            
            if not extracted_dict:
                logger.error(f"Sonnet 3.5 extraction failed for {filename}")
                empty_data = ExtractedLumperData()
                empty_data.validation_flags = ["AI extraction failed"]
                return empty_data, 0.0, True
            
            # Step 3: Structure and validate the data
            try:
                # Fix notes field if it's a dict or list
                if isinstance(extracted_dict.get('notes'), dict):
                    # Convert dict to readable string
                    notes_dict = extracted_dict['notes']
                    notes_parts = [f"{k}: {v}" for k, v in notes_dict.items()]
                    extracted_dict['notes'] = " | ".join(notes_parts)
                elif isinstance(extracted_dict.get('notes'), list):
                    extracted_dict['notes'] = ' | '.join(str(item) for item in extracted_dict['notes'])
                
                # Ensure special_services is a list
                if isinstance(extracted_dict.get('special_services'), str):
                    extracted_dict['special_services'] = [extracted_dict['special_services']]
                elif extracted_dict.get('special_services') is None:
                    extracted_dict['special_services'] = []
                
                extracted_data = ExtractedLumperData(**extracted_dict)
            except ValidationError as e:
                logger.error(f"Data validation failed for {filename}: {e}")
                extracted_data = ExtractedLumperData()
                extracted_data.validation_flags = [f"Data validation error: {str(e)}"]
                ai_confidence = 0.0
            
            # Step 4: Final validation and scoring
            validation_score = self._validate_lumper_data(extracted_data)
            final_confidence = min(ai_confidence, validation_score)
            
            # Update confidence in the data
            extracted_data.confidence_score = final_confidence
            
            # Determine if review is needed
            needs_review = final_confidence < 0.75 or len(extracted_data.validation_flags) > 2
            
            logger.info(f"Enhanced lumper extraction complete - Confidence: {final_confidence:.1%}, Review needed: {needs_review}")
            
            return extracted_data, final_confidence, needs_review
            
        except Exception as e:
            logger.error(f"Enhanced lumper extraction failed for {filename}: {e}")
            empty_data = ExtractedLumperData()
            empty_data.validation_flags = [f"Extraction error: {str(e)}"]
            return empty_data, 0.0, True
    
    # Backwards compatibility method
    async def extract_lumper_fields(
        self,
        text_content: str,
        use_cross_validation: bool = False  # Not used in new approach
    ) -> Tuple[ExtractedLumperData, float, bool]:
        """
        Backwards compatibility method.
        
        Note: This is kept for compatibility but the new enhanced method
        that processes files directly is recommended for better results.
        """
        logger.warning("Using legacy text-based extraction. Consider using extract_lumper_fields_enhanced() for better results.")
        
        # Use Sonnet 3.5 directly on the text
        extracted_dict, confidence = await self.extract_fields_from_markdown(text_content)
        
        if not extracted_dict:
            empty_data = ExtractedLumperData()
            empty_data.validation_flags = ["Legacy extraction failed"]
            return empty_data, 0.0, True
        
        try:
            extracted_data = ExtractedLumperData(**extracted_dict)
        except ValidationError as e:
            extracted_data = ExtractedLumperData()
            extracted_data.validation_flags = [f"Validation error: {str(e)}"]
            confidence = 0.0
        
        validation_score = self._validate_lumper_data(extracted_data)
        final_confidence = min(confidence, validation_score)
        extracted_data.confidence_score = final_confidence
        
        needs_review = final_confidence < 0.75
        return extracted_data, final_confidence, needs_review 
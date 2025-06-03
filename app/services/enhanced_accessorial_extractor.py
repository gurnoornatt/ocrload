"""
Enhanced Accessorial Extractor with Marker API + Sonnet 3.5

New improved workflow for accessorial documents (detention slips, load slips, etc.):
1. Datalab Marker API processes document with force_ocr=True, use_llm=False (NO PREPROCESSING)
2. Structured markdown output fed to Sonnet 3.5 for semantic reasoning
3. Much better extraction results due to cleaner, organized input

Supports various accessorial service types:
- Detention charges
- Load slips/extra stops
- Layover charges
- Waiting time
- Additional services
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

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


class ExtractedAccessorialData(BaseModel):
    """Structured accessorial document data with validation."""
    
    # Core identifiers
    document_number: Optional[str] = Field(None, description="Document/reference number")
    document_date: Optional[str] = Field(None, description="Document date in YYYY-MM-DD format")
    
    # Service information
    service_type: Optional[str] = Field(None, description="Type of accessorial service (detention, layover, load_slip, extra_stop, etc.)")
    service_description: Optional[str] = Field(None, description="Detailed description of service provided")
    
    # Location and timing
    location: Optional[str] = Field(None, description="Location where service was performed")
    start_time: Optional[str] = Field(None, description="Service start time/date")
    end_time: Optional[str] = Field(None, description="Service end time/date")
    duration_hours: Optional[float] = Field(None, description="Total duration in hours")
    
    # Equipment and load information
    truck_number: Optional[str] = Field(None, description="Truck/tractor number")
    trailer_number: Optional[str] = Field(None, description="Trailer number")
    driver_name: Optional[str] = Field(None, description="Driver name")
    carrier_name: Optional[str] = Field(None, description="Carrier/company name")
    load_number: Optional[str] = Field(None, description="Load/shipment number")
    bol_number: Optional[str] = Field(None, description="Bill of lading number")
    
    # Financial information - UPDATED to accept both numbers and strings
    rate_per_hour: Optional[Union[float, str]] = Field(None, description="Hourly rate for service (number or text like 'REGULAR RATE')")
    rate_flat: Optional[Union[float, str]] = Field(None, description="Flat rate for service (number or text)")
    total_charges: Optional[float] = Field(None, description="Total charges for service")
    currency: Optional[str] = Field(default="USD", description="Currency for charges")
    
    # Approval and authorization
    approved_by: Optional[str] = Field(None, description="Name of person who approved the charge")
    approval_signature: Optional[str] = Field(None, description="Signature or approval indicator")
    authorization_code: Optional[str] = Field(None, description="Authorization/approval code")
    
    # Justification and notes
    charge_justification: Optional[str] = Field(None, description="Reason/justification for the charge")
    customer_name: Optional[str] = Field(None, description="Customer/shipper name")
    notes: Optional[str] = Field(None, description="Additional notes or comments")
    
    # Special services and details
    special_services: List[str] = Field(default_factory=list, description="List of additional services")
    
    # Validation and confidence
    confidence_score: float = Field(0.0, description="Confidence in extraction accuracy (0.0-1.0)")
    validation_flags: List[str] = Field(default_factory=list, description="Validation issues found")


class EnhancedAccessorialExtractor:
    """
    Enhanced accessorial extractor using Marker API + Sonnet 3.5.
    
    NEW WORKFLOW (NO PREPROCESSING):
    1. Uses Datalab Marker API (force_ocr=True, use_llm=False) for structured markdown
    2. Feeds clean markdown to Sonnet 3.5 for semantic reasoning
    3. Achieves better extraction through organized input structure
    
    Supports various accessorial documents:
    - Detention slips
    - Load slips
    - Layover charges
    - Extra stop charges
    - Waiting time documentation
    """
    
    def __init__(self):
        """Initialize the enhanced accessorial extractor."""
        # Only Sonnet 3.5 - consistent with our new approach
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
            logger.warning("ANTHROPIC_API_KEY not found - Accessorial extraction will not be available")
        
        # Marker API client (NO preprocessing)
        self.marker_client = DatalabMarkerClient(preprocessing_enabled=False)
        
        logger.info(f"Enhanced Accessorial Extractor initialized - Sonnet 3.5: {'✓' if self.anthropic_client else '✗'}, Marker API: {'✓' if self.marker_client.api_key else '✗'}")
    
    async def extract_fields_from_markdown(
        self, 
        markdown_content: str,
        marker_metadata: Dict[str, Any] = None,
        model: str = "claude-3-5-sonnet-20241022"
    ) -> Tuple[Dict[str, Any], float]:
        """
        Extract accessorial fields from structured markdown using Sonnet 3.5.
        
        This is the core extraction that works with clean, organized markdown
        instead of raw OCR text, leading to much better results.
        """
        if not self.anthropic_client:
            logger.error("Anthropic client not available")
            return {}, 0.0
        
        try:
            # Enhanced prompt optimized for accessorial documents
            system_prompt = """You are an expert accessorial document data extraction specialist working with structured markdown input.

The input is pre-processed, structured markdown from an advanced OCR system with layout understanding. This gives you clean, organized content with proper formatting, tables, and sections.

Extract accessorial document data with 99-100% accuracy. Focus on:

DOCUMENT IDENTIFICATION:
- Document numbers: "Doc #", "Reference", "Slip #", "Ticket #"
- Dates: "Date", "Service Date", "Issue Date"

SERVICE INFORMATION:
- Service types: "Detention", "Layover", "Load Slip", "Extra Stop", "Waiting Time", "Demurrage"
- Service descriptions: Detailed explanation of what service was provided

TIMING & LOCATION:
- Start/End times: "Start Time", "End Time", "Arrival", "Departure"
- Duration: "Hours", "Duration", "Time Spent"
- Location: "Location", "Address", "Facility", "Terminal"

EQUIPMENT & PERSONNEL:
- Truck: "Truck #", "Tractor", "Unit #"
- Trailer: "Trailer #", "Equipment"
- Driver: "Driver", "Operator"
- Carrier: "Carrier", "Company", "Fleet"

LOAD INFORMATION:
- Load: "Load #", "Shipment", "Trip"
- BOL: "BOL", "Bill of Lading"

FINANCIAL DETAILS:
- Rates: "Rate", "$/Hour", "Per Hour", "Flat Rate"
- Total: "Total", "Amount", "Charges", "Cost"
- Currency: Usually USD

APPROVAL & AUTHORIZATION:
- Approver: "Approved by", "Authorized by", "Supervisor"
- Signatures: Look for signature blocks or approval indicators
- Authorization codes: Reference numbers for approval

JUSTIFICATION:
- Reason: "Reason", "Justification", "Cause", "Due to"
- Customer: "Customer", "Shipper", "Consignee"

MARKDOWN ADVANTAGES:
- Tables are properly formatted with | separators
- Headers and sections are clearly marked with #
- Form fields are well-structured
- Time stamps and signatures are clearly indicated

Use the markdown structure to understand document organization and extract fields with context.

Return a JSON object with the exact field names specified. Set confidence_score based on data completeness and clarity."""

            user_prompt = f"""Extract all accessorial document data from this structured markdown content:

{markdown_content}

Return valid JSON with these exact fields:
- document_number, document_date (YYYY-MM-DD format)
- service_type, service_description
- location, start_time, end_time, duration_hours
- truck_number, trailer_number, driver_name, carrier_name
- load_number, bol_number
- rate_per_hour, rate_flat, total_charges, currency
- approved_by, approval_signature, authorization_code
- charge_justification, customer_name, notes
- special_services (array)
- confidence_score (0.0-1.0), validation_flags (array)

Focus on accuracy and extract all available information. If a field is not present, use null."""
            
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
            
            # Parse JSON response using the same logic as other extractors
            try:
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
    
    def _validate_accessorial_data(self, data: ExtractedAccessorialData) -> float:
        """Validate extracted accessorial data and return validation score."""
        validation_score = 1.0
        issues = []
        
        # Core field validation
        critical_fields = [
            ('service_type', 'Service type missing'),
            ('location', 'Service location missing'),
        ]
        
        for field, message in critical_fields:
            if not getattr(data, field):
                issues.append(message)
                validation_score -= 0.15
        
        # Date validation
        if data.document_date:
            try:
                datetime.strptime(data.document_date, '%Y-%m-%d')
            except ValueError:
                issues.append('Invalid document_date format')
                validation_score -= 0.1
        
        # Numerical validation - UPDATED to handle string rate fields
        for field, field_name in [
            ('duration_hours', 'duration hours'),
            ('rate_per_hour', 'hourly rate'),
            ('rate_flat', 'flat rate'),
            ('total_charges', 'total charges')
        ]:
            value = getattr(data, field)
            # Only validate numerical values, skip strings for rate fields
            if value is not None:
                if isinstance(value, (int, float)) and value < 0:
                    issues.append(f'Invalid {field_name} value')
                    validation_score -= 0.05
                elif isinstance(value, str) and field in ['rate_per_hour', 'rate_flat']:
                    # String values are OK for rate fields (like "REGULAR RATE")
                    pass
                elif isinstance(value, str) and field not in ['rate_per_hour', 'rate_flat']:
                    # String values in numerical fields that should be numbers
                    issues.append(f'Invalid {field_name} format (expected number)')
                    validation_score -= 0.05
        
        # Business logic validation - UPDATED to handle string rates
        if data.duration_hours and data.rate_per_hour and data.total_charges:
            # Only calculate if rate_per_hour is numeric
            if isinstance(data.rate_per_hour, (int, float)):
                expected_total = data.duration_hours * data.rate_per_hour
                if abs(expected_total - data.total_charges) > (data.total_charges * 0.2):  # 20% tolerance
                    issues.append('Total charges inconsistent with duration × rate')
                    validation_score -= 0.1
        
        # Update validation flags
        data.validation_flags = issues
        
        return max(0.0, validation_score)
    
    async def extract_accessorial_fields_enhanced(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str = "image/jpeg"
    ) -> Tuple[ExtractedAccessorialData, float, bool]:
        """
        Complete enhanced accessorial extraction using new Marker API + Sonnet 3.5 workflow.
        
        NEW IMPROVED FLOW (NO PREPROCESSING):
        1. Datalab Marker API (force_ocr=True, use_llm=False) → structured markdown
        2. Sonnet 3.5 semantic reasoning on clean markdown → extracted fields
        
        Args:
            file_content: Document file content as bytes
            filename: Original filename
            mime_type: File MIME type
            
        Returns:
            Tuple of (extracted_data, confidence, needs_review)
        """
        logger.info(f"Starting enhanced accessorial extraction for {filename}")
        
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
                empty_data = ExtractedAccessorialData()
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
                empty_data = ExtractedAccessorialData()
                empty_data.validation_flags = ["AI extraction failed"]
                return empty_data, 0.0, True
            
            # Step 3: Structure and validate the data
            try:
                # Clean up field types - Claude sometimes returns structured data
                
                # Fix location field if it's a dict (Claude sometimes structures addresses)
                if isinstance(extracted_dict.get('location'), dict):
                    location_dict = extracted_dict['location']
                    if 'facility' in location_dict and 'city' in location_dict and 'state' in location_dict:
                        extracted_dict['location'] = f"{location_dict['facility']}, {location_dict['city']}, {location_dict['state']}"
                    elif 'city' in location_dict and 'state' in location_dict:
                        extracted_dict['location'] = f"{location_dict['city']}, {location_dict['state']}"
                    else:
                        # Convert any dict to string
                        location_parts = [f"{k}: {v}" for k, v in location_dict.items()]
                        extracted_dict['location'] = " | ".join(location_parts)
                
                # Fix approval_signature field if it's a boolean
                if isinstance(extracted_dict.get('approval_signature'), bool):
                    extracted_dict['approval_signature'] = "Yes" if extracted_dict['approval_signature'] else "No"
                
                # Fix notes field if it's a dict or list
                if isinstance(extracted_dict.get('notes'), dict):
                    # Convert dict to readable string
                    notes_dict = extracted_dict['notes']
                    notes_parts = [f"{k}: {v}" for k, v in notes_dict.items()]
                    extracted_dict['notes'] = " | ".join(notes_parts)
                elif isinstance(extracted_dict.get('notes'), list):
                    extracted_dict['notes'] = ' | '.join(str(item) for item in extracted_dict['notes'])
                
                # Fix rate fields that might be strings when they should be numbers
                for rate_field in ['rate_per_hour', 'rate_flat', 'total_charges', 'duration_hours']:
                    if rate_field in extracted_dict and extracted_dict[rate_field] is not None:
                        value = extracted_dict[rate_field]
                        if isinstance(value, str):
                            # Try to extract numbers from strings like "REGULAR RATE" or "$25.00"
                            import re
                            numbers = re.findall(r'[\d,]+\.?\d*', value.replace('$', '').replace(',', ''))
                            if numbers:
                                try:
                                    extracted_dict[rate_field] = float(numbers[0])
                                except ValueError:
                                    # If we can't convert to number, keep the original string for rate fields
                                    # Don't set to None - preserve the text information
                                    if rate_field in ['rate_per_hour', 'rate_flat']:
                                        # Keep as string for rates - this is valuable information
                                        pass  # Keep original value
                                    else:
                                        extracted_dict[rate_field] = None
                            else:
                                # No numbers found
                                if rate_field in ['rate_per_hour', 'rate_flat']:
                                    # Keep the original text for rate information
                                    pass  # Keep original value like "REGULAR RATE"
                                else:
                                    extracted_dict[rate_field] = None
                
                # Ensure special_services is a list
                if isinstance(extracted_dict.get('special_services'), str):
                    extracted_dict['special_services'] = [extracted_dict['special_services']]
                elif extracted_dict.get('special_services') is None:
                    extracted_dict['special_services'] = []
                
                # Clean string fields that might have extra whitespace
                for str_field in ['service_type', 'service_description', 'driver_name', 'carrier_name', 'customer_name']:
                    if str_field in extracted_dict and isinstance(extracted_dict[str_field], str):
                        extracted_dict[str_field] = extracted_dict[str_field].strip()
                
                extracted_data = ExtractedAccessorialData(**extracted_dict)
            except ValidationError as e:
                logger.error(f"Data validation failed for {filename}: {e}")
                extracted_data = ExtractedAccessorialData()
                extracted_data.validation_flags = [f"Data validation error: {str(e)}"]
                ai_confidence = 0.0
            
            # Step 4: Final validation and scoring
            validation_score = self._validate_accessorial_data(extracted_data)
            final_confidence = min(ai_confidence, validation_score)
            
            # Update confidence in the data
            extracted_data.confidence_score = final_confidence
            
            # Determine if review is needed
            needs_review = final_confidence < 0.75 or len(extracted_data.validation_flags) > 2
            
            logger.info(f"Enhanced accessorial extraction complete - Confidence: {final_confidence:.1%}, Review needed: {needs_review}")
            
            return extracted_data, final_confidence, needs_review
            
        except Exception as e:
            logger.error(f"Enhanced accessorial extraction failed for {filename}: {e}")
            empty_data = ExtractedAccessorialData()
            empty_data.validation_flags = [f"Extraction error: {str(e)}"]
            return empty_data, 0.0, True
    
    # Backwards compatibility method
    async def extract_accessorial_fields(
        self,
        text_content: str,
        document_type: str = "accessorial"
    ) -> Tuple[ExtractedAccessorialData, float, bool]:
        """
        Backwards compatibility method.
        
        Note: This is kept for compatibility but the new enhanced method
        that processes files directly is recommended for better results.
        """
        logger.warning("Using legacy text-based extraction. Consider using extract_accessorial_fields_enhanced() for better results.")
        
        # Use Sonnet 3.5 directly on the text
        extracted_dict, confidence = await self.extract_fields_from_markdown(text_content)
        
        if not extracted_dict:
            empty_data = ExtractedAccessorialData()
            empty_data.validation_flags = ["Legacy extraction failed"]
            return empty_data, 0.0, True
        
        try:
            extracted_data = ExtractedAccessorialData(**extracted_dict)
        except ValidationError as e:
            extracted_data = ExtractedAccessorialData()
            extracted_data.validation_flags = [f"Validation error: {str(e)}"]
            confidence = 0.0
        
        validation_score = self._validate_accessorial_data(extracted_data)
        final_confidence = min(confidence, validation_score)
        extracted_data.confidence_score = final_confidence
        
        needs_review = final_confidence < 0.75
        return extracted_data, final_confidence, needs_review 
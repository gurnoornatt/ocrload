"""
Enhanced BOL Extractor with Marker API + Sonnet 3.5

New improved workflow:
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


class ExtractedBOLData(BaseModel):
    """Structured BOL data with validation - same schema as before."""
    
    # Core BOL identifiers
    bol_number: Optional[str] = Field(None, description="Bill of Lading number")
    pro_number: Optional[str] = Field(None, description="Progressive number from carrier")
    
    # Dates
    pickup_date: Optional[str] = Field(None, description="Date picked up in YYYY-MM-DD format")
    delivery_date: Optional[str] = Field(None, description="Date delivered in YYYY-MM-DD format")
    
    # Shipper information
    shipper_name: Optional[str] = Field(None, description="Shipper company name")
    shipper_address: Optional[str] = Field(None, description="Complete shipper address")
    
    # Consignee information
    consignee_name: Optional[str] = Field(None, description="Consignee company name")
    consignee_address: Optional[str] = Field(None, description="Complete consignee address")
    
    # Carrier information
    carrier_name: Optional[str] = Field(None, description="Carrier/transportation company name")
    driver_name: Optional[str] = Field(None, description="Driver name")
    
    # Equipment information
    equipment_type: Optional[str] = Field(None, description="Type of equipment used")
    equipment_number: Optional[str] = Field(None, description="Equipment/trailer number")
    
    # Freight details
    commodity_description: Optional[str] = Field(None, description="Description of freight/goods")
    weight: Optional[float] = Field(None, description="Total weight")
    pieces: Optional[int] = Field(None, description="Number of pieces/packages")
    hazmat: Optional[bool] = Field(False, description="Hazardous materials flag")
    
    # Special instructions and charges
    special_instructions: Optional[str] = Field(None, description="Special handling instructions")
    freight_charges: Optional[float] = Field(None, description="Freight charges amount")
    
    # Confidence and validation
    confidence_score: float = Field(0.0, description="Confidence in extraction accuracy (0.0-1.0)")
    validation_flags: List[str] = Field(default_factory=list, description="Validation issues found")


class EnhancedBOLExtractor:
    """
    Enhanced BOL extractor using Marker API + Sonnet 3.5.
    
    NEW WORKFLOW:
    1. Uses Datalab Marker API (force_ocr=True, use_llm=True) for structured markdown
    2. Feeds clean markdown to Sonnet 3.5 for semantic reasoning
    3. Achieves better extraction through organized input structure
    """
    
    def __init__(self):
        """Initialize the enhanced extractor."""
        # Only Sonnet 3.5 - no more GPT-4o
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
            logger.warning("ANTHROPIC_API_KEY not found - BOL extraction will not be available")
        
        # Marker API client for structured preprocessing
        self.marker_client = DatalabMarkerClient()
        
        logger.info(f"Enhanced BOL Extractor initialized - Sonnet 3.5: {'✓' if self.client else '✗'}, Marker API: {'✓' if self.marker_client.api_key else '✗'}")
    
    async def extract_fields_from_markdown(
        self, 
        markdown_content: str,
        marker_metadata: Dict[str, Any] = None,
        model: str = "claude-3-5-sonnet-20241022"
    ) -> Tuple[Dict[str, Any], float]:
        """
        Extract BOL fields from structured markdown using Sonnet 3.5.
        
        This is the core extraction that works with clean, organized markdown
        instead of raw OCR text, leading to much better results.
        """
        if not self.client:
            logger.error("Anthropic client not available")
            return {}, 0.0
        
        try:
            # Enhanced prompt optimized for structured markdown input
            system_prompt = """You are an expert Bill of Lading (BOL) data extraction specialist working with structured markdown input.

The input is pre-processed, structured markdown from an advanced OCR system with layout understanding. This gives you clean, organized content with proper formatting, tables, and sections.

Extract BOL data with 99-100% accuracy. Focus on:

CORE IDENTIFIERS:
- BOL numbers: Look for "Bill of Lading", "BOL", "B/L", "BL Number"
- Pro numbers: Look for "Pro Number", "PRO#", "Progressive", "Tracking"

PARTY INFORMATION:
- Shipper: "Ship From", "Shipper", "Origin", "Consignor"
- Consignee: "Ship To", "Consignee", "Destination", "Deliver To"
- Carrier: "Carrier", "Transportation Company", "Trucking Company"

LOGISTICS DETAILS:
- Equipment: "Trailer", "Container", "Equipment", "Unit Number"
- Commodity: "Description", "Freight Description", "Goods", "Cargo"
- Weights: "Weight", "Gross Weight", "Net Weight", "Total Weight"
- Pieces: "Pieces", "Units", "Packages", "Count"

DATES & CHARGES:
- Pickup: "Pickup Date", "Ship Date", "Origin Date"
- Delivery: "Delivery Date", "Destination Date", "Due Date"
- Charges: "Freight Charges", "Total Charges", "Amount", "Cost"

MARKDOWN ADVANTAGES:
- Tables are properly formatted with | separators
- Headers and sections are clearly marked with #
- Lists are properly bulleted
- Key-value pairs are well-structured

Use the markdown structure to understand document organization and extract fields with context.

Return a JSON object with the exact field names specified. Set confidence_score based on data completeness and clarity."""

            user_prompt = f"""Extract all BOL data from this structured markdown content:

{markdown_content}

Return valid JSON with these exact fields:
- bol_number, pro_number
- pickup_date, delivery_date (YYYY-MM-DD format)
- shipper_name, shipper_address
- consignee_name, consignee_address
- carrier_name, driver_name
- equipment_type, equipment_number
- commodity_description, weight (numeric value only, no units), pieces (numeric value only)
- hazmat (boolean)
- special_instructions, freight_charges (numeric value only, no currency symbols)
- confidence_score (0.0-1.0), validation_flags (array)

IMPORTANT: 
- weight must be a number (e.g., 460.0, not "460.0 KG")
- freight_charges must be a number (e.g., 1250.00, not "As Agreed" or "$1,250")
- If you cannot determine a numeric value, use null
- pieces must be an integer (e.g., 5, not "5 pieces")"""
            
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
            
            # Debug: Check response structure
            logger.info(f"Anthropic API response type: {type(response)}")
            logger.info(f"Response content type: {type(response.content)}")
            logger.info(f"Response content length: {len(response.content)}")
            
            # Extract and parse response
            if not response.content or len(response.content) == 0:
                logger.error("Anthropic API returned empty content array")
                return {}, 0.0
                
            response_content = response.content[0].text
            logger.info(f"Received Sonnet 3.5 response ({len(response_content)} chars)")
            
            # Debug: Show full response if it's short
            if len(response_content) < 500:
                logger.info(f"Full response: {response_content}")
            else:
                logger.info(f"Response preview: {response_content[:200]}...")
            
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
    
    def _validate_bol_data(self, data: ExtractedBOLData) -> float:
        """Validate extracted BOL data and return validation score."""
        validation_score = 1.0
        issues = []
        
        # Core field validation
        critical_fields = [
            ('bol_number', 'BOL number missing'),
            ('shipper_name', 'Shipper name missing'),
            ('consignee_name', 'Consignee name missing'),
            ('carrier_name', 'Carrier name missing')
        ]
        
        for field, message in critical_fields:
            if not getattr(data, field):
                issues.append(message)
                validation_score -= 0.15
        
        # Date validation
        for date_field in ['pickup_date', 'delivery_date']:
            date_value = getattr(data, date_field)
            if date_value:
                try:
                    datetime.strptime(date_value, '%Y-%m-%d')
                except ValueError:
                    issues.append(f'Invalid {date_field} format')
                    validation_score -= 0.1
        
        # Numerical validation
        if data.weight is not None and data.weight < 0:
            issues.append('Invalid weight value')
            validation_score -= 0.05
        
        if data.pieces is not None and data.pieces < 0:
            issues.append('Invalid pieces count')
            validation_score -= 0.05
        
        # Update validation flags
        data.validation_flags = issues
        
        return max(0.0, validation_score)
    
    async def extract_bol_fields_enhanced(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str = "image/jpeg"
    ) -> Tuple[ExtractedBOLData, float, bool]:
        """
        Complete enhanced BOL extraction using new Marker API + Sonnet 3.5 workflow.
        
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
        logger.info(f"Starting enhanced BOL extraction for {filename}")
        
        try:
            # Step 1: Process with Marker API for structured markdown
            async with self.marker_client as marker:
                marker_result = await marker.process_document(
                    file_content=file_content,
                    filename=filename,
                    mime_type=mime_type,
                    language="English",
                    force_ocr=True,      # Force OCR as specified
                    use_llm=True,        # CRUCIAL for better structure
                    output_format="markdown"
                )
            
            if not marker_result.success or not marker_result.markdown_content:
                logger.error(f"Marker API failed for {filename}: {marker_result.error}")
                # Return empty result
                empty_data = ExtractedBOLData()
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
                empty_data = ExtractedBOLData()
                empty_data.validation_flags = ["AI extraction failed"]
                return empty_data, 0.0, True
            
            # Step 3: Structure and validate the data
            try:
                extracted_data = ExtractedBOLData(**extracted_dict)
            except ValidationError as e:
                logger.error(f"Data validation failed for {filename}: {e}")
                extracted_data = ExtractedBOLData()
                extracted_data.validation_flags = [f"Data validation error: {str(e)}"]
                ai_confidence = 0.0
            
            # Step 4: Final validation and scoring
            validation_score = self._validate_bol_data(extracted_data)
            final_confidence = min(ai_confidence, validation_score)
            
            # Update confidence in the data
            extracted_data.confidence_score = final_confidence
            
            # Determine if review is needed
            needs_review = final_confidence < 0.7 or len(extracted_data.validation_flags) > 2
            
            logger.info(f"Enhanced BOL extraction complete - Confidence: {final_confidence:.1%}, Review needed: {needs_review}")
            
            return extracted_data, final_confidence, needs_review
            
        except Exception as e:
            logger.error(f"Enhanced BOL extraction failed for {filename}: {e}")
            empty_data = ExtractedBOLData()
            empty_data.validation_flags = [f"Extraction error: {str(e)}"]
            return empty_data, 0.0, True
    
    # Backwards compatibility method
    async def extract_bol_fields(
        self,
        text_content: str,
        use_cross_validation: bool = False  # Not used in new approach
    ) -> Tuple[ExtractedBOLData, float, bool]:
        """
        Backwards compatibility method.
        
        Note: This is kept for compatibility but the new enhanced method
        that processes files directly is recommended for better results.
        """
        logger.warning("Using legacy text-based extraction. Consider using extract_bol_fields_enhanced() for better results.")
        
        # Use Sonnet 3.5 directly on the text
        extracted_dict, confidence = await self.extract_fields_from_markdown(text_content)
        
        if not extracted_dict:
            empty_data = ExtractedBOLData()
            empty_data.validation_flags = ["Legacy extraction failed"]
            return empty_data, 0.0, True
        
        try:
            extracted_data = ExtractedBOLData(**extracted_dict)
        except ValidationError as e:
            extracted_data = ExtractedBOLData()
            extracted_data.validation_flags = [f"Validation error: {str(e)}"]
            confidence = 0.0
        
        validation_score = self._validate_bol_data(extracted_data)
        final_confidence = min(confidence, validation_score)
        extracted_data.confidence_score = final_confidence
        
        needs_review = final_confidence < 0.7
        return extracted_data, final_confidence, needs_review 
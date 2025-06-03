"""
Semantic Bill of Lading (BOL) Field Extractor

Uses GPT-4o or Claude to understand BOL content and extract fields with high accuracy.
Implements cross-validation, confidence scoring, and structured output for logistics accuracy.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from app.config.settings import settings

# Add Anthropic import
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

logger = logging.getLogger(__name__)


class ExtractedBOLData(BaseModel):
    """Structured BOL data with validation."""
    
    # Core BOL identifiers
    bol_number: Optional[str] = Field(None, description="Bill of Lading number")
    pro_number: Optional[str] = Field(None, description="Progressive number from carrier")
    
    # Dates - renamed to match database schema
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
    
    # Freight details - renamed to match database schema
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


class SemanticBOLExtractor:
    """Extract BOL fields using GPT-4o and Claude for cross-validation."""
    
    def __init__(self):
        """Initialize the semantic extractor with API clients."""
        # OpenAI setup
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_client = None
        
        if self.openai_api_key:
            try:
                self.openai_client = OpenAI(api_key=self.openai_api_key)
                logger.info("OpenAI client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
        
        # Anthropic setup using official SDK
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        self.anthropic_client = None
        
        if self.anthropic_api_key and ANTHROPIC_AVAILABLE:
            try:
                self.anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
                logger.info("Anthropic client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client: {e}")
        elif not ANTHROPIC_AVAILABLE:
            logger.warning("Anthropic package not available. Install with: pip install anthropic")
        
        logger.info(f"Initialized SemanticBOLExtractor - OpenAI: {'✓' if self.openai_client else '✗'}, Anthropic: {'✓' if self.anthropic_client else '✗'}")
    
    def extract_fields_openai(
        self, 
        text_content: str, 
        model: str = "gpt-4o-2024-08-06"
    ) -> Tuple[Dict[str, Any], float]:
        """
        Extract BOL fields using OpenAI GPT-4o with structured outputs.
        
        Uses the modern Chat Completions API with JSON schema mode.
        """
        if not self.openai_client:
            logger.error("OpenAI client not available")
            return {}, 0.0
        
        try:
            # Define the JSON schema for structured output
            schema = {
                "type": "object",
                "properties": {
                    "bol_number": {"type": ["string", "null"]},
                    "pro_number": {"type": ["string", "null"]},
                    "pickup_date": {"type": ["string", "null"]},
                    "delivery_date": {"type": ["string", "null"]},
                    "shipper_name": {"type": ["string", "null"]},
                    "shipper_address": {"type": ["string", "null"]},
                    "consignee_name": {"type": ["string", "null"]},
                    "consignee_address": {"type": ["string", "null"]},
                    "carrier_name": {"type": ["string", "null"]},
                    "driver_name": {"type": ["string", "null"]},
                    "equipment_type": {"type": ["string", "null"]},
                    "equipment_number": {"type": ["string", "null"]},
                    "commodity_description": {"type": ["string", "null"]},
                    "weight": {"type": ["number", "null"]},
                    "pieces": {"type": ["integer", "null"]},
                    "hazmat": {"type": ["boolean", "null"]},
                    "special_instructions": {"type": ["string", "null"]},
                    "freight_charges": {"type": ["number", "null"]},
                    "confidence_score": {"type": "number"},
                    "validation_flags": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["bol_number", "pro_number", "pickup_date", "delivery_date",
                           "shipper_name", "shipper_address", "consignee_name", "consignee_address",
                           "carrier_name", "driver_name", "equipment_type", "equipment_number",
                           "commodity_description", "weight", "pieces", "hazmat", 
                           "special_instructions", "freight_charges", "confidence_score", "validation_flags"],
                "additionalProperties": False
            }
            
            # Use the modern Chat Completions API with structured outputs
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert Bill of Lading (BOL) data extraction specialist. 
                        
Extract BOL data with 99-100% accuracy. Pay special attention to:
- BOL numbers, Pro numbers
- Shipper and consignee information (names and addresses)
- Carrier details and driver names
- Equipment information (type and numbers)
- Commodity descriptions, weights, and piece counts
- Special instructions and freight charges
- Dates in proper format (YYYY-MM-DD)

Common BOL field names to look for:
- "Bill of Lading", "BOL", "B/L" for BOL numbers
- "Pro Number", "PRO#", "Progressive" for pro numbers
- "Ship From", "Shipper", "Origin" for shipper info
- "Ship To", "Consignee", "Destination" for consignee info
- "Carrier", "Transportation Company" for carrier info
- "Driver", "Driver Name" for driver information
- "Equipment", "Trailer", "Container" for equipment info
- "Description", "Commodity", "Freight" for commodity description
- "Weight", "Gross Weight", "Net Weight" for weight information
- "Pieces", "Units", "Packages" for piece counts
- "Pickup", "Ship Date" for pickup dates
- "Delivery", "Delivery Date" for delivery dates

Return structured data with high confidence scoring."""
                    },
                    {
                        "role": "user",
                        "content": f"Extract all BOL data from this text:\n\n{text_content}"
                    }
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "bol_extraction",
                        "strict": True,
                        "schema": schema
                    }
                }
            )
            
            # Parse the structured response
            if response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content
                extracted_data = json.loads(content)
                
                # Create structured data object for validation
                structured_data = ExtractedBOLData(**extracted_data)
                
                # Validate BOL data
                confidence = self._validate_bol_data(structured_data)
                
                logger.info(f"OpenAI BOL extraction completed - confidence: {confidence:.3f}")
                return extracted_data, confidence
            else:
                logger.error("OpenAI response empty or invalid")
                return {}, 0.0
                
        except Exception as e:
            logger.error(f"OpenAI BOL extraction failed: {e}")
            return {}, 0.0
    
    async def extract_fields_anthropic(
        self, 
        text_content: str,
        model: str = "claude-3-5-sonnet-20241022"
    ) -> Tuple[Dict[str, Any], float]:
        """
        Extract BOL fields using Anthropic Claude with structured JSON output.
        """
        if not self.anthropic_client:
            logger.error("Anthropic client not available")
            return {}, 0.0
        
        try:
            prompt = f"""Extract all Bill of Lading (BOL) data from the following text and return it as a JSON object.

Pay special attention to:
- BOL numbers, Pro numbers
- Shipper and consignee information (names and complete addresses)
- Carrier details and driver names  
- Equipment information (type and numbers)
- Commodity descriptions, weights, and piece counts
- Special instructions and freight charges
- Dates in YYYY-MM-DD format

Common field names to look for:
- "Bill of Lading", "BOL", "B/L" for BOL numbers
- "Pro Number", "PRO#", "Progressive" for pro numbers
- "Ship From", "Shipper", "Origin" for shipper info
- "Ship To", "Consignee", "Destination" for consignee info
- "Carrier", "Transportation Company" for carrier info
- "Driver", "Driver Name" for driver information
- "Equipment", "Trailer", "Container" for equipment info
- "Description", "Commodity", "Freight" for commodity description
- "Weight", "Gross Weight", "Net Weight" for weight information
- "Pieces", "Units", "Packages" for piece counts
- "Pickup", "Ship Date" for pickup dates
- "Delivery", "Delivery Date" for delivery dates

Return JSON with these exact fields:
{{
    "bol_number": "string or null",
    "pro_number": "string or null", 
    "pickup_date": "YYYY-MM-DD or null",
    "delivery_date": "YYYY-MM-DD or null",
    "shipper_name": "string or null",
    "shipper_address": "string or null",
    "consignee_name": "string or null", 
    "consignee_address": "string or null",
    "carrier_name": "string or null",
    "driver_name": "string or null",
    "equipment_type": "string or null",
    "equipment_number": "string or null",
    "commodity_description": "string or null",
    "weight": "number or null",
    "pieces": "integer or null",
    "hazmat": "boolean or null",
    "special_instructions": "string or null",
    "freight_charges": "number or null",
    "confidence_score": "number between 0.0 and 1.0",
    "validation_flags": ["array of validation issues"]
}}

Document text:
{text_content}"""

            response = self.anthropic_client.messages.create(
                model=model,
                max_tokens=2000,
                temperature=0.1,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            if response.content:
                # Extract JSON from response content
                content = response.content[0].text
                
                # Find JSON in the response (handle markdown code blocks)
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_content = content[json_start:json_end]
                    extracted_data = json.loads(json_content)
                    
                    # Create structured data object for validation
                    structured_data = ExtractedBOLData(**extracted_data)
                    
                    # Validate BOL data
                    confidence = self._validate_bol_data(structured_data)
                    
                    logger.info(f"Anthropic BOL extraction completed - confidence: {confidence:.3f}")
                    return extracted_data, confidence
                else:
                    logger.error("No valid JSON found in Anthropic response")
                    return {}, 0.0
            else:
                logger.error("Anthropic response empty")
                return {}, 0.0
                
        except Exception as e:
            logger.error(f"Anthropic BOL extraction failed: {e}")
            return {}, 0.0
    
    def _validate_bol_data(self, data: ExtractedBOLData) -> float:
        """
        Validate extracted BOL data and return confidence score.
        
        Args:
            data: Extracted BOL data
            
        Returns:
            float: Confidence score (0.0-1.0)
        """
        confidence = 1.0
        validation_flags = []
        
        # Check for required core fields
        required_fields = [
            ("bol_number", "BOL number missing"),
            ("shipper_name", "Shipper name missing"),
            ("consignee_name", "Consignee name missing"),
            ("carrier_name", "Carrier name missing")
        ]
        
        for field_name, error_msg in required_fields:
            if not getattr(data, field_name):
                validation_flags.append(error_msg)
                confidence -= 0.15
        
        # Validate weight and pieces are positive numbers
        if data.weight is not None and data.weight <= 0:
            validation_flags.append("Invalid weight value")
            confidence -= 0.1
        
        if data.pieces is not None and data.pieces <= 0:
            validation_flags.append("Invalid pieces count")
            confidence -= 0.1
        
        # Check for reasonable freight charges
        if data.freight_charges is not None and data.freight_charges < 0:
            validation_flags.append("Negative freight charges")
            confidence -= 0.1
        
        # Validate date formats
        date_fields = ["pickup_date", "delivery_date"]
        for field_name in date_fields:
            date_value = getattr(data, field_name)
            if date_value:
                try:
                    datetime.strptime(date_value, "%Y-%m-%d")
                except ValueError:
                    validation_flags.append(f"Invalid {field_name} format")
                    confidence -= 0.05
        
        # Check address completeness
        if data.shipper_address and len(data.shipper_address.strip()) < 10:
            validation_flags.append("Incomplete shipper address")
            confidence -= 0.05
        
        if data.consignee_address and len(data.consignee_address.strip()) < 10:
            validation_flags.append("Incomplete consignee address")
            confidence -= 0.05
        
        # Ensure confidence doesn't go below 0
        confidence = max(0.0, confidence)
        
        # Update validation flags in the data
        data.validation_flags = validation_flags
        
        if validation_flags:
            logger.warning(f"BOL validation issues: {validation_flags}")
        else:
            logger.info("✓ BOL data validation passed")
        
        return confidence
    
    async def extract_bol_fields(
        self, 
        text_content: str,
        use_cross_validation: bool = True
    ) -> Tuple[ExtractedBOLData, float, bool]:
        """
        Extract BOL fields with optional cross-validation between OpenAI and Anthropic.
        
        Args:
            text_content: Raw text from BOL document
            use_cross_validation: Whether to use both models for validation
            
        Returns:
            Tuple of (extracted_data, confidence_score, needs_review)
        """
        if use_cross_validation and self.openai_client and self.anthropic_client:
            logger.info("Using cross-validation with OpenAI and Anthropic")
            
            # Get results from both models
            openai_data, openai_confidence = self.extract_fields_openai(text_content)
            anthropic_data, anthropic_confidence = await self.extract_fields_anthropic(text_content)
            
            # Compare results and pick the best one or combine
            if openai_confidence >= anthropic_confidence:
                primary_data = openai_data
                primary_confidence = openai_confidence
                logger.info(f"Using OpenAI result (confidence: {openai_confidence:.3f})")
            else:
                primary_data = anthropic_data
                primary_confidence = anthropic_confidence
                logger.info(f"Using Anthropic result (confidence: {anthropic_confidence:.3f})")
            
            # Create structured output
            structured_data = ExtractedBOLData(**primary_data)
            
        elif self.openai_client:
            logger.info("Using OpenAI only")
            openai_data, primary_confidence = self.extract_fields_openai(text_content)
            structured_data = ExtractedBOLData(**openai_data)
            
        elif self.anthropic_client:
            logger.info("Using Anthropic only")
            anthropic_data, primary_confidence = await self.extract_fields_anthropic(text_content)
            structured_data = ExtractedBOLData(**anthropic_data)
            
        else:
            logger.error("No AI clients available")
            return ExtractedBOLData(), 0.0, True
        
        # Determine if human review is needed
        needs_review = primary_confidence < 0.8 or len(structured_data.validation_flags) > 2
        
        logger.info(f"BOL extraction complete - confidence: {primary_confidence:.3f}, needs_review: {needs_review}")
        
        return structured_data, primary_confidence, needs_review 
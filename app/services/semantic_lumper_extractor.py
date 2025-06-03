"""
Semantic Lumper Receipt Field Extractor

Uses GPT-4o or Claude to understand lumper receipt content and extract fields with high accuracy.
Implements cross-validation, confidence scoring, and structured output for accurate billing.
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


class ExtractedLumperData(BaseModel):
    """Structured lumper receipt data with validation."""
    
    # Core receipt identifiers
    receipt_number: Optional[str] = Field(None, description="Receipt or ticket number")
    receipt_date: Optional[str] = Field(None, description="Receipt date in YYYY-MM-DD format")
    
    # Facility information
    facility_name: Optional[str] = Field(None, description="Warehouse or facility name")
    facility_address: Optional[str] = Field(None, description="Complete facility address")
    
    # Driver and carrier information
    driver_name: Optional[str] = Field(None, description="Driver name")
    carrier_name: Optional[str] = Field(None, description="Carrier/trucking company name")
    bol_number: Optional[str] = Field(None, description="Associated BOL number")
    
    # Service details
    service_type: Optional[str] = Field(None, description="Type of lumper service performed")
    labor_hours: Optional[float] = Field(None, description="Total labor hours")
    hourly_rate: Optional[float] = Field(None, description="Hourly rate charged")
    total_amount: Optional[float] = Field(None, description="Total amount charged")
    
    # Equipment and additional services
    equipment_used: Optional[str] = Field(None, description="Equipment used for service")
    special_services: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Additional services performed")
    notes: Optional[str] = Field(None, description="Additional notes or special instructions")
    
    # Confidence and validation
    confidence_score: float = Field(0.0, description="Confidence in extraction accuracy (0.0-1.0)")
    validation_flags: List[str] = Field(default_factory=list, description="Validation issues found")


class SemanticLumperExtractor:
    """Extract lumper receipt fields using GPT-4o and Claude for cross-validation."""
    
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
        
        logger.info(f"Initialized SemanticLumperExtractor - OpenAI: {'✓' if self.openai_client else '✗'}, Anthropic: {'✓' if self.anthropic_client else '✗'}")
    
    def extract_fields_openai(
        self, 
        text_content: str, 
        model: str = "gpt-4o-2024-08-06"
    ) -> Tuple[Dict[str, Any], float]:
        """
        Extract lumper receipt fields using OpenAI GPT-4o with structured outputs.
        
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
                    "receipt_number": {"type": ["string", "null"]},
                    "receipt_date": {"type": ["string", "null"]},
                    "facility_name": {"type": ["string", "null"]},
                    "facility_address": {"type": ["string", "null"]},
                    "driver_name": {"type": ["string", "null"]},
                    "carrier_name": {"type": ["string", "null"]},
                    "bol_number": {"type": ["string", "null"]},
                    "service_type": {"type": ["string", "null"]},
                    "labor_hours": {"type": ["number", "null"]},
                    "hourly_rate": {"type": ["number", "null"]},
                    "total_amount": {"type": ["number", "null"]},
                    "equipment_used": {"type": ["string", "null"]},
                    "special_services": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "properties": {
                                "service": {"type": "string"},
                                "quantity": {"type": ["number", "null"]},
                                "amount": {"type": "number"}
                            },
                            "required": ["service", "quantity", "amount"],
                            "additionalProperties": False
                        }
                    },
                    "notes": {"type": ["string", "null"]},
                    "confidence_score": {"type": "number"},
                    "validation_flags": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["receipt_number", "receipt_date", "facility_name", "facility_address",
                           "driver_name", "carrier_name", "bol_number", "service_type",
                           "labor_hours", "hourly_rate", "total_amount", "equipment_used",
                           "special_services", "notes", "confidence_score", "validation_flags"],
                "additionalProperties": False
            }
            
            # Use the modern Chat Completions API with structured outputs
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert lumper receipt data extraction specialist. 
                        
Extract lumper receipt data with 99-100% accuracy. Pay special attention to:
- Receipt or ticket numbers
- Facility information (warehouse names and addresses)
- Driver and carrier details
- Service types and labor information
- Billing details (hours, rates, totals)
- Equipment used and special services
- Dates in proper format (YYYY-MM-DD)

Common lumper receipt field names to look for:
- "Receipt", "Ticket", "Invoice" for receipt numbers
- "Date", "Service Date", "Work Date" for dates
- "Warehouse", "Facility", "Location" for facility info
- "Driver", "Trucker" for driver names
- "Carrier", "Trucking Company", "Fleet" for carrier info
- "BOL", "Bill of Lading" for BOL numbers
- "Service", "Work Type", "Labor" for service types
- "Hours", "Time", "Duration" for labor hours
- "Rate", "Per Hour", "$/HR" for rates
- "Total", "Amount", "Charge" for totals
- "Equipment", "Forklift", "Pallet Jack" for equipment
- "Notes", "Comments", "Special" for additional notes

Handle handwritten text and varied layouts. Return structured data with high confidence scoring."""
                    },
                    {
                        "role": "user",
                        "content": f"Extract all lumper receipt data from this text:\n\n{text_content}"
                    }
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "lumper_extraction",
                        "strict": True,
                        "schema": schema
                    }
                }
            )
            
            # Parse the response
            content = response.choices[0].message.content
            if not content:
                logger.error("Empty response from OpenAI")
                return {}, 0.0
            
            try:
                data = json.loads(content)
                logger.info(f"OpenAI extraction successful with confidence: {data.get('confidence_score', 0)}")
                return data, data.get('confidence_score', 0.0)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse OpenAI JSON response: {e}")
                return {}, 0.0
            
        except Exception as e:
            logger.error(f"OpenAI extraction failed: {e}")
            return {}, 0.0
    
    async def extract_fields_anthropic(
        self, 
        text_content: str,
        model: str = "claude-3-5-sonnet-20241022"
    ) -> Tuple[Dict[str, Any], float]:
        """
        Extract lumper receipt fields using Anthropic Claude.
        
        Uses Claude's native JSON generation capabilities.
        """
        if not self.anthropic_client:
            logger.error("Anthropic client not available")
            return {}, 0.0
        
        try:
            # Create the prompt with clear JSON schema
            system_prompt = """You are an expert lumper receipt data extraction specialist. Extract lumper receipt data with 99-100% accuracy.

Return a JSON object with these exact fields:
{
  "receipt_number": "string or null",
  "receipt_date": "YYYY-MM-DD string or null", 
  "facility_name": "string or null",
  "facility_address": "string or null",
  "driver_name": "string or null",
  "carrier_name": "string or null",
  "bol_number": "string or null",
  "service_type": "string or null",
  "labor_hours": "number or null",
  "hourly_rate": "number or null", 
  "total_amount": "number or null",
  "equipment_used": "string or null",
  "special_services": "array of objects or null",
  "notes": "string or null",
  "confidence_score": "number 0.0-1.0",
  "validation_flags": ["array of strings"]
}

Pay attention to handwritten text and varied layouts. Common field names:
- Receipt/Ticket numbers: "Receipt", "Ticket", "Invoice"
- Dates: "Date", "Service Date", "Work Date"
- Facilities: "Warehouse", "Facility", "Location"
- People: "Driver", "Trucker" 
- Companies: "Carrier", "Trucking Company", "Fleet"
- Service info: "Service", "Work Type", "Labor"
- Billing: "Hours", "Rate", "Total", "Amount"

Return ONLY the JSON object, no explanations."""

            user_prompt = f"Extract all lumper receipt data from this text:\n\n{text_content}"
            
            # Use Anthropic's message API
            response = self.anthropic_client.messages.create(
                model=model,
                max_tokens=2000,
                temperature=0.1,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            )
            
            # Parse the response
            content = response.content[0].text.strip()
            if not content:
                logger.error("Empty response from Anthropic")
                return {}, 0.0
            
            try:
                # Clean up the response in case it has markdown formatting
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                data = json.loads(content)
                logger.info(f"Anthropic extraction successful with confidence: {data.get('confidence_score', 0)}")
                return data, data.get('confidence_score', 0.0)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Anthropic JSON response: {e}")
                logger.debug(f"Raw content: {content}")
                return {}, 0.0
            
        except Exception as e:
            logger.error(f"Anthropic extraction failed: {e}")
            return {}, 0.0
    
    def _validate_lumper_data(self, data: ExtractedLumperData) -> float:
        """
        Validate extracted lumper receipt data and return confidence score.
        
        Args:
            data: Extracted lumper data
            
        Returns:
            float: Confidence score between 0.0 and 1.0
        """
        confidence_factors = []
        validation_flags = []
        
        # Receipt number validation
        if data.receipt_number and len(data.receipt_number.strip()) > 0:
            confidence_factors.append(0.15)
        else:
            validation_flags.append("missing_receipt_number")
        
        # Date validation
        if data.receipt_date:
            try:
                datetime.strptime(data.receipt_date, "%Y-%m-%d")
                confidence_factors.append(0.15)
            except ValueError:
                validation_flags.append("invalid_date_format")
                confidence_factors.append(0.05)
        else:
            validation_flags.append("missing_date")
        
        # Facility validation
        if data.facility_name and len(data.facility_name.strip()) > 2:
            confidence_factors.append(0.15)
        else:
            validation_flags.append("missing_facility_name")
        
        # Driver/carrier validation
        if data.driver_name and len(data.driver_name.strip()) > 2:
            confidence_factors.append(0.10)
        else:
            validation_flags.append("missing_driver_name")
        
        if data.carrier_name and len(data.carrier_name.strip()) > 2:
            confidence_factors.append(0.10)
        else:
            validation_flags.append("missing_carrier_name")
        
        # Service type validation
        if data.service_type and len(data.service_type.strip()) > 2:
            confidence_factors.append(0.10)
        else:
            validation_flags.append("missing_service_type")
        
        # Financial validation
        if data.total_amount and data.total_amount > 0:
            confidence_factors.append(0.15)
        else:
            validation_flags.append("missing_total_amount")
        
        # Hours and rate validation
        if data.labor_hours and data.labor_hours > 0:
            confidence_factors.append(0.05)
        else:
            validation_flags.append("missing_labor_hours")
        
        if data.hourly_rate and data.hourly_rate > 0:
            confidence_factors.append(0.05)
        else:
            validation_flags.append("missing_hourly_rate")
        
        # Cross-validation: hours * rate should approximate total
        if all([data.labor_hours, data.hourly_rate, data.total_amount]):
            calculated_total = data.labor_hours * data.hourly_rate
            if abs(calculated_total - data.total_amount) / data.total_amount < 0.1:  # Within 10%
                confidence_factors.append(0.10)
            else:
                validation_flags.append("amount_calculation_mismatch")
        
        # Update validation flags
        data.validation_flags = validation_flags
        
        # Calculate final confidence
        base_confidence = sum(confidence_factors) if confidence_factors else 0.0
        return min(base_confidence, 1.0)
    
    async def extract_lumper_fields(
        self, 
        text_content: str,
        use_cross_validation: bool = True
    ) -> Tuple[ExtractedLumperData, float, bool]:
        """
        Extract lumper receipt fields using both OpenAI and Anthropic for cross-validation.
        
        Args:
            text_content: OCR text from lumper receipt
            use_cross_validation: Whether to use both providers for validation
            
        Returns:
            Tuple of (extracted_data, confidence_score, cross_validation_passed)
        """
        logger.info("Starting lumper receipt extraction")
        
        openai_data = {}
        anthropic_data = {}
        openai_confidence = 0.0
        anthropic_confidence = 0.0
        
        # Extract using OpenAI
        if self.openai_client:
            try:
                openai_data, openai_confidence = self.extract_fields_openai(text_content)
                logger.info(f"OpenAI extraction confidence: {openai_confidence}")
            except Exception as e:
                logger.error(f"OpenAI extraction failed: {e}")
        
        # Extract using Anthropic (if cross-validation enabled)
        if use_cross_validation and self.anthropic_client:
            try:
                anthropic_data, anthropic_confidence = await self.extract_fields_anthropic(text_content)
                logger.info(f"Anthropic extraction confidence: {anthropic_confidence}")
            except Exception as e:
                logger.error(f"Anthropic extraction failed: {e}")
        
        # Determine best extraction
        if openai_confidence >= anthropic_confidence:
            primary_data = openai_data
            primary_confidence = openai_confidence
            backup_data = anthropic_data
        else:
            primary_data = anthropic_data
            primary_confidence = anthropic_confidence
            backup_data = openai_data
        
        # Validate the data structure
        try:
            lumper_data = ExtractedLumperData(**primary_data)
        except ValidationError as e:
            logger.error(f"Primary data validation failed: {e}")
            try:
                lumper_data = ExtractedLumperData(**backup_data)
                primary_confidence = anthropic_confidence if openai_confidence >= anthropic_confidence else openai_confidence
            except ValidationError as e2:
                logger.error(f"Backup data validation also failed: {e2}")
                lumper_data = ExtractedLumperData()
                primary_confidence = 0.0
        
        # Calculate final confidence
        final_confidence = self._validate_lumper_data(lumper_data)
        lumper_data.confidence_score = final_confidence
        
        # Cross-validation check
        cross_validation_passed = True
        if use_cross_validation and openai_data and anthropic_data:
            # Check key field agreement
            key_fields = ['receipt_number', 'facility_name', 'total_amount', 'service_type']
            disagreements = 0
            for field in key_fields:
                openai_val = openai_data.get(field)
                anthropic_val = anthropic_data.get(field)
                if openai_val != anthropic_val and openai_val and anthropic_val:
                    disagreements += 1
            
            if disagreements > len(key_fields) * 0.5:  # More than 50% disagreement
                cross_validation_passed = False
                lumper_data.validation_flags.append("cross_validation_failed")
        
        logger.info(f"Final lumper extraction confidence: {final_confidence}")
        return lumper_data, final_confidence, cross_validation_passed 
"""
Semantic Invoice Field Extractor

Uses GPT-4o or Claude to understand invoice content and extract fields with high accuracy.
Implements cross-validation, confidence scoring, and structured output for financial accuracy.
"""

import json
import logging
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
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


class ExtractedInvoiceData(BaseModel):
    """Structured invoice data with validation."""
    
    invoice_number: Optional[str] = Field(None, description="Invoice number or ID")
    vendor_name: Optional[str] = Field(None, description="Vendor/supplier name")
    invoice_date: Optional[str] = Field(None, description="Invoice date in YYYY-MM-DD format")
    due_date: Optional[str] = Field(None, description="Due date in YYYY-MM-DD format")
    
    # Critical financial fields for accuracy
    subtotal: Optional[float] = Field(None, description="Subtotal amount before tax (e.g., 145.00)")
    tax_amount: Optional[float] = Field(None, description="Tax amount (e.g., 9.06)")
    total_amount: Optional[float] = Field(None, description="Total amount including tax (e.g., 154.06)")
    
    currency: Optional[str] = Field(None, description="Currency code (USD, EUR, etc.)")
    
    # Line items
    line_items: List[Dict[str, Any]] = Field(default_factory=list, description="Individual line items from the invoice")
    
    # Confidence and validation
    confidence_score: float = Field(0.0, description="Confidence in extraction accuracy (0.0-1.0)")
    validation_flags: List[str] = Field(default_factory=list, description="Validation issues found")


class SemanticInvoiceExtractor:
    """Extract invoice fields using GPT-4o and Claude for cross-validation."""
    
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
        
        logger.info(f"Initialized SemanticInvoiceExtractor - OpenAI: {'✓' if self.openai_client else '✗'}, Anthropic: {'✓' if self.anthropic_client else '✗'}")
    
    def extract_fields_openai(
        self, 
        text_content: str, 
        model: str = "gpt-4o-2024-08-06"
    ) -> Tuple[Dict[str, Any], float]:
        """
        Extract invoice fields using OpenAI GPT-4o with structured outputs.
        
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
                    "invoice_number": {"type": ["string", "null"]},
                    "vendor_name": {"type": ["string", "null"]},
                    "invoice_date": {"type": ["string", "null"]},
                    "due_date": {"type": ["string", "null"]},
                    "subtotal": {"type": ["number", "null"]},
                    "tax_amount": {"type": ["number", "null"]},
                    "total_amount": {"type": ["number", "null"]},
                    "currency": {"type": ["string", "null"]},
                    "line_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string"},
                                "quantity": {"type": "number"},
                                "unit_price": {"type": "number"},
                                "total": {"type": "number"}
                            },
                            "required": ["description", "quantity", "unit_price", "total"],
                            "additionalProperties": False
                        }
                    },
                    "confidence_score": {"type": "number"},
                    "validation_flags": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["invoice_number", "vendor_name", "invoice_date", "due_date", 
                           "subtotal", "tax_amount", "total_amount", "currency", "line_items", 
                           "confidence_score", "validation_flags"],
                "additionalProperties": False
            }
            
            # Use the modern Chat Completions API with structured outputs
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert invoice data extraction specialist. 
                        
Extract invoice data with 99-100% accuracy. Pay special attention to:
- SUBTOTAL vs TOTAL amounts (subtotal is before tax, total is after tax)
- Tax calculations and line item details
- Invoice numbers, dates, and vendor information

Critical: If you see amounts like:
- Subtotal: $145.00
- Tax: $9.06  
- Total: $154.06

Make sure subtotal=145.00, tax_amount=9.06, total_amount=154.06

Return structured data with high confidence scoring."""
                    },
                    {
                        "role": "user",
                        "content": f"Extract all invoice data from this text:\n\n{text_content}"
                    }
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "invoice_extraction",
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
                structured_data = ExtractedInvoiceData(**extracted_data)
                
                # Validate financial calculations
                confidence = self._validate_financial_data(structured_data)
                
                logger.info(f"OpenAI extraction completed - confidence: {confidence:.3f}")
                return extracted_data, confidence
            else:
                logger.error("OpenAI response empty or invalid")
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
        Extract invoice fields using Anthropic Claude for cross-validation.
        
        Uses the official Anthropic SDK with async support.
        """
        if not self.anthropic_client:
            logger.error("Anthropic client not available")
            return {}, 0.0
        
        try:
            prompt = f"""Extract invoice data from this text with 99-100% accuracy. 
            
Pay special attention to distinguishing between subtotal and total amounts.

Text: {text_content}

Return a JSON object with these fields:
- invoice_number: string
- vendor_name: string  
- invoice_date: string (YYYY-MM-DD)
- due_date: string (YYYY-MM-DD)
- subtotal: number (amount before tax)
- tax_amount: number
- total_amount: number (final amount including tax)
- currency: string
- line_items: array of objects with description, quantity, unit_price, total
- confidence_score: number (0.0-1.0)
- validation_flags: array of strings

Respond only with valid JSON."""

            # Use the official Anthropic client
            message = self.anthropic_client.messages.create(
                model=model,
                max_tokens=1500,
                messages=[
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ]
            )
            
            if message.content and len(message.content) > 0:
                content = message.content[0].text
                
                try:
                    extracted_data = json.loads(content)
                    confidence = extracted_data.get("confidence_score", 0.8)
                    
                    # Create structured data object for validation
                    structured_data = ExtractedInvoiceData(**extracted_data)
                    
                    # Validate financial calculations
                    validated_confidence = self._validate_financial_data(structured_data)
                    
                    logger.info(f"Anthropic extraction completed - confidence: {validated_confidence:.3f}")
                    return extracted_data, validated_confidence
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse Anthropic JSON response: {e}")
                    return {}, 0.0
            else:
                logger.error("Empty response from Anthropic")
                return {}, 0.0
                
        except Exception as e:
            logger.error(f"Anthropic extraction failed: {e}")
            return {}, 0.0
    
    def _validate_financial_data(self, data: ExtractedInvoiceData) -> float:
        """
        Validate financial calculations and return confidence score.
        """
        confidence = 0.8  # Base confidence
        
        try:
            # Check if we have the critical amounts
            if data.subtotal is not None and data.total_amount is not None:
                confidence += 0.1
                
                # Validate tax calculation if tax amount is provided
                if data.tax_amount is not None:
                    expected_total = data.subtotal + data.tax_amount
                    if abs(expected_total - data.total_amount) < 0.01:  # Within 1 cent
                        confidence += 0.1
                        logger.info("✓ Tax calculation validates correctly")
                    else:
                        data.validation_flags.append(f"Tax calculation mismatch: {data.subtotal} + {data.tax_amount} ≠ {data.total_amount}")
                        confidence -= 0.2
                
                # Check for reasonable amounts
                if data.total_amount > data.subtotal:
                    confidence += 0.05
                else:
                    data.validation_flags.append("Total should be greater than subtotal")
                    confidence -= 0.1
            
            # Check for required fields
            if data.invoice_number:
                confidence += 0.05
            if data.vendor_name:
                confidence += 0.05
                
        except Exception as e:
            logger.error(f"Financial validation error: {e}")
            confidence -= 0.3
        
        return min(1.0, max(0.0, confidence))
    
    async def extract_invoice_fields(
        self, 
        text_content: str,
        use_cross_validation: bool = True
    ) -> Tuple[ExtractedInvoiceData, float, bool]:
        """
        Extract invoice fields with confidence scoring and validation.
        
        Args:
            text_content: Raw text from OCR
            use_cross_validation: Whether to cross-validate with multiple models
            
        Returns:
            Tuple of (extracted_data, confidence_score, needs_human_review)
        """
        try:
            if use_cross_validation and self.openai_client and self.anthropic_client:
                # Run both models for cross-validation
                logger.info("Running cross-validation with OpenAI + Anthropic")
                
                # Extract using OpenAI (synchronous)
                openai_data, openai_confidence = self.extract_fields_openai(text_content)
                
                # Extract using Anthropic (asynchronous)
                anthropic_data, anthropic_confidence = await self.extract_fields_anthropic(text_content)
                
                # Compare results and select best
                if openai_confidence > anthropic_confidence:
                    best_data = openai_data
                    best_confidence = openai_confidence
                    logger.info(f"Selected OpenAI result (confidence: {openai_confidence:.3f})")
                else:
                    best_data = anthropic_data  
                    best_confidence = anthropic_confidence
                    logger.info(f"Selected Anthropic result (confidence: {anthropic_confidence:.3f})")
                
                # Cross-validation bonus
                if abs(openai_confidence - anthropic_confidence) < 0.2:
                    best_confidence = min(1.0, best_confidence + 0.1)
                    logger.info("Cross-validation bonus applied")
                
            elif self.openai_client:
                # Use OpenAI only
                logger.info("Using OpenAI only")
                best_data, best_confidence = self.extract_fields_openai(text_content)
                
            elif self.anthropic_client:
                # Use Anthropic only
                logger.info("Using Anthropic only")
                best_data, best_confidence = await self.extract_fields_anthropic(text_content)
                
            else:
                logger.error("No AI models available")
                return ExtractedInvoiceData(), 0.0, True
            
            # Convert to structured data
            try:
                if isinstance(best_data, dict):
                    extracted_data = ExtractedInvoiceData(**best_data)
                else:
                    extracted_data = best_data
            except ValidationError as e:
                logger.error(f"Data validation failed: {e}")
                extracted_data = ExtractedInvoiceData()
                best_confidence = 0.0
            
            # Determine if human review is needed
            needs_human_review = (
                best_confidence < 0.85 or 
                len(extracted_data.validation_flags) > 0 or
                not extracted_data.total_amount
            )
            
            return extracted_data, best_confidence, needs_human_review
            
        except Exception as e:
            logger.error(f"Invoice field extraction failed: {e}")
            return ExtractedInvoiceData(), 0.0, True 
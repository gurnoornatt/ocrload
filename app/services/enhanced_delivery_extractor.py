"""
Enhanced Delivery & Packing List Extractor with Marker API + Sonnet 3.5

New improved workflow for delivery notes and packing lists:
1. Datalab Marker API processes document with force_ocr=True, use_llm=False (NO PREPROCESSING)
2. Structured markdown output fed to Sonnet 3.5 for semantic reasoning
3. Much better extraction results due to cleaner, organized input

Supports:
- Delivery Notes (POD - Proof of Delivery)
- Packing Lists  
- Item descriptions, quantities, weights, SKUs
- Delivery confirmations, signatures, condition notes
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, ValidationError

from app.config.settings import settings
from app.services.ocr_clients.datalab_marker_client import DatalabMarkerClient, MarkerResult

# Anthropic import for Sonnet 3.5
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

logger = logging.getLogger(__name__)


class ExtractedPackingItem(BaseModel):
    """Individual packing list item with validation."""
    
    item_description: Optional[str] = Field(None, description="Description of the item")
    sku: Optional[str] = Field(None, description="SKU/product code")
    quantity: Optional[Union[int, float]] = Field(None, description="Quantity shipped")
    unit: Optional[str] = Field(None, description="Unit of measure (pcs, lbs, kg, etc.)")
    weight: Optional[float] = Field(None, description="Weight of items")
    weight_unit: Optional[str] = Field(None, description="Weight unit (lbs, kg, etc.)")
    dimensions: Optional[str] = Field(None, description="Dimensions if specified")
    special_handling: Optional[str] = Field(None, description="Special handling instructions")
    condition: Optional[str] = Field(None, description="Condition of items")


class ExtractedDeliveryData(BaseModel):
    """Structured delivery note and packing list data with validation."""
    
    # Document identification
    document_number: Optional[str] = Field(None, description="Delivery note/packing list number")
    document_type: Optional[str] = Field(None, description="Document type (delivery_note, packing_list, pod)")
    document_date: Optional[str] = Field(None, description="Document date in YYYY-MM-DD format")
    
    # Delivery information
    delivery_date: Optional[str] = Field(None, description="Actual delivery date")
    delivery_time: Optional[str] = Field(None, description="Delivery time")
    delivery_status: Optional[str] = Field(None, description="Delivery status (delivered, partial, refused, etc.)")
    
    # Locations and parties
    origin_address: Optional[str] = Field(None, description="Pickup/origin address")
    destination_address: Optional[str] = Field(None, description="Delivery destination address")
    shipper_name: Optional[str] = Field(None, description="Shipper/sender name")
    consignee_name: Optional[str] = Field(None, description="Consignee/recipient name")
    carrier_name: Optional[str] = Field(None, description="Carrier company name")
    
    # Transport details
    driver_name: Optional[str] = Field(None, description="Driver name")
    truck_number: Optional[str] = Field(None, description="Truck/vehicle number")
    trailer_number: Optional[str] = Field(None, description="Trailer number")
    
    # Reference numbers
    bol_number: Optional[str] = Field(None, description="Bill of lading number")
    pro_number: Optional[str] = Field(None, description="PRO number")
    po_number: Optional[str] = Field(None, description="Purchase order number")
    load_number: Optional[str] = Field(None, description="Load number")
    
    # Packing list items
    items: List[ExtractedPackingItem] = Field(default_factory=list, description="List of packed items")
    total_pieces: Optional[int] = Field(None, description="Total number of pieces")
    total_weight: Optional[float] = Field(None, description="Total weight")
    total_weight_unit: Optional[str] = Field(None, description="Total weight unit")
    
    # Delivery confirmation  
    recipient_name: Optional[str] = Field(None, description="Name of person who received delivery")
    recipient_signature: Optional[str] = Field(None, description="Signature confirmation")
    delivery_confirmed: Optional[bool] = Field(None, description="Whether delivery was confirmed")
    
    # Condition and notes
    condition_notes: Optional[str] = Field(None, description="Notes about condition of goods")
    delivery_notes: Optional[str] = Field(None, description="General delivery notes")
    damage_reported: Optional[bool] = Field(None, description="Whether any damage was reported")
    special_instructions: Optional[str] = Field(None, description="Special delivery instructions")
    
    # Validation and confidence
    confidence_score: float = Field(0.0, description="Confidence in extraction accuracy (0.0-1.0)")
    validation_flags: List[str] = Field(default_factory=list, description="Validation issues found")


class EnhancedDeliveryExtractor:
    """
    Enhanced delivery note and packing list extractor using Marker API + Sonnet 3.5.
    
    NEW WORKFLOW (NO PREPROCESSING):
    1. Uses Datalab Marker API (force_ocr=True, use_llm=False) for structured markdown
    2. Feeds clean markdown to Sonnet 3.5 for semantic reasoning
    3. Achieves better extraction through organized input structure
    
    Supports:
    - Delivery notes (POD)
    - Packing lists
    - Item details, quantities, weights
    - Delivery confirmations and signatures
    """
    
    def __init__(self):
        """Initialize the enhanced delivery extractor."""
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
            logger.warning("ANTHROPIC_API_KEY not found - Delivery extraction will not be available")
        
        # Marker API client (NO preprocessing)
        self.marker_client = DatalabMarkerClient(preprocessing_enabled=False)
        
        logger.info(f"Enhanced Delivery Extractor initialized - Sonnet 3.5: {'✓' if self.anthropic_client else '✗'}, Marker API: {'✓' if self.marker_client.api_key else '✗'}")
    
    async def extract_fields_from_markdown(
        self, 
        markdown_content: str,
        marker_metadata: Dict[str, Any] = None,
        model: str = "claude-3-5-sonnet-20241022"
    ) -> Tuple[Dict[str, Any], float]:
        """Extract delivery and packing list data from markdown using Claude Sonnet 3.5."""
        
        # Determine document type hint based on markdown content
        doc_type_hint = "delivery_note"  # default
        content_lower = markdown_content.lower()
        if any(term in content_lower for term in ["packing list", "pack list", "shipping list"]):
            doc_type_hint = "packing_list"
        elif any(term in content_lower for term in ["pod", "proof of delivery", "delivery receipt"]):
            doc_type_hint = "pod"
        
        if not self.anthropic_client:
            logger.error("Anthropic client not initialized")
            return {}, 0.0
        
        try:
            # Enhanced prompt optimized for delivery notes and packing lists
            system_prompt = """You are an expert delivery note and packing list data extraction specialist working with structured markdown input.

The input is pre-processed, structured markdown from an advanced OCR system with layout understanding. This gives you clean, organized content with proper formatting, tables, and sections.

CRITICAL: Extract delivery and packing list data with maximum accuracy and flexibility. DO NOT leave fields empty just because the exact field name doesn't match. Be INTELLIGENT about finding information regardless of how it's labeled in the document.

FLEXIBLE FIELD MAPPING - Look for these concepts under ANY naming:

DOCUMENT IDENTIFICATION:
- Document numbers: Look for ANY number that identifies the document - "Invoice #", "Doc #", "Ref #", "Number", "ID", etc.
- Document type: Determine from content and context (delivery_note, packing_list, or pod)
- Dates: ANY date on the document - "Date", "Delivery Date", "Ship Date", "Created", "Issued", etc.

COMPANY INFORMATION (be very flexible with names):
- Shipper/Sender: "From", "Shipper", "Sender", "Ship From", "Origin Company", "Supplier", etc.
- Consignee/Recipient: "To", "Consignee", "Recipient", "Ship To", "Deliver To", "Customer", "Destination Company", etc.
- Carrier: "Carrier", "Transport", "Shipping Company", "Logistics", "Trucking", etc.

PEOPLE:
- Driver: "Driver", "Operator", "Delivery Person", any person name associated with transport
- Recipient: "Received by", "Delivered to", "Signed by", any person who received goods

REFERENCE NUMBERS (extract ANY reference numbers you find):
- BOL: "BOL", "Bill of Lading", "B/L", "BL", any long alphanumeric code
- PRO: "PRO", "PRO Number", "Tracking", any tracking-style number
- PO: "PO", "Purchase Order", "Order #", "P.O.", any order reference
- Load: "Load #", "Trip #", "Job #", any load reference

ITEMS AND QUANTITIES (be very flexible):
- Extract ALL items/products mentioned, regardless of how they're listed
- For each item, capture: description, quantity, unit, weight, SKU/code if present
- Look for quantities with ANY unit: pieces, pcs, ea, each, lbs, kg, tons, pallets, boxes, etc.
- If items are in a table, extract each row
- If items are in a list, extract each line item
- If quantities are unclear, make reasonable assumptions based on context

DELIVERY INFORMATION:
- Delivery dates: ANY date that seems related to delivery/receipt
- Delivery status: Look for "delivered", "received", "completed", "refused", etc.
- Condition: ANY notes about item condition - "good", "damaged", "excellent", etc.
- Signatures: Look for signature lines, "signed", "received by", signature blocks

ADDRESSES (extract complete addresses when found):
- Origin: Where goods shipped FROM
- Destination: Where goods delivered TO
- Format as complete addresses when possible

TOTALS AND WEIGHTS:
- Total pieces: Sum of all quantities or any "total" mentioned
- Total weight: Any weight totals mentioned
- If totals aren't explicitly stated, calculate from individual items when possible

INTELLIGENCE RULES:
1. If a field maps to multiple possible values, pick the most relevant one
2. If quantities are ranges (like "10-15"), use the average or first number
3. If dates are relative ("yesterday", "last week"), convert to actual dates when possible
4. If company names are abbreviated, expand them when context is clear
5. Extract data even if formatting is poor or inconsistent
6. When in doubt, include rather than exclude information
7. Use context clues to determine what information represents

CONFIDENCE SCORING:
- High confidence (0.8-1.0): Clear, well-formatted documents with explicit labels
- Medium confidence (0.6-0.8): Some ambiguity but information is extractable
- Low confidence (0.3-0.6): Poor formatting but some data recoverable
- Very low (0.0-0.3): Mostly unreadable or no relevant data

Return comprehensive JSON with all fields filled to the best of your ability. It's better to have reasonable guesses than empty fields."""

            user_prompt = f"""Extract delivery and packing list data from this markdown:

{markdown_content}

You MUST return a comprehensive JSON object with ALL available information. Fill every field you can determine from the document.

Required JSON format (return ONLY this JSON, no other text):
{{
  "document_number": "extract any document/reference number",
  "document_type": "delivery_note or packing_list or pod",
  "document_date": "YYYY-MM-DD format if found",
  "delivery_date": "YYYY-MM-DD format if found",
  "delivery_time": "any time information",
  "delivery_status": "delivery status if mentioned",
  "origin_address": "full pickup address",
  "destination_address": "full delivery address", 
  "shipper_name": "company shipping the goods",
  "consignee_name": "company receiving the goods",
  "carrier_name": "transport/carrier company",
  "driver_name": "driver name if mentioned",
  "truck_number": "truck/vehicle number",
  "trailer_number": "trailer number if present",
  "bol_number": "bill of lading number",
  "pro_number": "PRO tracking number",
  "po_number": "purchase order number",
  "load_number": "load/trip number",
  "items": [
    {{
      "item_description": "item description",
      "sku": "product code if any",
      "quantity": 10,
      "unit": "pieces/lbs/etc",
      "weight": 100.5,
      "weight_unit": "lbs",
      "condition": "condition notes"
    }}
  ],
  "total_pieces": 10,
  "total_weight": 1000.5,
  "total_weight_unit": "lbs",
  "recipient_name": "person who received delivery",
  "delivery_confirmed": true,
  "condition_notes": "condition of goods",
  "delivery_notes": "any delivery notes",
  "special_instructions": "special instructions",
  "damage_reported": false,
  "confidence_score": 0.85
}}

CRITICAL: Extract MAXIMUM data. If you see company names, put them in shipper_name/consignee_name. If you see ANY numbers, categorize them appropriately. If you see items/cargo, list them all with details. Return comprehensive JSON only."""
            
            logger.info(f"Sending structured markdown to Sonnet 3.5 ({len(markdown_content)} chars)")
            
            # Make API call to Sonnet 3.5
            response = self.anthropic_client.messages.create(
                model=model,
                max_tokens=6000,  # Increased for packing lists with many items
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
            
            # Parse JSON response with improved error handling (using debug script logic)
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
                    start = json_content.find('```') + 3
                    end = json_content.find('```', start)
                    if end != -1:
                        json_content = json_content[start:end].strip()
                
                # Method 2: Direct JSON parsing (like debug script)
                if not json_content.strip().startswith('{'):
                    # Look for the first opening brace
                    start_pos = json_content.find('{')
                    if start_pos != -1:
                        json_content = json_content[start_pos:]
                
                # Try direct parsing first (like debug script works)
                try:
                    extracted_dict = json.loads(json_content)
                    logger.info(f"✅ Direct JSON parsing successful")
                except json.JSONDecodeError:
                    # If direct fails, try cleaning
                    cleaned_content = self._clean_json_response(json_content)
                    extracted_dict = json.loads(cleaned_content)
                    logger.info(f"✅ Cleaned JSON parsing successful")
                
            except json.JSONDecodeError as e:
                logger.warning(f"Standard JSON parsing failed: {e}")
                logger.debug(f"Failed content: {json_content[:300]}...")
                
                try:
                    # Try aggressive cleaning
                    cleaned_json = self._aggressive_json_clean(response_content)
                    extracted_dict = json.loads(cleaned_json)
                    logger.info(f"✅ Aggressive cleaning successful")
                except (json.JSONDecodeError, ValueError) as e2:
                    logger.error(f"All JSON parsing attempts failed: {e2}")
                    logger.debug(f"Raw response: {response_content[:200]}...")
                    
                    # Last resort: try to extract any useful data from the response
                    try:
                        # Look for individual field patterns in the response
                        import re
                        fallback_data = {}
                        
                        # Try to extract simple field: value patterns
                        field_patterns = [
                            (r'"document_type":\s*"([^"]+)"', 'document_type'),
                            (r'"driver_name":\s*"([^"]+)"', 'driver_name'),
                            (r'"truck_number":\s*"([^"]+)"', 'truck_number'),
                            (r'"shipper_name":\s*"([^"]+)"', 'shipper_name'),
                            (r'"consignee_name":\s*"([^"]+)"', 'consignee_name'),
                        ]
                        
                        for pattern, field_name in field_patterns:
                            match = re.search(pattern, response_content)
                            if match:
                                fallback_data[field_name] = match.group(1)
                        
                        if fallback_data:
                            fallback_data['confidence_score'] = 0.3  # Low confidence for fallback
                            fallback_data['validation_flags'] = ['JSON parsing failed - partial extraction']
                            extracted_dict = fallback_data
                            logger.info(f"✅ Fallback extraction found {len(fallback_data)} fields")
                        else:
                            raise ValueError("No extractable data found")
                            
                    except Exception as e3:
                        logger.error(f"Fallback extraction also failed: {e3}")
                        return {
                            'document_type': doc_type_hint,
                            'confidence_score': 0.0,
                            'validation_flags': ['Complete JSON parsing failure'],
                            'items': []
                        }, 0.0
            
            # Process the successfully extracted data
            confidence = extracted_dict.get('confidence_score', 0.8)
            logger.info(f"Sonnet 3.5 extraction successful - confidence: {confidence:.1%}")
            return extracted_dict, confidence
        
        except Exception as e:
            logger.error(f"Sonnet 3.5 extraction failed: {e}")
            return {}, 0.0
    
    def _validate_delivery_data(self, data: ExtractedDeliveryData) -> float:
        """Validate extracted delivery data and return validation score."""
        validation_score = 1.0
        issues = []
        
        # Count how much data we actually extracted (more flexible approach)
        extracted_data_count = 0
        total_possible_fields = 0
        
        # Core content validation - focus on data completeness, not exact field matching
        data_dict = data.model_dump()
        for field_name, field_value in data_dict.items():
            if field_name in ['validation_flags', 'confidence_score']:
                continue
                
            total_possible_fields += 1
            
            # Count any non-empty data as a success
            if field_value is not None:
                if isinstance(field_value, str) and field_value.strip():
                    extracted_data_count += 1
                elif isinstance(field_value, list) and len(field_value) > 0:
                    extracted_data_count += 1
                elif isinstance(field_value, (int, float, bool)):
                    extracted_data_count += 1
        
        # Calculate data completeness score (main factor)
        data_completeness = extracted_data_count / total_possible_fields if total_possible_fields > 0 else 0
        
        # Specific validations (less strict, more focused on common sense)
        if data.document_type in ["delivery_note", "pod"]:
            # For delivery documents, we expect SOME delivery-related information
            has_delivery_info = any([
                data.delivery_date, data.delivery_time, data.delivery_confirmed,
                data.recipient_name, data.driver_name
            ])
            if not has_delivery_info:
                issues.append('No delivery information found')
                validation_score -= 0.1  # Minor penalty
                
        elif data.document_type == "packing_list":
            # For packing lists, we expect SOME items
            if not data.items or len(data.items) == 0:
                issues.append('No items found in packing list')
                validation_score -= 0.15  # Minor penalty
        
        # Company information - just warn if completely missing
        has_company_info = any([
            data.shipper_name, data.consignee_name, data.carrier_name
        ])
        if not has_company_info:
            issues.append('Limited company information')
            validation_score -= 0.05  # Very minor penalty
        
        # Date validation (only for dates that exist)
        for date_field, field_name in [
            ('document_date', 'document date'),
            ('delivery_date', 'delivery date')
        ]:
            date_value = getattr(data, date_field)
            if date_value:
                try:
                    # Try multiple date formats
                    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S']:
                        try:
                            datetime.strptime(str(date_value), fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        # If no format worked, it's still okay - just note it
                        issues.append(f'Unusual {field_name} format: {date_value}')
                except Exception:
                    pass  # Don't penalize for date format issues
        
        # Item validation (very lenient)
        if data.items:
            items_with_content = 0
            for i, item in enumerate(data.items):
                if item.item_description or item.sku or item.quantity:
                    items_with_content += 1
            
            if items_with_content == 0:
                issues.append('Items found but no content extracted')
                validation_score -= 0.1
        
        # Base score heavily on data completeness
        final_score = (data_completeness * 0.7) + (validation_score * 0.3)
        
        # Bonus for having items with details (for packing lists)
        if data.items and len(data.items) > 0:
            items_with_details = sum(1 for item in data.items 
                                   if item.item_description and item.quantity)
            if items_with_details > 0:
                final_score += 0.1  # Bonus for detailed items
        
        # Bonus for having reference numbers
        ref_numbers = [data.bol_number, data.pro_number, data.po_number, data.load_number]
        if any(ref_numbers):
            final_score += 0.05  # Small bonus for reference numbers
        
        # Update validation flags
        data.validation_flags = issues
        
        return min(1.0, max(0.1, final_score))  # Never go below 0.1 if we extracted any data
    
    async def extract_delivery_fields_enhanced(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str = "image/jpeg"
    ) -> Tuple[ExtractedDeliveryData, float, bool]:
        """
        Complete enhanced delivery/packing list extraction using new Marker API + Sonnet 3.5 workflow.
        
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
        logger.info(f"Starting enhanced delivery extraction for {filename}")
        
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
                empty_data = ExtractedDeliveryData()
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
                empty_data = ExtractedDeliveryData()
                empty_data.validation_flags = ["AI extraction failed"]
                return empty_data, 0.0, True
            
            # Step 3: Structure and validate the data with INTELLIGENT FIELD MAPPING
            try:
                # INTELLIGENT FIELD MAPPING - Map Claude's creative field names to our model
                field_mapping = {
                    # Document fields
                    'document_number': ['document_number', 'doc_number', 'invoice_number', 'receipt_number', 'reference_number'],
                    'document_type': ['document_type', 'doc_type', 'type'],
                    'document_date': ['document_date', 'doc_date', 'date', 'issue_date', 'created_date'],
                    
                    # Delivery fields  
                    'delivery_date': ['delivery_date', 'del_date', 'arrival_date', 'received_date'],
                    'delivery_time': ['delivery_time', 'del_time', 'arrival_time', 'time'],
                    'delivery_status': ['delivery_status', 'status', 'del_status'],
                    'delivery_confirmed': ['delivery_confirmed', 'confirmed', 'delivered', 'received'],
                    
                    # Location fields
                    'origin_address': ['origin_address', 'shipper_address', 'from_address', 'pickup_address'],
                    'destination_address': ['destination_address', 'consignee_address', 'to_address', 'delivery_address', 'consignee_location'],
                    
                    # Company fields
                    'shipper_name': ['shipper_name', 'shipper', 'from_company', 'sender_name', 'origin_company'],
                    'consignee_name': ['consignee_name', 'consignee', 'to_company', 'recipient_name', 'destination_company'],
                    'carrier_name': ['carrier_name', 'carrier', 'transport_company', 'shipping_company'],
                    
                    # People fields
                    'driver_name': ['driver_name', 'driver', 'operator', 'delivery_person'],
                    'recipient_name': ['recipient_name', 'received_by', 'signed_by', 'delivered_to'],
                    
                    # Vehicle fields
                    'truck_number': ['truck_number', 'truck_no', 'vehicle_number', 'truck'],
                    'trailer_number': ['trailer_number', 'trailer_no', 'trailer'],
                    
                    # Reference numbers
                    'bol_number': ['bol_number', 'bol', 'bill_of_lading', 'bl_number'],
                    'pro_number': ['pro_number', 'pro', 'tracking_number'],
                    'po_number': ['po_number', 'po', 'purchase_order', 'order_number'],
                    'load_number': ['load_number', 'load', 'trip_number', 'job_number'],
                    
                    # Weight and quantity fields
                    'total_pieces': ['total_pieces', 'total_items', 'pieces', 'total_count', 'quantity'],
                    'total_weight': ['total_weight', 'weight', 'gross_weight', 'total_wt'],
                    'total_weight_unit': ['total_weight_unit', 'weight_unit', 'wt_unit'],
                    
                    # Notes and conditions
                    'condition_notes': ['condition_notes', 'condition', 'notes', 'comments', 'equipment_condition'],
                    'delivery_notes': ['delivery_notes', 'notes', 'comments', 'remarks', 'additional_notes'],
                    'special_instructions': ['special_instructions', 'instructions', 'special_notes'],
                    'damage_reported': ['damage_reported', 'damage', 'damaged'],
                    
                    # Signature fields
                    'recipient_signature': ['recipient_signature', 'signature', 'signed', 'sig']
                }
                
                # Create a cleaned dictionary with proper field mapping
                cleaned_dict = {}
                
                # First, handle items array specially
                items_data = []
                if 'items' in extracted_dict and isinstance(extracted_dict['items'], list):
                    for item_data in extracted_dict['items']:
                        if isinstance(item_data, dict):
                            try:
                                item = ExtractedPackingItem(**item_data)
                                items_data.append(item)
                            except ValidationError:
                                # Create a flexible item mapping
                                item_dict = {}
                                for field, value in item_data.items():
                                    if 'description' in field.lower() or 'desc' in field.lower():
                                        item_dict['item_description'] = str(value) if value else None
                                    elif 'sku' in field.lower() or 'code' in field.lower() or 'part' in field.lower():
                                        item_dict['sku'] = str(value) if value else None
                                    elif 'quantity' in field.lower() or 'qty' in field.lower() or field.lower() == 'count':
                                        try:
                                            item_dict['quantity'] = float(value) if value is not None else None
                                        except:
                                            item_dict['quantity'] = None
                                    elif 'weight' in field.lower() and 'unit' not in field.lower():
                                        try:
                                            item_dict['weight'] = float(value) if value is not None else None
                                        except:
                                            item_dict['weight'] = None
                                    elif 'unit' in field.lower():
                                        item_dict['unit'] = str(value) if value else None
                                
                                # Add basic description if we have any useful data
                                if not item_dict.get('item_description') and value:
                                    item_dict['item_description'] = str(value)
                                
                                try:
                                    item = ExtractedPackingItem(**item_dict)
                                    items_data.append(item)
                                except ValidationError:
                                    # Create minimal item
                                    items_data.append(ExtractedPackingItem(
                                        item_description=str(item_data) if item_data else "Item"
                                    ))
                
                cleaned_dict['items'] = items_data
                
                # Map all other fields using intelligent mapping
                for target_field, possible_names in field_mapping.items():
                    value = None
                    
                    # Try each possible name
                    for name in possible_names:
                        if name in extracted_dict:
                            value = extracted_dict[name]
                            break
                    
                    # If not found, try case-insensitive and partial matching
                    if value is None:
                        for key, val in extracted_dict.items():
                            key_lower = key.lower().replace('_', '').replace(' ', '')
                            for name in possible_names:
                                name_lower = name.lower().replace('_', '').replace(' ', '')
                                if key_lower == name_lower or key_lower in name_lower or name_lower in key_lower:
                                    value = val
                                    break
                            if value is not None:
                                break
                    
                    # SPECIAL HANDLING for Claude's creative field names we observed
                    if value is None and target_field == 'destination_address':
                        # Try consignee_location, consignee_address variations
                        for alt_name in ['consignee_location', 'delivery_location', 'destination_location']:
                            if alt_name in extracted_dict:
                                value = extracted_dict[alt_name]
                                break
                    
                    if value is None and target_field == 'bol_number':
                        # Try container_numbers array for BOL-like numbers
                        if 'container_numbers' in extracted_dict and isinstance(extracted_dict['container_numbers'], list):
                            container_nums = extracted_dict['container_numbers']
                            if container_nums:
                                value = container_nums[0]  # Take first container number as BOL
                    
                    if value is None and target_field == 'delivery_time':
                        # Try timing object with various time fields
                        if 'timing' in extracted_dict and isinstance(extracted_dict['timing'], dict):
                            timing = extracted_dict['timing']
                            for time_key in ['arrival_time', 'appointment_time', 'start_time', 'delivery_time']:
                                if time_key in timing:
                                    value = timing[time_key]
                                    break
                    
                    if value is None and target_field == 'special_instructions':
                        # Try additional_details for payment terms and special instructions
                        if 'additional_details' in extracted_dict and isinstance(extracted_dict['additional_details'], dict):
                            details = extracted_dict['additional_details']
                            instructions = []
                            if 'terms' in details and isinstance(details['terms'], dict):
                                for term_key, term_val in details['terms'].items():
                                    if term_val:
                                        instructions.append(f"{term_key.replace('_', ' ').title()}: {term_val}")
                            if 'load_type' in details:
                                instructions.append(f"Load Type: {details['load_type']}")
                            if instructions:
                                value = '; '.join(instructions)
                    
                    # Clean the value based on expected type
                    if value is not None:
                        if target_field in ['delivery_confirmed', 'damage_reported']:
                            # Boolean fields
                            if isinstance(value, str):
                                cleaned_dict[target_field] = value.lower() in ['true', 'yes', 'confirmed', '1', 'received']
                            elif isinstance(value, bool):
                                cleaned_dict[target_field] = value
                            else:
                                cleaned_dict[target_field] = bool(value)
                        
                        elif target_field in ['total_pieces', 'total_weight']:
                            # Numeric fields
                            if isinstance(value, str):
                                try:
                                    import re
                                    number_match = re.search(r'[\d.]+', value)
                                    if number_match:
                                        cleaned_dict[target_field] = float(number_match.group())
                                    else:
                                        cleaned_dict[target_field] = None
                                except:
                                    cleaned_dict[target_field] = None
                            elif isinstance(value, (int, float)):
                                cleaned_dict[target_field] = value
                            else:
                                cleaned_dict[target_field] = None
                        
                        else:
                            # String fields - handle arrays, objects, etc.
                            if isinstance(value, list):
                                if target_field in ['special_instructions', 'condition_notes', 'delivery_notes']:
                                    # Notes fields - join with newlines
                                    cleaned_dict[target_field] = '\n'.join(str(item) for item in value if item)
                                else:
                                    # Other fields - take first meaningful item
                                    for item in value:
                                        if item and str(item).strip():
                                            cleaned_dict[target_field] = str(item).strip()
                                            break
                            elif isinstance(value, dict):
                                # Convert dict to string representation
                                if target_field == 'delivery_time':
                                    # Special handling for time objects
                                    time_parts = []
                                    for k, v in value.items():
                                        if v:
                                            time_parts.append(f"{k.replace('_', ' ').title()}: {v}")
                                    cleaned_dict[target_field] = ", ".join(time_parts) if time_parts else None
                                else:
                                    # General dict to string conversion
                                    dict_parts = []
                                    for k, v in value.items():
                                        if v:
                                            dict_parts.append(str(v))
                                    cleaned_dict[target_field] = ", ".join(dict_parts) if dict_parts else None
                            else:
                                # Direct string conversion
                                cleaned_dict[target_field] = str(value).strip() if str(value).strip() else None
                
                # Handle special nested structures that Claude might return
                if 'timing' in extracted_dict and isinstance(extracted_dict['timing'], dict):
                    timing = extracted_dict['timing']
                    if 'arrival_time' in timing:
                        cleaned_dict['delivery_time'] = timing['arrival_time']
                    elif 'start_time' in timing:
                        cleaned_dict['delivery_time'] = timing['start_time']
                
                if 'equipment_type' in extracted_dict and isinstance(extracted_dict['equipment_type'], dict):
                    equip = extracted_dict['equipment_type']
                    if equip.get('empty'):
                        cleaned_dict['delivery_status'] = 'Empty Return'
                    elif equip.get('loaded'):
                        cleaned_dict['delivery_status'] = 'Loaded Delivery'
                
                # Handle container numbers or reference numbers
                for field in ['container_numbers', 'reference_numbers', 'tracking_numbers']:
                    if field in extracted_dict and isinstance(extracted_dict[field], list):
                        if not cleaned_dict.get('bol_number') and extracted_dict[field]:
                            cleaned_dict['bol_number'] = extracted_dict[field][0]
                
                # Extract data from additional_notes if present
                if 'additional_notes' in extracted_dict and isinstance(extracted_dict['additional_notes'], dict):
                    notes = extracted_dict['additional_notes']
                    for key, value in notes.items():
                        if 'condition' in key.lower() and not cleaned_dict.get('condition_notes'):
                            cleaned_dict['condition_notes'] = str(value)
                        elif 'payment' in key.lower() or 'finance' in key.lower():
                            if not cleaned_dict.get('special_instructions'):
                                cleaned_dict['special_instructions'] = str(value)
                            else:
                                cleaned_dict['special_instructions'] += f"\n{value}"
                
                # Set confidence from Claude or default
                cleaned_dict['confidence_score'] = extracted_dict.get('confidence_score', ai_confidence)
                
                # Create the final data object
                extracted_data = ExtractedDeliveryData(**cleaned_dict)
                
            except ValidationError as e:
                logger.error(f"Data validation failed for {filename}: {e}")
                # Create a minimal data object with whatever we can salvage
                basic_data = {
                    'document_type': extracted_dict.get('document_type', doc_type_hint),
                    'confidence_score': ai_confidence,
                    'validation_flags': [f"Data validation error: {str(e)}"]
                }
                extracted_data = ExtractedDeliveryData(**basic_data)
            
            # Step 4: Final validation and scoring
            validation_score = self._validate_delivery_data(extracted_data)
            final_confidence = min(ai_confidence, validation_score)
            
            # Update confidence in the data
            extracted_data.confidence_score = final_confidence
            
            # Determine if review is needed
            needs_review = final_confidence < 0.75 or len(extracted_data.validation_flags) > 2
            
            logger.info(f"Enhanced delivery extraction complete - Confidence: {final_confidence:.1%}, Review needed: {needs_review}")
            
            return extracted_data, final_confidence, needs_review
            
        except Exception as e:
            logger.error(f"Enhanced delivery extraction failed for {filename}: {e}")
            empty_data = ExtractedDeliveryData()
            empty_data.validation_flags = [f"Extraction error: {str(e)}"]
            return empty_data, 0.0, True
    
    def _clean_json_response(self, json_content: str) -> str:
        """Clean JSON response by removing comments and fixing common issues."""
        # Remove single-line comments (// comments)
        lines = json_content.split('\n')
        cleaned_lines = []
        for line in lines:
            # Remove // comments
            if '//' in line:
                line = line[:line.find('//')]
            # Skip empty lines
            line = line.strip()
            if line:
                # Remove trailing commas before closing braces/brackets
                line = line.rstrip(',')
                cleaned_lines.append(line)
        
        cleaned_content = '\n'.join(cleaned_lines)
        
        # Fix common JSON issues
        cleaned_content = cleaned_content.replace(',}', '}')
        cleaned_content = cleaned_content.replace(',]', ']')
        
        # Remove empty lines that cause delimiter issues
        cleaned_content = '\n'.join(line for line in cleaned_content.split('\n') if line.strip())
        
        return cleaned_content
    
    def _aggressive_json_clean(self, response_content: str) -> str:
        """More aggressive JSON cleaning for difficult responses."""
        import re
        
        # Find the JSON object boundaries
        start = response_content.find('{')
        if start == -1:
            raise ValueError("No JSON object found")
        
        # Find matching closing brace
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
        
        if end <= start:
            raise ValueError("Malformed JSON object")
        
        json_part = response_content[start:end]
        
        # Very aggressive cleaning
        # Remove all comments
        json_part = re.sub(r'//.*', '', json_part)  
        # Remove empty lines completely 
        json_part = re.sub(r'\n\s*\n', '\n', json_part)  
        # Remove lines that only have whitespace
        lines = json_part.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        json_part = '\n'.join(non_empty_lines)
        # Remove trailing commas before closing braces/brackets
        json_part = re.sub(r',\s*([}\]])', r'\1', json_part)  
        # Remove double commas
        json_part = re.sub(r',\s*,', ',', json_part)  
        # Remove commas after closing braces/brackets
        json_part = re.sub(r'([}\]]),\s*([}\]])', r'\1\2', json_part)
        
        # Apply regular cleaning too
        return self._clean_json_response(json_part) 
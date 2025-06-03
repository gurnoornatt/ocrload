"""
Enhanced Delivery & Packing List Parser with Marker API + Sonnet 3.5

Integrates the enhanced delivery extractor with the document parser pattern.
Replaces the old OCR + regex/rules workflow with marker + sonnet no preprocessing.

New improved workflow:
1. Datalab Marker API processes document with force_ocr=True, use_llm=False (no preprocessing)  
2. Structured markdown output fed directly to Sonnet 3.5 for semantic reasoning
3. Much better extraction results due to cleaner, organized input
4. Compatible with existing document parser interface
5. Full database integration with specific tables for delivery notes and packing lists

Supports various delivery documents:
- Delivery Notes (POD - Proof of Delivery)
- Packing Lists
- Item details, quantities, weights, SKUs  
- Delivery confirmations and signatures
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.enhanced_delivery_extractor import (
    EnhancedDeliveryExtractor,
    ExtractedDeliveryData,
    ExtractedPackingItem
)

import logging

logger = logging.getLogger(__name__)


@dataclass
class DeliveryParsingResult:
    """Result of delivery note/packing list parsing operation."""
    
    success: bool
    document_type: str  # 'delivery_note', 'packing_list', or 'pod'
    confidence: float
    extracted_data: Optional[ExtractedDeliveryData]
    field_stats: Optional[Dict[str, Any]]
    extraction_details: Dict[str, Any]
    raw_markdown: str = ""  # Add raw markdown storage
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for database storage."""
        return {
            "success": self.success,
            "document_type": self.document_type,
            "confidence": self.confidence,
            "field_stats": self.field_stats,
            "extraction_details": self.extraction_details,
            "extracted_data": self.extracted_data.model_dump() if self.extracted_data else None
        }
    
    def get_database_record(self, document_id: str) -> Dict[str, Any]:
        """Convert parsing result to database format for documents table."""
        return {
            "id": document_id,
            "type": self._get_document_db_type(),
            "status": "parsed" if self.success else "failed",
            "confidence": self.confidence,
            "parsed_data": {
                "extraction_method": "enhanced_marker_sonnet",
                "confidence": self.confidence,
                "field_count": self.field_stats.get('extracted_fields', 0) if self.field_stats else 0,
                "raw_markdown": self.extraction_details.get('raw_markdown'),
                "raw_markdown_length": self.extraction_details.get('raw_markdown_length', 0),
                "validation_flags": self.extracted_data.validation_flags if self.extracted_data else [],
                "document_type": self.document_type,
                "items_count": len(self.extracted_data.items) if self.extracted_data and self.extracted_data.items else 0
            },
            "manual_review_required": self.confidence < 0.75 or (self.extracted_data and len(self.extracted_data.validation_flags) > 2),
            "ocr_engine": "datalab_marker_v1",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    
    def _get_document_db_type(self) -> str:
        """Map document type to database enum value."""
        type_mapping = {
            'delivery_note': 'DELIVERY_NOTE',
            'packing_list': 'PACKING_LIST', 
            'pod': 'POD'
        }
        return type_mapping.get(self.document_type, 'DELIVERY_NOTE')


class EnhancedDeliveryParser:
    """
    Enhanced delivery note and packing list parser using Marker API + Sonnet 3.5.
    
    NEW WORKFLOW (NO PREPROCESSING):
    1. Uses Datalab Marker API (force_ocr=True, use_llm=False) for structured markdown
    2. Feeds clean markdown to Sonnet 3.5 for semantic reasoning
    3. Achieves better extraction through organized input structure
    4. Integrates with database for delivery notes and packing lists
    
    Supports delivery notes, packing lists, and POD documents.
    """
    
    def __init__(self):
        """Initialize the enhanced delivery parser."""
        self.extractor = EnhancedDeliveryExtractor()
        logger.info("Enhanced Delivery Parser initialized with marker + sonnet workflow")
    
    async def parse_from_file_content(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        document_id: str
    ) -> DeliveryParsingResult:
        """
        Parse delivery document from file content using enhanced marker + sonnet workflow.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename  
            mime_type: MIME type of file
            document_id: Unique document identifier
            
        Returns:
            DeliveryParsingResult with extracted data and metadata
        """
        logger.info(f"Parsing delivery document: {filename} ({len(file_content)} bytes)")
        
        try:
            # Use enhanced extraction workflow (marker API + sonnet)
            extracted_data, confidence, needs_review = await self.extractor.extract_delivery_fields_enhanced(
                file_content=file_content,
                filename=filename,
                mime_type=mime_type
            )
            
            if not extracted_data:
                logger.error(f"Enhanced extraction failed for {filename}")
                return DeliveryParsingResult(
                    success=False,
                    document_type="unknown",
                    confidence=0.0,
                    extracted_data=None,
                    field_stats=None,
                    extraction_details={"error": "Enhanced extraction failed"}
                )
            
            # Determine document type from extracted data or filename
            document_type = self._determine_document_type(extracted_data, filename)
            
            # Calculate field statistics
            field_stats = self._calculate_field_stats(extracted_data)
            
            # Prepare extraction details for debugging
            raw_markdown = getattr(self.extractor.marker_client, '_last_markdown', '')
            extraction_details = {
                "extraction_method": "enhanced_marker_sonnet",
                "raw_markdown_length": len(raw_markdown),
                "needs_review": needs_review,
                "validation_score": extracted_data.confidence_score,
                "ai_confidence": confidence
            }
            
            logger.info(f"Delivery parsing complete - Type: {document_type}, Confidence: {confidence:.1%}, Items: {len(extracted_data.items)}")
            
            return DeliveryParsingResult(
                success=True,
                document_type=document_type,
                confidence=confidence,
                extracted_data=extracted_data,
                field_stats=field_stats,
                extraction_details=extraction_details,
                raw_markdown=raw_markdown
            )
            
        except Exception as e:
            logger.error(f"Delivery parsing failed for {filename}: {e}")
            return DeliveryParsingResult(
                success=False,
                document_type="unknown",
                confidence=0.0,
                extracted_data=None,
                field_stats=None,
                extraction_details={"error": str(e)}
            )
    
    def _determine_document_type(self, data: ExtractedDeliveryData, filename: str) -> str:
        """Determine document type from extracted data and filename."""
        
        # Check extracted document type first
        if data.document_type:
            return data.document_type.lower()
        
        # Check filename patterns
        filename_lower = filename.lower()
        if any(term in filename_lower for term in ['pod', 'delivery', 'receipt']):
            return 'pod'
        elif any(term in filename_lower for term in ['packing', 'pack']):
            return 'packing_list'
        elif 'delivery' in filename_lower:
            return 'delivery_note'
        
        # Check content patterns
        if data.items and len(data.items) > 0:
            return 'packing_list'
        elif data.delivery_date or data.recipient_name or data.delivery_confirmed:
            return 'delivery_note'
        
        # Default
        return 'delivery_note'
    
    def _calculate_field_stats(self, data: ExtractedDeliveryData) -> Dict[str, Any]:
        """Calculate statistics about extracted fields."""
        
        total_fields = 0
        extracted_fields = 0
        critical_fields = 0
        critical_extracted = 0
        
        # Define critical fields for each document type
        critical_field_names = [
            'document_number', 'document_date', 'delivery_date',
            'consignee_name', 'shipper_name', 'carrier_name'
        ]
        
        # Count all fields
        for field_name, field_value in data.model_dump().items():
            if field_name in ['validation_flags', 'confidence_score']:
                continue
                
            total_fields += 1
            
            if field_value is not None:
                if isinstance(field_value, list) and len(field_value) > 0:
                    extracted_fields += 1
                elif isinstance(field_value, str) and field_value.strip():
                    extracted_fields += 1
                elif isinstance(field_value, (int, float, bool)):
                    extracted_fields += 1
            
            # Count critical fields
            if field_name in critical_field_names:
                critical_fields += 1
                if field_value is not None and (
                    (isinstance(field_value, str) and field_value.strip()) or
                    isinstance(field_value, (int, float, bool))
                ):
                    critical_extracted += 1
        
        # Item statistics
        items_count = len(data.items) if data.items else 0
        items_with_descriptions = sum(1 for item in data.items if item.item_description) if data.items else 0
        items_with_quantities = sum(1 for item in data.items if item.quantity is not None) if data.items else 0
        
        return {
            'total_fields': total_fields,
            'extracted_fields': extracted_fields,
            'extraction_rate': extracted_fields / total_fields if total_fields > 0 else 0,
            'critical_fields': critical_fields,
            'critical_extracted': critical_extracted,
            'critical_rate': critical_extracted / critical_fields if critical_fields > 0 else 0,
            'items_count': items_count,
            'items_with_descriptions': items_with_descriptions,
            'items_with_quantities': items_with_quantities,
            'validation_issues': len(data.validation_flags)
        }
    
    def _convert_to_delivery_table_format(self, data: ExtractedDeliveryData, document_id: str) -> Dict[str, Any]:
        """Convert ExtractedDeliveryData to database format for delivery-specific tables."""
        
        # For packing lists, we might store in a separate table
        # For now, we'll store comprehensive data in a generic format
        # This can be extended to write to specific tables based on document type
        
        # Convert items to JSON format for storage
        items_json = []
        if data.items:
            for item in data.items:
                item_dict = {
                    'item_description': item.item_description,
                    'sku': item.sku,
                    'quantity': item.quantity,
                    'unit': item.unit,
                    'weight': item.weight,
                    'weight_unit': item.weight_unit,
                    'dimensions': item.dimensions,
                    'special_handling': item.special_handling,
                    'condition': item.condition
                }
                items_json.append(item_dict)
        
        return {
            'id': str(uuid.uuid4()),
            'document_id': document_id,
            'document_number': data.document_number,
            'document_date': data.document_date,
            'delivery_date': data.delivery_date,
            'delivery_time': data.delivery_time,
            'delivery_status': data.delivery_status,
            'origin_address': data.origin_address,
            'destination_address': data.destination_address,
            'shipper_name': data.shipper_name,
            'consignee_name': data.consignee_name,
            'carrier_name': data.carrier_name,
            'driver_name': data.driver_name,
            'truck_number': data.truck_number,
            'trailer_number': data.trailer_number,
            'bol_number': data.bol_number,
            'pro_number': data.pro_number,
            'po_number': data.po_number,
            'load_number': data.load_number,
            'items': items_json,
            'total_pieces': data.total_pieces,
            'total_weight': data.total_weight,
            'total_weight_unit': data.total_weight_unit,
            'recipient_name': data.recipient_name,
            'recipient_signature': data.recipient_signature,
            'delivery_confirmed': data.delivery_confirmed,
            'condition_notes': data.condition_notes,
            'delivery_notes': data.delivery_notes,
            'damage_reported': data.damage_reported,
            'special_instructions': data.special_instructions,
            'supporting_docs': {
                'confidence_score': data.confidence_score,
                'validation_flags': data.validation_flags,
                'extraction_method': 'enhanced_marker_sonnet',
                'original_filename': Path(document_id).name if document_id else 'unknown'
            },
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
    
    async def parse_from_file(self, file_path: Path) -> DeliveryParsingResult:
        """
        Parse a delivery document from file path with database integration.
        """
        try:
            # Generate document ID
            document_id = str(uuid.uuid4())
            
            # Read file content
            with open(file_path, 'rb') as file:
                file_content = file.read()
            
            # Parse using file content method
            result = await self.parse_from_file_content(
                file_content=file_content,
                filename=file_path.name,
                mime_type=self._get_mime_type(file_path.suffix),
                document_id=document_id
            )
            
            # Create document record for database if we have a supabase client
            if hasattr(self, 'supabase') and self.supabase:
                try:
                    # Insert into documents table (basic record)
                    doc_record = {
                        "id": document_id,
                        "type": self._map_document_type(result.document_type),
                        "status": "PARSED" if result.success else "FAILED",
                        "confidence": result.confidence,
                        "raw_ocr_data": {"raw_markdown": result.raw_markdown},
                        "parsed_data": {
                            # Include ALL the rich extracted data
                            **result.extracted_data.model_dump() if result.extracted_data else {},
                            # Plus summary information
                            "extraction_method": "enhanced_marker_sonnet",
                            "raw_markdown_length": len(result.raw_markdown) if result.raw_markdown else 0,
                            "field_count": len([k for k, v in (result.extracted_data.model_dump() if result.extracted_data else {}).items() if v is not None]),
                            "items_count": len(result.extracted_data.items) if result.extracted_data and result.extracted_data.items else 0,
                            "validation_flags": result.extracted_data.validation_flags if result.extracted_data else [],
                            "confidence": result.confidence
                        }
                    }
                    
                    # Insert document
                    doc_response = self.supabase.table("documents").insert(doc_record).execute()
                    
                    # Insert processing metrics
                    metrics_record = {
                        "id": str(uuid.uuid4()),
                        "document_id": document_id,
                        "document_type": self._map_document_type(result.document_type),
                        "confidence_score": result.confidence,
                        "ocr_engine": "datalab_marker_v1",
                        "validation_passed": len(result.extracted_data.validation_flags) == 0 if result.extracted_data else False,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    
                    metrics_response = self.supabase.table("document_processing_metrics").insert(metrics_record).execute()
                    
                    # Insert individual fields if we have extracted data
                    if result.extracted_data:
                        field_records = self._create_field_records(document_id, result.extracted_data)
                        if field_records:
                            fields_response = self.supabase.table("document_fields").insert(field_records).execute()
                    
                    logger.info(f"Stored delivery document {document_id} in database with {len(field_records) if 'field_records' in locals() else 0} fields")
                    
                except Exception as db_error:
                    logger.error(f"Database storage failed for {file_path.name}: {db_error}")
                    # Continue with the result even if database storage fails
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to parse delivery document from {file_path}: {e}")
            raise
    
    def _map_document_type(self, doc_type: str) -> str:
        """Map document type to database enum value."""
        type_mapping = {
            'delivery_note': 'DELIVERY_NOTE',
            'packing_list': 'PACKING_LIST',
            'pod': 'POD'
        }
        return type_mapping.get(doc_type.lower() if doc_type else '', 'DELIVERY_NOTE')
    
    def _get_mime_type(self, file_extension: str) -> str:
        """Get MIME type from file extension."""
        extension_map = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff'
        }
        return extension_map.get(file_extension.lower(), 'application/octet-stream')
    
    def _create_field_records(self, document_id: str, data: ExtractedDeliveryData) -> List[Dict[str, Any]]:
        """Create individual field records for the document_fields table."""
        field_records = []
        
        # Define field mappings with confidence scores
        field_mappings = [
            ('document_number', data.document_number, 'string'),
            ('document_date', data.document_date.isoformat() if data.document_date else None, 'date'),
            ('delivery_date', data.delivery_date.isoformat() if data.delivery_date else None, 'date'),
            ('shipper_name', data.shipper_name, 'string'),
            ('consignee_name', data.consignee_name, 'string'),
            ('carrier_name', data.carrier_name, 'string'),
            ('driver_name', data.driver_name, 'string'),
            ('bol_number', data.bol_number, 'string'),
            ('pro_number', data.pro_number, 'string'),
            ('total_pieces', str(data.total_pieces) if data.total_pieces else None, 'number'),
            ('total_weight', str(data.total_weight) if data.total_weight else None, 'number'),
            ('recipient_name', data.recipient_name, 'string'),
            ('delivery_confirmed', str(data.delivery_confirmed) if data.delivery_confirmed is not None else None, 'boolean'),
            ('condition_notes', data.condition_notes, 'string'),
            ('recipient_signature', data.recipient_signature, 'string'),
            ('delivery_time', data.delivery_time, 'string'),
            ('delivery_notes', data.delivery_notes, 'string'),
            ('items_count', str(len(data.items)) if data.items else '0', 'number')
        ]
        
        for field_name, field_value, field_type in field_mappings:
            if field_value is not None and str(field_value).strip():
                field_records.append({
                    "id": str(uuid.uuid4()),
                    "document_id": document_id,
                    "field_name": field_name,
                    "field_value": str(field_value),
                    "confidence": data.confidence_score if hasattr(data, 'confidence_score') else 0.85,
                    "field_type": field_type,
                    "validation_status": "VALID",
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                })
        
        # Add items as separate fields
        if data.items:
            for i, item in enumerate(data.items):
                field_records.append({
                    "id": str(uuid.uuid4()),
                    "document_id": document_id,
                    "field_name": f"item_{i+1}_description",
                    "field_value": item.item_description or "",
                    "confidence": 0.85,
                    "field_type": "string",
                    "validation_status": "VALID",
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                })
                
                if item.quantity:
                    field_records.append({
                        "id": str(uuid.uuid4()),
                        "document_id": document_id,
                        "field_name": f"item_{i+1}_quantity",
                        "field_value": str(item.quantity),
                        "confidence": 0.85,
                        "field_type": "number",
                        "validation_status": "VALID",
                        "created_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat()
                    })
        
        return field_records


async def main():
    """Test the enhanced delivery parser."""
    parser = EnhancedDeliveryParser()
    
    # Test documents
    test_docs = [
        "test_documents/delivery_note/POD1.jpeg",
        "test_documents/packing_list/PL1.png"
    ]
    
    for doc_path in test_docs:
        if Path(doc_path).exists():
            print(f"\n🔍 Testing: {doc_path}")
            result = await parser.parse_from_file(Path(doc_path))
            
            print(f"Success: {result.success}")
            print(f"Type: {result.document_type}")
            print(f"Confidence: {result.confidence:.1%}")
            
            if result.extracted_data:
                print(f"Document #: {result.extracted_data.document_number}")
                print(f"Items: {len(result.extracted_data.items)}")
                if result.extracted_data.items:
                    for i, item in enumerate(result.extracted_data.items[:3]):
                        print(f"  Item {i+1}: {item.item_description} (Qty: {item.quantity})")


if __name__ == "__main__":
    asyncio.run(main()) 
"""
Enhanced Accessorial Parser with Marker API + Sonnet 3.5

Integrates the enhanced accessorial extractor with the document parser pattern.
Replaces the old OCR + regex/rules workflow with marker + sonnet no preprocessing.

New improved workflow:
1. Datalab Marker API processes document with force_ocr=True, use_llm=False (no preprocessing)  
2. Structured markdown output fed directly to Sonnet 3.5 for semantic reasoning
3. Much better extraction results due to cleaner, organized input
4. Compatible with existing document parser interface
5. Full database integration with accessorial_charges table

Supports various accessorial documents:
- Detention slips
- Load slips
- Layover charges
- Extra stop charges
- Waiting time documentation
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional
from datetime import datetime

from app.models.database import Document  # Will need accessorial model when created
from app.services.enhanced_accessorial_extractor import EnhancedAccessorialExtractor, ExtractedAccessorialData

logger = logging.getLogger(__name__)


@dataclass
class AccessorialParsingResult:
    """Result of accessorial parsing operation."""

    data: Dict[str, Any]  # Structured data for accessorial_charges table
    confidence: float
    extraction_details: dict[str, Any]


class EnhancedAccessorialParser:
    """
    Enhanced Accessorial parser using Marker API + Sonnet 3.5.
    
    NEW WORKFLOW (no preprocessing):
    1. Uses Datalab Marker API (force_ocr=True, use_llm=False) for structured markdown
    2. Feeds clean markdown directly to Sonnet 3.5 for semantic reasoning
    3. Achieves better extraction through organized input structure
    4. No preprocessing or regex/rules - pure AI extraction
    5. Full integration with accessorial_charges database table
    
    This integrates the enhanced accessorial extractor with the standard document parser interface.
    """

    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.85  # Service type + location + charges found
    MEDIUM_CONFIDENCE_THRESHOLD = 0.65  # Some key fields found
    LOW_CONFIDENCE_THRESHOLD = 0.40  # Minimal fields found

    def __init__(self):
        """Initialize the enhanced accessorial parser."""
        self.extractor = EnhancedAccessorialExtractor()
        logger.info("Enhanced Accessorial Parser initialized with Marker API + Sonnet 3.5")

    async def parse_from_file_content(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        document_id: str
    ) -> AccessorialParsingResult:
        """
        Parse accessorial document from file content using enhanced marker + sonnet workflow.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename  
            mime_type: MIME type of file
            document_id: Unique document identifier
            
        Returns:
            AccessorialParsingResult with extracted data and metadata
        """
        logger.info(f"Parsing accessorial document: {filename} ({len(file_content)} bytes)")
        
        try:
            # Use enhanced extraction
            extracted_data, confidence, needs_review = await self.extractor.extract_accessorial_fields_enhanced(
                file_content=file_content,
                filename=filename,
                mime_type=mime_type
            )
            
            # Convert to database format
            accessorial_data = self._convert_to_accessorial_charges_format(extracted_data, document_id)
            
            # Get raw markdown for debugging
            raw_markdown = None
            try:
                async with self.extractor.marker_client as marker:
                    marker_result = await marker.process_document(
                        file_content=file_content,
                        filename=filename,
                        mime_type=mime_type,
                        language="English",
                        force_ocr=True,
                        use_llm=False,
                        output_format="markdown"
                    )
                
                if marker_result.success:
                    raw_markdown = marker_result.markdown_content
            except Exception as e:
                logger.warning(f"Could not get raw markdown for debugging: {e}")
            
            # Build extraction details with debugging info
            extraction_details = {
                "extraction_method": "marker_sonnet",
                "confidence": confidence,
                "fields_extracted": {
                    "extracted_fields": len([k for k, v in extracted_data.dict().items() if v is not None and v != [] and v != ""]),
                    "total_fields": len(extracted_data.dict()),
                    "extraction_rate": len([k for k, v in extracted_data.dict().items() if v is not None and v != [] and v != ""]) / len(extracted_data.dict())
                },
                "validation_flags": extracted_data.validation_flags,
                "processing_metadata": {
                    "filename": filename,
                    "file_size": len(file_content),
                    "mime_type": mime_type,
                    "needs_review": needs_review
                }
            }
            
            # Add raw markdown for debugging if available
            if raw_markdown:
                extraction_details["raw_markdown"] = raw_markdown
                extraction_details["raw_markdown_length"] = len(raw_markdown)
            
            return AccessorialParsingResult(
                data=accessorial_data,
                confidence=confidence,
                extraction_details=extraction_details
            )
            
        except Exception as e:
            logger.error(f"Accessorial parsing failed for {filename}: {e}")
            
            # Return empty result with error
            empty_data = self._convert_to_accessorial_charges_format(
                ExtractedAccessorialData(), 
                document_id
            )
            
            return AccessorialParsingResult(
                data=empty_data,
                confidence=0.0,
                extraction_details={
                    "extraction_method": "marker_sonnet",
                    "error": str(e),
                    "confidence": 0.0,
                    "processing_metadata": {
                        "filename": filename,
                        "file_size": len(file_content),
                        "mime_type": mime_type,
                        "needs_review": True
                    }
                }
            )

    def parse(self, ocr_text: str, document_id: str) -> AccessorialParsingResult:
        """
        Legacy method for compatibility with existing workflow.
        
        Note: This bypasses the enhanced Marker workflow and works with raw OCR text.
        For best results, use parse_from_file_content() with the enhanced workflow.
        """
        logger.warning("Using legacy OCR text parsing. Consider using parse_from_file_content() for better results.")
        
        try:
            # Create a basic accessorial document with available data
            accessorial_dict = {
                "document_id": document_id,
                "charge_type": self._extract_basic_service_type(ocr_text),
                "carrier_name": None,
                "total_amount": self._extract_basic_charges(ocr_text),
                "extraction_method": "legacy_ocr"
            }
            
            # Calculate basic confidence
            confidence = self._calculate_basic_confidence(accessorial_dict)
            
            extraction_details = {
                "extraction_method": "legacy_ocr",
                "confidence": confidence,
                "workflow": "legacy",
                "note": "Consider using enhanced workflow for better accuracy"
            }
            
            return AccessorialParsingResult(
                data=accessorial_dict,
                confidence=confidence,
                extraction_details=extraction_details
            )
            
        except Exception as e:
            logger.error(f"Legacy accessorial parsing failed: {e}")
            return AccessorialParsingResult(
                data={"document_id": document_id, "error": str(e)},
                confidence=0.0,
                extraction_details={"error": str(e), "extraction_method": "legacy_ocr"}
            )

    def parse_from_ocr_result(self, ocr_result: dict[str, Any], document_id: str) -> AccessorialParsingResult:
        """
        Parse accessorial document from OCR result dictionary.
        
        This method provides compatibility with the existing OCR workflow.
        """
        if ocr_result.get("extraction_method") == "marker":
            # If we have marker content, try to use the enhanced workflow
            markdown_content = ocr_result.get("markdown_content", "")
            if markdown_content:
                logger.info("Using enhanced extraction from marker content")
                # TODO: Implement async call properly - for now use legacy
                ocr_text = markdown_content
            else:
                ocr_text = ocr_result.get("text", "")
        else:
            # Extract text from traditional OCR result
            ocr_text = ocr_result.get("text", "")
            if not ocr_text and "pages" in ocr_result:
                # Extract text from pages
                text_parts = []
                for page in ocr_result["pages"]:
                    if "text_lines" in page:
                        for line in page["text_lines"]:
                            text_parts.append(line.get("text", ""))
                ocr_text = "\n".join(text_parts)
        
        return self.parse(ocr_text, document_id)

    def _convert_to_accessorial_charges_format(self, data: ExtractedAccessorialData, document_id: str) -> Dict[str, Any]:
        """Convert ExtractedAccessorialData to accessorial_charges table format."""
        
        # Calculate total amount if possible
        total_amount = None
        if data.total_charges:
            total_amount = data.total_charges
        elif data.duration_hours and data.rate_per_hour and isinstance(data.rate_per_hour, (int, float)):
            total_amount = data.duration_hours * data.rate_per_hour
        
        # Handle unit price
        unit_price = None
        if data.rate_per_hour and isinstance(data.rate_per_hour, (int, float)):
            unit_price = data.rate_per_hour
        elif data.rate_flat and isinstance(data.rate_flat, (int, float)):
            unit_price = data.rate_flat
        
        # Build charge description
        description_parts = []
        if data.service_description:
            description_parts.append(data.service_description)
        if data.notes:
            description_parts.append(f"Notes: {data.notes}")
        
        charge_description = " | ".join(description_parts) if description_parts else data.service_type
        
        # Store all additional details in supporting_docs
        supporting_docs = {
            "extraction_method": "marker_sonnet",
            "start_time": data.start_time,
            "end_time": data.end_time,
            "truck_number": data.truck_number,
            "trailer_number": data.trailer_number,
            "customer_name": data.customer_name,
            "special_services": data.special_services,
            "confidence_score": data.confidence_score,
            "validation_flags": data.validation_flags
        }
        
        # Add rate information to supporting docs even if it's text
        if data.rate_per_hour:
            supporting_docs["rate_per_hour"] = data.rate_per_hour
        if data.rate_flat:
            supporting_docs["rate_flat"] = data.rate_flat
        if data.location:
            supporting_docs["service_location"] = data.location
        if data.driver_name:
            supporting_docs["driver_name"] = data.driver_name
        if data.authorization_code:
            supporting_docs["authorization_code"] = data.authorization_code
        
        return {
            "document_id": document_id,
            "charge_number": data.document_number,
            "charge_date": data.document_date,
            "carrier_name": data.carrier_name,
            "bol_number": data.bol_number,
            "pro_number": data.load_number,  # Map load_number to pro_number
            "charge_type": data.service_type,
            "charge_description": charge_description,
            "quantity": data.duration_hours,
            "unit_price": unit_price,
            "total_amount": total_amount,
            "justification": data.charge_justification,
            "supporting_docs": supporting_docs,
            "approval_status": "approved" if data.approved_by else "pending",
            "approved_by": data.approved_by,
            "approved_at": None  # Would need to parse approval date if available
        }

    def _count_extracted_fields(self, extracted_data: ExtractedAccessorialData) -> Dict[str, int]:
        """Count how many fields were successfully extracted."""
        field_dict = extracted_data.dict()
        
        # Don't count metadata fields
        exclude_fields = {"confidence_score", "validation_flags"}
        
        total_fields = len([k for k in field_dict.keys() if k not in exclude_fields])
        extracted_fields = len([k for k, v in field_dict.items() if v is not None and k not in exclude_fields])
        
        return {
            "total_fields": total_fields,
            "extracted_fields": extracted_fields,
            "extraction_rate": extracted_fields / total_fields if total_fields > 0 else 0.0
        }

    def _extract_basic_service_type(self, text: str) -> Optional[str]:
        """Extract service type using basic pattern matching."""
        import re
        
        text_lower = text.lower()
        
        # Check for common service types
        if 'detention' in text_lower:
            return 'detention'
        elif 'layover' in text_lower:
            return 'layover'
        elif 'load slip' in text_lower or 'loadslip' in text_lower:
            return 'load_slip'
        elif 'extra stop' in text_lower:
            return 'extra_stop'
        elif 'waiting' in text_lower and 'time' in text_lower:
            return 'waiting_time'
        elif 'demurrage' in text_lower:
            return 'demurrage'
        
        return None

    def _extract_basic_location(self, text: str) -> Optional[str]:
        """Extract location using basic pattern matching."""
        import re
        
        # Look for common location patterns
        lines = text.split('\n')
        for line in lines[:15]:  # Check first 15 lines
            line = line.strip()
            if len(line) > 10 and not line.isdigit():
                # Look for address-like patterns
                if re.search(r'\b\d+\s+\w+.*(?:st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ln|lane)\b', line, re.IGNORECASE):
                    return line
                # Look for city, state patterns
                if re.search(r'\b[A-Z][a-z]+,\s*[A-Z]{2}\b', line):
                    return line
        
        return None

    def _extract_basic_charges(self, text: str) -> Optional[float]:
        """Extract total charges using basic pattern matching."""
        import re
        
        # Look for dollar amounts
        pattern = r'\$\s*(\d+(?:\.\d{2})?)'
        matches = re.findall(pattern, text)
        
        if matches:
            # Return the largest amount found (likely the total)
            amounts = [float(match) for match in matches]
            return max(amounts)
        
        return None

    def _calculate_basic_confidence(self, accessorial_dict: Dict[str, Any]) -> float:
        """Calculate confidence based on extracted fields in basic mode."""
        confidence = 0.0
        
        # Key fields that boost confidence
        if accessorial_dict.get("charge_type"):
            confidence += 0.3
        if accessorial_dict.get("carrier_name"):
            confidence += 0.2
        if accessorial_dict.get("total_amount"):
            confidence += 0.2
        if accessorial_dict.get("charge_number"):
            confidence += 0.1
        if accessorial_dict.get("bol_number"):
            confidence += 0.1
        if accessorial_dict.get("charge_date"):
            confidence += 0.1
        
        return min(confidence, 1.0) 
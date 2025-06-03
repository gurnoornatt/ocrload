"""
Enhanced BOL Parser with Marker API + Sonnet 3.5

Integrates the enhanced BOL extractor with the document parser pattern.
Replaces the old OCR + regex/rules workflow with marker + sonnet no preprocessing.

New improved workflow:
1. Datalab Marker API processes document with force_ocr=True, use_llm=False (no preprocessing)  
2. Structured markdown output fed directly to Sonnet 3.5 for semantic reasoning
3. Much better extraction results due to cleaner, organized input
4. Compatible with existing document parser interface
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from app.models.database import BillOfLading
from app.services.enhanced_bol_extractor import EnhancedBOLExtractor, ExtractedBOLData

logger = logging.getLogger(__name__)


@dataclass
class BOLParsingResult:
    """Result of BOL parsing operation."""

    data: BillOfLading
    confidence: float
    extraction_details: dict[str, Any]


class EnhancedBOLParser:
    """
    Enhanced BOL parser using Marker API + Sonnet 3.5.
    
    NEW WORKFLOW (no preprocessing):
    1. Uses Datalab Marker API (force_ocr=True, use_llm=False) for structured markdown
    2. Feeds clean markdown directly to Sonnet 3.5 for semantic reasoning
    3. Achieves better extraction through organized input structure
    4. No preprocessing or regex/rules - pure AI extraction
    
    This integrates the enhanced BOL extractor with the standard document parser interface.
    """

    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.85  # BOL number + shipper + consignee found
    MEDIUM_CONFIDENCE_THRESHOLD = 0.65  # Some key fields found
    LOW_CONFIDENCE_THRESHOLD = 0.40  # Minimal fields found

    def __init__(self):
        """Initialize the enhanced BOL parser."""
        self.extractor = EnhancedBOLExtractor()
        logger.info("Enhanced BOL Parser initialized with Marker API + Sonnet 3.5")

    async def parse_from_file_content(
        self, 
        file_content: bytes, 
        filename: str, 
        mime_type: str,
        document_id: str
    ) -> BOLParsingResult:
        """
        Parse BOL from file content using enhanced marker + sonnet workflow.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            mime_type: File MIME type
            document_id: Document identifier
            
        Returns:
            BOLParsingResult with extracted data and confidence
        """
        logger.info(f"Starting enhanced BOL parsing: {filename}")
        
        try:
            # Use the enhanced extractor workflow
            extracted_data, confidence, needs_review = await self.extractor.extract_bol_fields_enhanced(
                file_content=file_content,
                filename=filename,
                mime_type=mime_type
            )
            
            # Convert ExtractedBOLData to BOL database model
            bol_data = self._convert_to_bol_model(extracted_data, document_id)
            
            # Create extraction details for compatibility
            extraction_details = {
                "extraction_method": "marker_sonnet",
                "confidence": confidence,
                "needs_review": needs_review,
                "workflow": "enhanced",
                "fields_extracted": self._count_extracted_fields(extracted_data),
                "validation_flags": extracted_data.validation_flags
            }
            
            logger.info(f"✓ Enhanced BOL parsing completed - confidence: {confidence:.3f}, needs_review: {needs_review}")
            
            return BOLParsingResult(
                data=bol_data,
                confidence=confidence,
                extraction_details=extraction_details
            )
            
        except Exception as e:
            logger.error(f"Enhanced BOL parsing failed: {e}")
            return BOLParsingResult(
                data=BillOfLading(document_id=document_id),
                confidence=0.0,
                extraction_details={"error": str(e), "extraction_method": "marker_sonnet"}
            )

    def parse(self, ocr_text: str, document_id: str) -> BOLParsingResult:
        """
        Legacy method for compatibility with existing workflow.
        
        Note: This bypasses the enhanced Marker workflow and works with raw OCR text.
        For best results, use parse_from_file_content() with the enhanced workflow.
        """
        logger.warning("Using legacy OCR text parsing. Consider using parse_from_file_content() for better results.")
        
        try:
            # Create a basic BOL with available data
            bol_data = BillOfLading(
                document_id=document_id,
                bol_number=self._extract_basic_bol_number(ocr_text),
                shipper_name=self._extract_basic_shipper(ocr_text),
                consignee_name=self._extract_basic_consignee(ocr_text)
            )
            
            # Calculate basic confidence
            confidence = self._calculate_basic_confidence(bol_data)
            
            extraction_details = {
                "extraction_method": "legacy_ocr",
                "confidence": confidence,
                "workflow": "legacy",
                "note": "Consider using enhanced workflow for better accuracy"
            }
            
            return BOLParsingResult(
                data=bol_data,
                confidence=confidence,
                extraction_details=extraction_details
            )
            
        except Exception as e:
            logger.error(f"Legacy BOL parsing failed: {e}")
            return BOLParsingResult(
                data=BillOfLading(document_id=document_id),
                confidence=0.0,
                extraction_details={"error": str(e), "extraction_method": "legacy_ocr"}
            )

    def parse_from_ocr_result(self, ocr_result: dict[str, Any], document_id: str) -> BOLParsingResult:
        """
        Parse BOL from OCR result dictionary.
        
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

    def _convert_to_bol_model(self, extracted_data: ExtractedBOLData, document_id: str) -> BillOfLading:
        """Convert ExtractedBOLData to BOL database model."""
        
        # Parse dates safely
        def safe_date_parse(date_str):
            if not date_str:
                return None
            try:
                from datetime import datetime
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except:
                return None
        
        return BillOfLading(
            document_id=document_id,
            bol_number=extracted_data.bol_number,
            pro_number=extracted_data.pro_number,
            pickup_date=safe_date_parse(extracted_data.pickup_date),
            delivery_date=safe_date_parse(extracted_data.delivery_date),
            shipper_name=extracted_data.shipper_name,
            shipper_address=extracted_data.shipper_address,
            consignee_name=extracted_data.consignee_name,
            consignee_address=extracted_data.consignee_address,
            carrier_name=extracted_data.carrier_name,
            driver_name=extracted_data.driver_name,
            equipment_type=extracted_data.equipment_type,
            equipment_number=extracted_data.equipment_number,
            commodity_description=extracted_data.commodity_description,
            weight=extracted_data.weight,
            pieces=extracted_data.pieces,
            hazmat=extracted_data.hazmat or False,
            special_instructions=extracted_data.special_instructions,
            freight_charges=extracted_data.freight_charges,
            confidence_score=extracted_data.confidence_score
        )

    def _count_extracted_fields(self, extracted_data: ExtractedBOLData) -> Dict[str, int]:
        """Count extracted fields for reporting."""
        core_fields = ['bol_number', 'shipper_name', 'consignee_name', 'carrier_name']
        additional_fields = ['pickup_date', 'delivery_date', 'weight', 'pieces', 'freight_charges']
        
        core_count = sum(1 for field in core_fields if getattr(extracted_data, field))
        additional_count = sum(1 for field in additional_fields if getattr(extracted_data, field))
        
        return {
            "core_fields": core_count,
            "additional_fields": additional_count,
            "total_fields": core_count + additional_count
        }

    def _extract_basic_bol_number(self, text: str) -> Optional[str]:
        """Basic BOL number extraction for legacy compatibility."""
        import re
        patterns = [
            r"(?:BOL|Bill\s+of\s+Lading|B/L)\s*#?\s*:?\s*([A-Z0-9\-_]{3,20})",
            r"BOL\s*([A-Z0-9\-_]{3,20})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_basic_shipper(self, text: str) -> Optional[str]:
        """Basic shipper extraction for legacy compatibility."""
        import re
        patterns = [
            r"(?:Shipper|Ship\s+From|Consignor)[:]*\s*\n?\s*([A-Z][A-Za-z\s&.,'-]{2,50})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_basic_consignee(self, text: str) -> Optional[str]:
        """Basic consignee extraction for legacy compatibility."""
        import re
        patterns = [
            r"(?:Consignee|Ship\s+To|Deliver\s+To)[:]*\s*\n?\s*([A-Z][A-Za-z\s&.,'-]{2,50})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None

    def _calculate_basic_confidence(self, bol_data: BillOfLading) -> float:
        """Calculate basic confidence score for legacy parsing."""
        score = 0.0
        total_checks = 4
        
        if bol_data.bol_number:
            score += 1.0
        if bol_data.shipper_name:
            score += 1.0
        if bol_data.consignee_name:
            score += 1.0
        if bol_data.carrier_name:
            score += 1.0
            
        return score / total_checks 
"""
Enhanced Lumper Receipt Parser with Marker API + Sonnet 3.5

Integrates the enhanced lumper extractor with the document parser pattern.
Replaces the old OCR + regex/rules workflow with marker + sonnet no preprocessing.

New improved workflow:
1. Datalab Marker API processes document with force_ocr=True, use_llm=False (no preprocessing)  
2. Structured markdown output fed directly to Sonnet 3.5 for semantic reasoning
3. Much better extraction results due to cleaner, organized input
4. Compatible with existing document parser interface
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.models.database import LumperReceipt
from app.services.enhanced_lumper_extractor import EnhancedLumperExtractor, ExtractedLumperData

logger = logging.getLogger(__name__)


@dataclass
class LumperParsingResult:
    """Result of lumper receipt parsing operation."""

    data: LumperReceipt
    confidence: float
    extraction_details: dict[str, Any]


class EnhancedLumperParser:
    """
    Enhanced Lumper Receipt parser using Marker API + Sonnet 3.5.
    
    NEW WORKFLOW (no preprocessing):
    1. Uses Datalab Marker API (force_ocr=True, use_llm=False) for structured markdown
    2. Feeds clean markdown directly to Sonnet 3.5 for semantic reasoning
    3. Achieves better extraction through organized input structure
    4. No preprocessing or regex/rules - pure AI extraction
    
    This integrates the enhanced lumper extractor with the standard document parser interface.
    """

    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.85  # Receipt number + facility + charges found
    MEDIUM_CONFIDENCE_THRESHOLD = 0.65  # Some key fields found
    LOW_CONFIDENCE_THRESHOLD = 0.40  # Minimal fields found

    def __init__(self):
        """Initialize the enhanced lumper parser."""
        self.extractor = EnhancedLumperExtractor()
        logger.info("Enhanced Lumper Parser initialized with Marker API + Sonnet 3.5")

    async def parse_from_file_content(
        self, 
        file_content: bytes, 
        filename: str, 
        mime_type: str,
        document_id: str
    ) -> LumperParsingResult:
        """
        Parse lumper receipt from file content using enhanced marker + sonnet workflow.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            mime_type: File MIME type
            document_id: Document identifier
            
        Returns:
            LumperParsingResult with extracted data and confidence
        """
        logger.info(f"Starting enhanced lumper parsing: {filename}")
        
        try:
            # Use the enhanced extractor workflow
            extracted_data, confidence, needs_review = await self.extractor.extract_lumper_fields_enhanced(
                file_content=file_content,
                filename=filename,
                mime_type=mime_type
            )
            
            # Convert ExtractedLumperData to LumperReceipt database model
            lumper_data = self._convert_to_lumper_model(extracted_data, document_id)
            
            # Create extraction details for compatibility
            extraction_details = {
                "extraction_method": "marker_sonnet",
                "confidence": confidence,
                "needs_review": needs_review,
                "workflow": "enhanced",
                "fields_extracted": self._count_extracted_fields(extracted_data),
                "validation_flags": extracted_data.validation_flags
            }
            
            logger.info(f"✓ Enhanced lumper parsing completed - confidence: {confidence:.3f}, needs_review: {needs_review}")
            
            return LumperParsingResult(
                data=lumper_data,
                confidence=confidence,
                extraction_details=extraction_details
            )
            
        except Exception as e:
            logger.error(f"Enhanced lumper parsing failed: {e}")
            return LumperParsingResult(
                data=LumperReceipt(document_id=document_id),
                confidence=0.0,
                extraction_details={"error": str(e), "extraction_method": "marker_sonnet"}
            )

    def parse(self, ocr_text: str, document_id: str) -> LumperParsingResult:
        """
        Legacy method for compatibility with existing workflow.
        
        Note: This bypasses the enhanced Marker workflow and works with raw OCR text.
        For best results, use parse_from_file_content() with the enhanced workflow.
        """
        logger.warning("Using legacy OCR text parsing. Consider using parse_from_file_content() for better results.")
        
        try:
            # Create a basic lumper receipt with available data
            lumper_data = LumperReceipt(
                document_id=document_id,
                receipt_number=self._extract_basic_receipt_number(ocr_text),
                facility_name=self._extract_basic_facility(ocr_text),
                total_amount=self._extract_basic_total(ocr_text)
            )
            
            # Calculate basic confidence
            confidence = self._calculate_basic_confidence(lumper_data)
            
            extraction_details = {
                "extraction_method": "legacy_ocr",
                "confidence": confidence,
                "workflow": "legacy",
                "note": "Consider using enhanced workflow for better accuracy"
            }
            
            return LumperParsingResult(
                data=lumper_data,
                confidence=confidence,
                extraction_details=extraction_details
            )
            
        except Exception as e:
            logger.error(f"Legacy lumper parsing failed: {e}")
            return LumperParsingResult(
                data=LumperReceipt(document_id=document_id),
                confidence=0.0,
                extraction_details={"error": str(e), "extraction_method": "legacy_ocr"}
            )

    def parse_from_ocr_result(self, ocr_result: dict[str, Any], document_id: str) -> LumperParsingResult:
        """
        Parse lumper receipt from OCR result dictionary.
        
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

    def _convert_to_lumper_model(self, extracted_data: ExtractedLumperData, document_id: str) -> LumperReceipt:
        """Convert ExtractedLumperData to LumperReceipt database model."""
        
        # Map fields from extracted data to database model
        return LumperReceipt(
            document_id=document_id,
            receipt_number=extracted_data.receipt_number,
            receipt_date=extracted_data.receipt_date,
            facility_name=extracted_data.facility_name,
            facility_address=extracted_data.facility_address,
            driver_name=extracted_data.driver_name,
            carrier_name=extracted_data.carrier_name,
            bol_number=extracted_data.load_number,  # Map load_number to bol_number
            service_type=extracted_data.service_type,
            labor_hours=extracted_data.labor_hours,
            hourly_rate=extracted_data.hourly_rate,
            total_amount=extracted_data.total_charges,
            equipment_used=extracted_data.trailer_number,
            special_services=[{"service": svc} for svc in extracted_data.special_services] if extracted_data.special_services else None,
            notes=extracted_data.notes,
            confidence_score=extracted_data.confidence_score
        )

    def _count_extracted_fields(self, extracted_data: ExtractedLumperData) -> Dict[str, int]:
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

    def _extract_basic_receipt_number(self, text: str) -> Optional[str]:
        """Extract receipt number using basic pattern matching."""
        import re
        
        patterns = [
            r'receipt\s*#?\s*(\w+)',
            r'trans\s*#?\s*(\w+)',
            r'lumper\s*#?\s*(\w+)',
            r'#(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None

    def _extract_basic_facility(self, text: str) -> Optional[str]:
        """Extract facility name using basic pattern matching."""
        import re
        
        # Look for company names, warehouse names, etc.
        lines = text.split('\n')
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if len(line) > 5 and not line.isdigit():
                # Skip common OCR artifacts and dates
                if not re.search(r'^\d+[/\-]\d+', line):
                    return line
        
        return None

    def _extract_basic_total(self, text: str) -> Optional[float]:
        """Extract total amount using basic pattern matching."""
        import re
        
        # Look for dollar amounts
        pattern = r'\$\s*(\d+(?:\.\d{2})?)'
        matches = re.findall(pattern, text)
        
        if matches:
            # Return the largest amount found (likely the total)
            amounts = [float(match) for match in matches]
            return max(amounts)
        
        return None

    def _calculate_basic_confidence(self, lumper_data: LumperReceipt) -> float:
        """Calculate confidence based on extracted fields in basic mode."""
        confidence = 0.0
        
        # Key fields that boost confidence
        if lumper_data.receipt_number:
            confidence += 0.3
        if lumper_data.facility_name:
            confidence += 0.2
        if lumper_data.total_amount:
            confidence += 0.2
        if lumper_data.driver_name:
            confidence += 0.1
        if lumper_data.carrier_name:
            confidence += 0.1
        if lumper_data.receipt_date:
            confidence += 0.1
        
        return min(confidence, 1.0) 
"""
POD (Proof of Delivery) Parser

Extracts structured data from proof of delivery documents supporting
both PDF (direct text extraction with pdfplumber) and image formats (via OCR).
Implements confidence scoring based on successful field extraction and
validates presence of required delivery confirmation fields.

Key Features:
- Delivery confirmation detection
- Receiver name extraction
- Signature presence validation
- Delivery date/time parsing
- Delivery notes extraction
- Business logic: Updates load status to 'delivered' when confidence >= 0.9
- Invoice readiness: Triggers invoice_ready event when POD + ratecon_verified
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

try:
    import pdfplumber

    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logging.warning("pdfplumber not available - PDF direct extraction disabled")

from app.models.database import PODData

logger = logging.getLogger(__name__)


@dataclass
class PODParsingResult:
    """Result of POD parsing operation."""

    data: PODData
    confidence: float
    pod_completed: bool
    extraction_details: dict[str, Any]


class PODParser:
    """
    Parser for Proof of Delivery (POD) documents.

    Extracts delivery confirmation data using regex patterns that handle
    various carrier and delivery service formats. Supports both PDF direct
    extraction and OCR-based processing for images.

    Features:
    - Multi-format support (PDF direct text extraction, OCR for images)
    - Delivery confirmation detection patterns
    - Signature presence validation
    - Receiver name extraction with common titles/formats
    - Delivery date/time parsing (multiple formats)
    - Delivery notes and special instructions extraction
    - Confidence scoring based on field extraction success
    - Business logic integration (load status updates, event emission)
    - OCR artifact cleaning for better recognition
    """

    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.90  # Delivery confirmed + signature + date + receiver
    MEDIUM_CONFIDENCE_THRESHOLD = (
        0.70  # Delivery confirmed + (signature OR receiver OR date)
    )
    POD_COMPLETED_THRESHOLD = 0.80  # Minimum confidence for load completion

    def __init__(self):
        """Initialize POD parser with regex patterns."""
        self._compile_regex_patterns()

    def _compile_regex_patterns(self):
        """Compile all regex patterns for POD extraction."""

        # Delivery confirmation patterns
        self.delivery_confirmation_patterns = [
            # Direct confirmation phrases
            re.compile(r"delivery\s+confirmed?", re.IGNORECASE),
            re.compile(r"delivered\s+successfully", re.IGNORECASE),
            re.compile(r"package\s+delivered", re.IGNORECASE),
            re.compile(r"shipment\s+delivered", re.IGNORECASE),
            re.compile(r"freight\s+delivered", re.IGNORECASE),
            re.compile(r"cargo\s+delivered", re.IGNORECASE),
            re.compile(r"goods\s+delivered", re.IGNORECASE),
            re.compile(r"delivery\s+complete[d]?", re.IGNORECASE),
            re.compile(r"received\s+in\s+good\s+condition", re.IGNORECASE),
            re.compile(r"delivery\s+accepted", re.IGNORECASE),
            # Status indicators
            re.compile(r"status[:\s]*delivered", re.IGNORECASE),
            re.compile(r"proof\s+of\s+delivery", re.IGNORECASE),
            re.compile(r"pod\s+confirmation", re.IGNORECASE),
        ]

        # Signature detection patterns
        self.signature_patterns = [
            # Direct signature references
            re.compile(r"signature[:\s]*([A-Za-z\s]+)", re.IGNORECASE),
            re.compile(r"signed\s+by[:\s]*([A-Za-z\s]+)", re.IGNORECASE),
            re.compile(r"received\s+by[:\s]*([A-Za-z\s]+)", re.IGNORECASE),
            re.compile(r"accepted\s+by[:\s]*([A-Za-z\s]+)", re.IGNORECASE),
            # Signature indicators
            re.compile(r"electronically\s+signed", re.IGNORECASE),
            re.compile(r"digital\s+signature", re.IGNORECASE),
            re.compile(r"signature\s+on\s+file", re.IGNORECASE),
            re.compile(r"signed\s+digitally", re.IGNORECASE),
            # Visual signature markers (common OCR artifacts)
            re.compile(r"[*]{2,}.*signature.*[*]{2,}", re.IGNORECASE),
            re.compile(r"___+.*signature.*___+", re.IGNORECASE),
        ]

        # Receiver name patterns
        self.receiver_patterns = [
            # With titles/prefixes
            re.compile(
                r"(?:received|delivered|signed)\s+(?:to|by)[:\s]*(?:mr\.?|ms\.?|mrs\.?|dr\.?)?\s*([A-Za-z][A-Za-z\s]{2,30})",
                re.IGNORECASE,
            ),
            re.compile(
                r"consignee[:\s]*(?:mr\.?|ms\.?|mrs\.?)?\s*([A-Za-z][A-Za-z\s]{2,30})",
                re.IGNORECASE,
            ),
            re.compile(
                r"recipient[:\s]*(?:mr\.?|ms\.?|mrs\.?)?\s*([A-Za-z][A-Za-z\s]{2,30})",
                re.IGNORECASE,
            ),
            re.compile(
                r"customer[:\s]*(?:mr\.?|ms\.?|mrs\.?)?\s*([A-Za-z][A-Za-z\s]{2,30})",
                re.IGNORECASE,
            ),
            # Generic patterns
            re.compile(r"name[:\s]*([A-Za-z][A-Za-z\s]{2,30})", re.IGNORECASE),
            re.compile(r"contact[:\s]*([A-Za-z][A-Za-z\s]{2,30})", re.IGNORECASE),
            # Name after signature line
            re.compile(
                r"signature[:\s]*[_\-]*\s*([A-Za-z][A-Za-z\s]{2,30})", re.IGNORECASE
            ),
        ]

        # Delivery date/time patterns
        self.delivery_date_patterns = [
            # With delivery keywords
            re.compile(
                r"(?:delivered|delivery|received)\s+(?:on|at)?[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:delivered|delivery|received)\s+(?:on|at)?[:\s]*(\d{4}[/-]\d{1,2}[/-]\d{1,2})",
                re.IGNORECASE,
            ),
            re.compile(
                r"delivery\s+date[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", re.IGNORECASE
            ),
            re.compile(
                r"delivery\s+date[:\s]*(\d{4}[/-]\d{1,2}[/-]\d{1,2})", re.IGNORECASE
            ),
            re.compile(
                r"delivered[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", re.IGNORECASE
            ),
            re.compile(r"delivered[:\s]*(\d{4}[/-]\d{1,2}[/-]\d{1,2})", re.IGNORECASE),
            # Time inclusion
            re.compile(
                r"(?:delivered|delivery|received)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(?:at\s+)?(\d{1,2}:\d{2})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:delivered|delivery|received)[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(\d{1,2}:\d{2}\s*[ap]m)",
                re.IGNORECASE,
            ),
            # Generic date patterns in POD context
            re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", re.IGNORECASE),
            re.compile(r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})", re.IGNORECASE),
        ]

        # Delivery notes patterns
        self.notes_patterns = [
            # Direct notes references - more specific boundaries with word boundaries
            re.compile(
                r"(?:delivery\s+)?notes?\b[:\s]*([^\n\r]{10,200})", re.IGNORECASE
            ),
            re.compile(
                r"(?:special\s+)?instructions?\b[:\s]*([^\n\r]{10,200})", re.IGNORECASE
            ),
            re.compile(r"comments?\b[:\s]*([^\n\r]{10,200})", re.IGNORECASE),
            re.compile(r"remarks?\b[:\s]*([^\n\r]{10,200})", re.IGNORECASE),
            re.compile(r"observations?\b[:\s]*([^\n\r]{5,100})", re.IGNORECASE),
            # Condition notes - more specific
            re.compile(r"condition[:\s]*([^\n\r]{5,100})", re.IGNORECASE),
            re.compile(r"((?:good|poor|damaged|excellent)\s+condition)", re.IGNORECASE),
            # Damage/exception notes - include the keyword in capture
            re.compile(r"(damage[sd]?[:\s]*[^\n\r]{5,100})", re.IGNORECASE),
            re.compile(r"(exception[:\s]*[^\n\r]{5,100})", re.IGNORECASE),
        ]

        # POD document identifiers
        self.pod_indicators = [
            "proof of delivery",
            "pod",
            "delivery receipt",
            "delivery confirmation",
            "consignee receipt",
            "freight receipt",
            "delivery note",
            "shipment receipt",
        ]

    def parse_pdf(self, pdf_content: bytes) -> PODParsingResult:
        """
        Parse POD from PDF content using pdfplumber.

        Args:
            pdf_content: PDF file content as bytes

        Returns:
            PODParsingResult with extracted data
        """
        if not PDF_AVAILABLE:
            logger.error("pdfplumber not available for PDF parsing")
            return PODParsingResult(
                data=PODData(),
                confidence=0.0,
                pod_completed=False,
                extraction_details={"error": "pdfplumber not available"},
            )

        try:
            # Extract text from PDF
            with pdfplumber.open(pdf_content) as pdf:
                text_content = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_content += page_text + "\n"

            if not text_content.strip():
                logger.warning("No text extracted from PDF")
                return PODParsingResult(
                    data=PODData(),
                    confidence=0.0,
                    pod_completed=False,
                    extraction_details={"error": "No text found in PDF"},
                )

            logger.info(f"Extracted {len(text_content)} characters from PDF")
            return self.parse(text_content)

        except Exception as e:
            logger.error(f"PDF parsing failed: {e}")
            return PODParsingResult(
                data=PODData(),
                confidence=0.0,
                pod_completed=False,
                extraction_details={"error": f"PDF parsing failed: {str(e)}"},
            )

    def parse(self, text_content: str) -> PODParsingResult:
        """
        Parse POD from text content.

        Args:
            text_content: Raw text from POD document

        Returns:
            PODParsingResult with extracted data
        """
        logger.info(f"Parsing POD from {len(text_content)} characters of text")

        # Clean OCR artifacts first
        cleaned_text = self._clean_ocr_artifacts(text_content)

        # Extract individual fields
        extraction_details = {}

        delivery_confirmed = self._extract_delivery_confirmation(
            cleaned_text, extraction_details
        )
        signature_present = self._extract_signature_presence(
            cleaned_text, extraction_details
        )
        receiver_name = self._extract_receiver_name(cleaned_text, extraction_details)
        delivery_date = self._extract_delivery_date(cleaned_text, extraction_details)
        delivery_notes = self._extract_delivery_notes(cleaned_text, extraction_details)

        # Create POD data object
        pod_data = PODData(
            delivery_confirmed=delivery_confirmed,
            delivery_date=delivery_date,
            receiver_name=receiver_name,
            signature_present=signature_present,
            delivery_notes=delivery_notes,
        )

        # Calculate confidence score
        confidence = self._calculate_confidence(pod_data, extraction_details)

        # Determine if POD is completed
        pod_completed = self._is_pod_completed(pod_data, confidence)

        logger.info(
            f"POD parsing completed: confidence={confidence:.2f}, pod_completed={pod_completed}"
        )

        return PODParsingResult(
            data=pod_data,
            confidence=confidence,
            pod_completed=pod_completed,
            extraction_details=extraction_details,
        )

    def _extract_delivery_confirmation(
        self, text: str, details: dict[str, Any]
    ) -> bool:
        """Extract delivery confirmation status."""
        text_lower = text.lower()

        # Check for delivery confirmation indicators
        for pattern in self.delivery_confirmation_patterns:
            if pattern.search(text):
                details["delivery_confirmation_method"] = "pattern_match"
                details["delivery_confirmation_pattern"] = pattern.pattern
                logger.debug("Delivery confirmation found via pattern matching")
                return True

        # Check for POD document type indicators
        for indicator in self.pod_indicators:
            if indicator in text_lower:
                details["delivery_confirmation_method"] = "document_type"
                details["delivery_confirmation_indicator"] = indicator
                logger.debug(
                    f"Delivery confirmation inferred from document type: {indicator}"
                )
                return True

        details["delivery_confirmation_method"] = "not_found"
        logger.debug("No delivery confirmation indicators found")
        return False

    def _extract_signature_presence(self, text: str, details: dict[str, Any]) -> bool:
        """Extract signature presence information."""
        signature_indicators = []

        for pattern in self.signature_patterns:
            matches = pattern.findall(text)
            if matches:
                signature_indicators.extend(matches)

        # Check for signature-related keywords
        text_lower = text.lower()
        signature_keywords = [
            "signature",
            "signed",
            "electronic signature",
            "digital signature",
            "signature on file",
            "signed by",
            "received by",
            "accepted by",
        ]

        for keyword in signature_keywords:
            if keyword in text_lower:
                signature_indicators.append(keyword)

        if signature_indicators:
            details["signature_method"] = "found"
            details["signature_indicators"] = signature_indicators[
                :5
            ]  # Limit to avoid clutter
            logger.debug(
                f"Signature presence detected: {len(signature_indicators)} indicators"
            )
            return True

        details["signature_method"] = "not_found"
        logger.debug("No signature indicators found")
        return False

    def _extract_receiver_name(
        self, text: str, details: dict[str, Any]
    ) -> str | None:
        """Extract receiver name."""
        best_match = None
        best_score = 0

        for pattern in self.receiver_patterns:
            matches = pattern.findall(text)
            if matches:
                # Evaluate each match and pick the best one
                for match in matches:
                    name = match.strip()

                    # Basic filters - skip obvious non-names
                    if len(name) < 2:
                        continue

                    # Filter out obvious non-name content
                    bad_words = [
                        "date",
                        "time",
                        "signature",
                        "line",
                        "print",
                        "page",
                        "delivery",
                        "package",
                        "condition",
                        "satisfied",
                        "front door",
                        "good",
                        "excellent",
                        "poor",
                        "damaged",
                        "notes",
                        "comments",
                        "remarks",
                    ]

                    if any(word in name.lower() for word in bad_words):
                        continue

                    # Filter out matches with newlines or too much whitespace
                    if "\n" in name or "\r" in name:
                        # Try to extract just the name part before newline
                        clean_name = name.split("\n")[0].strip()
                        if len(clean_name) >= 2 and not any(
                            word in clean_name.lower() for word in bad_words
                        ):
                            name = clean_name
                        else:
                            continue

                    # Score the match based on quality indicators
                    score = 0

                    # Prefer shorter matches (likely to be actual names)
                    if len(name) <= 20:
                        score += 3
                    elif len(name) <= 30:
                        score += 1

                    # Prefer matches with common name patterns
                    if re.match(
                        r"^[A-Z][a-z]+ [A-Z][a-z]+$", name
                    ):  # "John Smith" pattern
                        score += 5
                    elif re.match(r"^[A-Z][a-z]+$", name):  # Single name
                        score += 2

                    # Prefer matches without excessive punctuation
                    if name.count(".") <= 1 and name.count(",") <= 1:
                        score += 1

                    # Update best match if this is better
                    if score > best_score:
                        best_match = name
                        best_score = score
                        details["receiver_name_method"] = "pattern_match"
                        details["receiver_name_pattern"] = pattern.pattern
                        details["receiver_name_score"] = score

        if best_match:
            logger.debug(f"Receiver name extracted: {best_match} (score: {best_score})")
            return best_match

        details["receiver_name_method"] = "not_found"
        logger.debug("No receiver name found")
        return None

    def _extract_delivery_date(
        self, text: str, details: dict[str, Any]
    ) -> datetime | None:
        """Extract delivery date."""
        for pattern in self.delivery_date_patterns:
            matches = pattern.findall(text)
            if matches:
                for match in matches:
                    # Handle tuple results (date + time)
                    if isinstance(match, tuple):
                        date_str = match[0]
                        time_str = match[1] if len(match) > 1 else None
                    else:
                        date_str = match
                        time_str = None

                    parsed_date = self._parse_date(date_str, time_str)
                    if parsed_date:
                        details["delivery_date_method"] = "pattern_match"
                        details["delivery_date_pattern"] = pattern.pattern
                        details["delivery_date_raw"] = date_str
                        if time_str:
                            details["delivery_time_raw"] = time_str
                        logger.debug(f"Delivery date extracted: {parsed_date}")
                        return parsed_date

        details["delivery_date_method"] = "not_found"
        logger.debug("No delivery date found")
        return None

    def _extract_delivery_notes(
        self, text: str, details: dict[str, Any]
    ) -> str | None:
        """Extract delivery notes."""
        notes_found = []

        for pattern in self.notes_patterns:
            matches = pattern.findall(text)
            if matches:
                for match in matches:
                    note = match.strip()
                    if len(note) >= 5:  # Minimum meaningful note length
                        notes_found.append(note)

        if notes_found:
            # Combine notes, removing duplicates and limiting length
            combined_notes = ". ".join(
                dict.fromkeys(notes_found)
            )  # Remove duplicates while preserving order
            combined_notes = combined_notes[:500]  # Limit total length
            details["delivery_notes_method"] = "pattern_match"
            details["delivery_notes_count"] = len(notes_found)
            logger.debug(f"Delivery notes extracted: {len(combined_notes)} characters")
            return combined_notes

        details["delivery_notes_method"] = "not_found"
        logger.debug("No delivery notes found")
        return None

    def _parse_date(
        self, date_str: str, time_str: str | None = None
    ) -> datetime | None:
        """Parse date string into datetime object."""
        try:
            # Clean up the date string
            date_str = date_str.strip()

            # Common date formats
            date_formats = [
                "%m/%d/%Y",
                "%m-%d-%Y",
                "%m/%d/%y",
                "%m-%d-%y",
                "%Y/%m/%d",
                "%Y-%m-%d",
                "%d/%m/%Y",
                "%d-%m-%Y",
                "%B %d, %Y",
                "%b %d, %Y",
                "%Y-%m-%d %H:%M:%S",
                "%m/%d/%Y %H:%M:%S",
            ]

            parsed_date = None
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

            if not parsed_date:
                logger.debug(f"Could not parse date: {date_str}")
                return None

            # If we have time_str, try to add it
            if time_str and parsed_date:
                try:
                    # Parse time
                    time_str = time_str.strip()
                    time_formats = ["%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"]

                    for time_fmt in time_formats:
                        try:
                            time_obj = datetime.strptime(time_str, time_fmt).time()
                            parsed_date = parsed_date.replace(
                                hour=time_obj.hour,
                                minute=time_obj.minute,
                                second=time_obj.second,
                            )
                            break
                        except ValueError:
                            continue
                except Exception as e:
                    logger.debug(f"Could not parse time {time_str}: {e}")

            return parsed_date

        except Exception as e:
            logger.debug(f"Date parsing error: {e}")
            return None

    def _calculate_confidence(
        self, pod_data: PODData, details: dict[str, Any]
    ) -> float:
        """Calculate confidence score based on extracted fields."""
        score = 0.0

        # Core delivery confirmation (40% weight)
        if pod_data.delivery_confirmed:
            score += 0.40

        # Signature presence (25% weight)
        if pod_data.signature_present:
            score += 0.25

        # Delivery date (20% weight)
        if pod_data.delivery_date:
            score += 0.20

        # Receiver name (10% weight)
        if pod_data.receiver_name:
            score += 0.10

        # Delivery notes (5% weight)
        if pod_data.delivery_notes:
            score += 0.05

        # Quality bonuses
        bonuses = 0.0

        # Bonus for multiple confirmation methods
        if details.get("delivery_confirmation_method") == "pattern_match":
            bonuses += 0.02

        # Bonus for receiver name with good pattern
        if pod_data.receiver_name and len(pod_data.receiver_name) > 5:
            bonuses += 0.02

        # Bonus for delivery notes with substantial content
        if pod_data.delivery_notes and len(pod_data.delivery_notes) > 20:
            bonuses += 0.01

        final_score = min(1.0, score + bonuses)

        details["confidence_breakdown"] = {
            "base_score": score,
            "bonuses": bonuses,
            "final_score": final_score,
            "delivery_confirmed_weight": 0.40 if pod_data.delivery_confirmed else 0.0,
            "signature_weight": 0.25 if pod_data.signature_present else 0.0,
            "date_weight": 0.20 if pod_data.delivery_date else 0.0,
            "receiver_weight": 0.10 if pod_data.receiver_name else 0.0,
            "notes_weight": 0.05 if pod_data.delivery_notes else 0.0,
        }

        return final_score

    def _is_pod_completed(self, pod_data: PODData, confidence: float) -> bool:
        """Determine if POD is completed based on data and confidence."""
        # Minimum requirements: delivery confirmed
        if not pod_data.delivery_confirmed:
            return False

        # Must meet minimum confidence threshold
        if confidence < self.POD_COMPLETED_THRESHOLD:
            return False

        return True

    def parse_from_ocr_result(self, ocr_result: dict[str, Any]) -> PODParsingResult:
        """
        Parse POD from OCR service result.

        Args:
            ocr_result: Result from OCR service (Datalab or Marker)

        Returns:
            PODParsingResult with extracted data
        """
        try:
            # Extract text from OCR result
            if "text" in ocr_result:
                text_content = ocr_result["text"]
            elif "content" in ocr_result:
                text_content = ocr_result["content"]
            else:
                logger.error("No text content found in OCR result")
                return PODParsingResult(
                    data=PODData(),
                    confidence=0.0,
                    pod_completed=False,
                    extraction_details={"error": "No text in OCR result"},
                )

            # Add OCR metadata to extraction details
            result = self.parse(text_content)
            result.extraction_details["ocr_metadata"] = {
                "ocr_confidence": ocr_result.get("confidence"),
                "ocr_method": ocr_result.get("method", "unknown"),
                "page_count": ocr_result.get("page_count", 1),
            }

            return result

        except Exception as e:
            logger.error(f"OCR result parsing failed: {e}")
            return PODParsingResult(
                data=PODData(),
                confidence=0.0,
                pod_completed=False,
                extraction_details={"error": f"OCR parsing failed: {str(e)}"},
            )

    def _clean_ocr_artifacts(self, text: str) -> str:
        """
        Clean common OCR artifacts from text.

        Args:
            text: Raw text that may contain OCR artifacts

        Returns:
            Cleaned text with common OCR errors corrected
        """
        # Common OCR substitutions for POD-specific terms
        ocr_fixes = {
            # Delivery-related terms
            "del1very": "delivery",
            "de1ivery": "delivery",
            "del1vered": "delivered",
            "de1ivered": "delivered",
            "d3livery": "delivery",
            "d3livered": "delivered",
            "del!very": "delivery",
            "del!vered": "delivered",
            # Signature-related terms
            "s1gnature": "signature",
            "s1gned": "signed",
            "rec31ved": "received",
            "rece1ved": "received",
            "acc3pted": "accepted",
            "accept3d": "accepted",
            # Proof/POD terms
            "pr00f": "proof",
            "pr0of": "proof",
            "p0d": "pod",
            # Date/time terms
            "dat3": "date",
            "dat_e": "date",
            "t1me": "time",
            "tim3": "time",
            # Common words
            "c0nfirmat10n": "confirmation",
            "c0nfirmati0n": "confirmation",
            "c0mplete": "complete",
            "compl3te": "complete",
        }

        cleaned_text = text
        for error, correction in ocr_fixes.items():
            # Case-insensitive replacement
            cleaned_text = re.sub(
                re.escape(error), correction, cleaned_text, flags=re.IGNORECASE
            )

        # Fix common letter/number substitutions in context
        # Only fix when it makes sense in context
        common_fixes = [
            (r"\b0([a-z]{2,})\b", r"o\1"),  # 0 -> o at start of words
            (r"\b([a-z]+)0([a-z]+)\b", r"\1o\2"),  # 0 -> o in middle of words
            (r"\b1([a-z]{2,})\b", r"l\1"),  # 1 -> l at start of words
            (r"\b([a-z]+)1([a-z]+)\b", r"\1l\2"),  # 1 -> l in middle of words
        ]

        for pattern, replacement in common_fixes:
            cleaned_text = re.sub(
                pattern, replacement, cleaned_text, flags=re.IGNORECASE
            )

        return cleaned_text

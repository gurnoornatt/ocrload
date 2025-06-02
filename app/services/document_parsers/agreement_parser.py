"""
Agreement Document Parser

Extracts structured data from driver agreement documents with signature detection.
Implements confidence scoring based on successful field extraction and
automatically sets agreement_signed flag to true when confidence >= 0.9.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.database import AgreementData

logger = logging.getLogger(__name__)


@dataclass
class AgreementParsingResult:
    """Result of Agreement parsing operation."""

    data: AgreementData
    confidence: float
    agreement_signed: bool
    extraction_details: dict[str, Any]


class AgreementParser:
    """
    Parser for driver agreement documents.

    Extracts key agreement information using regex patterns that handle
    various agreement formats and layouts. Implements signature detection
    and confidence scoring.

    Features:
    - Multi-format agreement support (driver contracts, terms of service, etc.)
    - Signature detection (digital and scanned formats)
    - Agreement type identification
    - Key terms extraction
    - Signing date detection
    - Confidence scoring based on field extraction success
    - Automatic agreement_signed flag setting (true when confidence >= 0.9)
    """

    # Minimum confidence for agreement_signed flag
    AGREEMENT_SIGNED_THRESHOLD = 0.90

    def __init__(self):
        """Initialize Agreement parser with regex patterns."""
        self._compile_regex_patterns()

    def _compile_regex_patterns(self):
        """Compile regex patterns for different agreement fields."""

        # Signature patterns (multiple to increase confidence)
        self.signature_patterns = [
            # Digital signatures with flexible spelling for OCR errors
            re.compile(
                r"(?:Digitally|D[0-9]g[0-9]tally|Electronic(?:ally)?)\s+(?:Signed|S[0-9]gn[e3]d)\s+(?:by|BY)[:]*\s*([A-Za-z0-9\s\.]+)",
                re.IGNORECASE,
            ),
            # Driver/Signature lines with OCR error tolerance - must have colon or specific signature context
            re.compile(
                r"(?:Driver|Dr[0-9]v[e3]r)\s+(?:Signature|S[0-9]gnatur[e3])[:](?:\s*([A-Za-z0-9_\s\.]*)|$)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:Signature|S[0-9]gnatur[e3])[:](?:\s*([A-Za-z0-9_\s\.]*)|$)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:Signed|S[0-9]gn[e3]d)\s+(?:by|BY)[:]*\s*([A-Za-z0-9_\s\.]+)",
                re.IGNORECASE,
            ),
            # Signature placeholders and marks - require at least 2 X's or 4+ underscores/dashes
            re.compile(r"X{2,}[_\-\s]*|X[_\-]{3,}|[_\-]{4,}", re.IGNORECASE),
            # Date signed patterns with OCR tolerance - including "Signed on:"
            re.compile(
                r"(?:Date|Dat[e3])\s+(?:Signed|S[0-9]gn[e3]d)[:]*\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:Signed|S[0-9]gn[e3]d)\s+(?:on|ON)[:]*\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                re.IGNORECASE,
            ),
            # Electronic signature confirmation with OCR tolerance
            re.compile(
                r"(?:I\s+agree|I\s+accept|I\s+acknowledge).*(?:terms|agreement|contract|conditions|responsibility)",
                re.IGNORECASE,
            ),
        ]

        # Agreement type patterns
        self.agreement_type_patterns = [
            # Common agreement types with OCR error tolerance
            re.compile(
                r"(?:Driver|Dr[0-9]v[e3]r|Independent\s+Contractor|Carrier)\s+(?:Agreement|Agr[e3][e3]m[e3]nt)",
                re.IGNORECASE,
            ),
            re.compile(r"Transportation\s+Agreement", re.IGNORECASE),
            re.compile(r"Freight\s+Broker\s+Agreement", re.IGNORECASE),
            re.compile(r"Freight\s+Agreement", re.IGNORECASE),
            re.compile(r"Load\s+Agreement", re.IGNORECASE),
            # Terms and Conditions - must be at start of line or have clear title context
            re.compile(
                r"(?:^|\n)\s*Terms\s+(?:and\s+Conditions|of\s+Service)",
                re.IGNORECASE | re.MULTILINE,
            ),
            re.compile(r"(?:Employment|Service)\s+Contract", re.IGNORECASE),
            re.compile(r"Non[\s-]?Disclosure\s+Agreement|NDA", re.IGNORECASE),
        ]

        # Key terms patterns (common agreement clauses)
        self.key_terms_patterns = [
            # Liability and insurance
            re.compile(
                r"(?:liability|insurance|coverage).*(?:amount|limit)[:]*\s*\$?([0-9,]+(?:\.[0-9]{2})?)",
                re.IGNORECASE,
            ),
            # Payment terms
            re.compile(
                r"(?:payment|compensation|rate).*(?:per|@).*(?:mile|load|hour)",
                re.IGNORECASE,
            ),
            # Equipment requirements
            re.compile(
                r"(?:equipment|vehicle|truck).*(?:requirement|specification)",
                re.IGNORECASE,
            ),
            # Termination clauses
            re.compile(
                r"(?:termination|cancel|terminate).*(?:notice|days|immediately)",
                re.IGNORECASE,
            ),
            # Compliance requirements
            re.compile(
                r"(?:compliance|regulation|DOT|FMCSA).*(?:requirement|standard)",
                re.IGNORECASE,
            ),
        ]

        # Signing date patterns
        self.signing_date_patterns = [
            # "Date Signed: 01/01/2025" or "Signed on: 01/01/2025"
            re.compile(
                r"(?:Date\s+Signed|Signed\s+on|Signature\s+Date)[:]*\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                re.IGNORECASE,
            ),
            # "Date: 01/01/2025" near signature context
            re.compile(
                r"(?:Date)[:]*\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", re.IGNORECASE
            ),
            # "Agreed on: 01/01/2025"
            re.compile(
                r"(?:Agreed\s+on|Agreement\s+Date)[:]*\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                re.IGNORECASE,
            ),
        ]

    def parse(self, ocr_text: str) -> AgreementParsingResult:
        """
        Parse Agreement document from OCR text.

        Args:
            ocr_text: Raw OCR text from agreement document

        Returns:
            AgreementParsingResult with extracted data, confidence, and signed status
        """
        logger.info(
            f"Parsing Agreement document from {len(ocr_text)} characters of OCR text"
        )

        # Extract individual fields
        extraction_details = {}

        signature_detected = self._detect_signature(ocr_text, extraction_details)
        signing_date = self._extract_signing_date(ocr_text, extraction_details)
        agreement_type = self._extract_agreement_type(ocr_text, extraction_details)
        key_terms = self._extract_key_terms(ocr_text, extraction_details)

        # Create Agreement data object
        agreement_data = AgreementData(
            signature_detected=signature_detected,
            signing_date=signing_date,
            agreement_type=agreement_type,
            key_terms=key_terms,
        )

        # Calculate confidence and signed status
        confidence = self._calculate_confidence(agreement_data, extraction_details)
        agreement_signed = confidence >= self.AGREEMENT_SIGNED_THRESHOLD

        result = AgreementParsingResult(
            data=agreement_data,
            confidence=confidence,
            agreement_signed=agreement_signed,
            extraction_details=extraction_details,
        )

        logger.info(
            f"Agreement parsing completed: confidence={confidence:.2f}, "
            f"signed={agreement_signed}, signature_detected={signature_detected}"
        )

        return result

    def _detect_signature(self, text: str, details: dict[str, Any]) -> bool:
        """Detect if a signature is present in the agreement text."""
        signature_indicators = 0
        signature_details = []

        for i, pattern in enumerate(self.signature_patterns):
            # For patterns 4 (signature_marks), we just need to check if pattern matches
            if i in [4]:  # signature_marks pattern
                if pattern.search(text):
                    signature_indicators += 1
                    pattern_type = self._get_signature_pattern_type(i)
                    signature_details.append(
                        {
                            "pattern": i,
                            "matches": [f"{pattern_type}_found"],
                            "pattern_type": pattern_type,
                        }
                    )
                    logger.debug(f"Signature pattern {i} matched: {pattern_type} found")
            else:
                matches = pattern.findall(text)
                if matches:
                    signature_indicators += 1
                    signature_details.append(
                        {
                            "pattern": i,
                            "matches": matches,
                            "pattern_type": self._get_signature_pattern_type(i),
                        }
                    )
                    logger.debug(f"Signature pattern {i} matched: {matches}")

        details["signature_indicators"] = signature_indicators
        details["signature_details"] = signature_details

        # Consider signature detected if we have multiple indicators or strong single indicator
        signature_detected = (
            signature_indicators >= 2
            or self._has_strong_signature_indicator(signature_details)
        )

        return signature_detected

    def _get_signature_pattern_type(self, pattern_index: int) -> str:
        """Get descriptive type for signature pattern."""
        pattern_types = [
            "digital_signature",  # 0
            "signature_line_driver",  # 1
            "signature_line",  # 2
            "signed_by",  # 3
            "signature_marks",  # 4
            "signed_date",  # 5
            "signed_on",  # 6
            "electronic_agreement",  # 7
        ]
        return (
            pattern_types[pattern_index]
            if pattern_index < len(pattern_types)
            else "unknown"
        )

    def _has_strong_signature_indicator(self, signature_details: list[dict]) -> bool:
        """Check if we have strong signature indicators."""
        for detail in signature_details:
            pattern_type = detail["pattern_type"]
            # Digital signatures, electronic agreements, signature marks, and dated signatures are strong indicators
            if pattern_type in [
                "digital_signature",
                "electronic_agreement",
                "signature_marks",
                "signed_date",
                "signed_on",
            ]:
                return True
            # Signature lines (even empty ones with colons) and lines with actual names are strong indicators
            if pattern_type in ["signature_line", "signature_line_driver"]:
                return True  # Any signature line with colon format is strong
            # Signed by patterns with actual names (not empty matches)
            if pattern_type == "signed_by":
                matches = detail["matches"]
                if any(len(str(match).strip()) > 3 for match in matches):
                    return True
        return False

    def _extract_signing_date(
        self, text: str, details: dict[str, Any]
    ) -> datetime | None:
        """Extract signing date from agreement text."""
        for i, pattern in enumerate(self.signing_date_patterns):
            match = pattern.search(text)
            if match:
                date_str = match.group(1)
                parsed_date = self._parse_date(date_str)
                if parsed_date:
                    details["signing_date_pattern"] = i
                    details["signing_date_raw"] = date_str
                    logger.debug(
                        f"Extracted signing date: {parsed_date} using pattern {i}"
                    )
                    return parsed_date

        details["signing_date_pattern"] = None
        return None

    def _extract_agreement_type(
        self, text: str, details: dict[str, Any]
    ) -> str | None:
        """Extract agreement type from text."""
        for i, pattern in enumerate(self.agreement_type_patterns):
            match = pattern.search(text)
            if match:
                agreement_type = match.group(0).strip()
                # Normalize the case to title case with proper handling of articles
                words = agreement_type.lower().split()
                titled_words = []
                for j, word in enumerate(words):
                    # Keep articles and prepositions lowercase unless they're the first word
                    if j > 0 and word in [
                        "and",
                        "of",
                        "the",
                        "in",
                        "on",
                        "at",
                        "to",
                        "for",
                        "with",
                    ]:
                        titled_words.append(word)
                    else:
                        titled_words.append(word.capitalize())
                agreement_type = " ".join(titled_words)
                details["agreement_type_pattern"] = i
                details["agreement_type_raw"] = agreement_type
                logger.debug(
                    f"Extracted agreement type: {agreement_type} using pattern {i}"
                )
                return agreement_type

        details["agreement_type_pattern"] = None
        return None

    def _extract_key_terms(
        self, text: str, details: dict[str, Any]
    ) -> list[str] | None:
        """Extract key terms and clauses from agreement text."""
        key_terms = []

        for _i, pattern in enumerate(self.key_terms_patterns):
            matches = pattern.findall(text)
            if matches:
                # Clean up and add matches
                for match in matches[:3]:  # Limit to prevent overwhelming data
                    if isinstance(match, tuple):
                        match = " ".join(match)
                    cleaned_match = re.sub(r"\s+", " ", str(match).strip())
                    if len(cleaned_match) > 10:  # Only meaningful terms
                        key_terms.append(cleaned_match)

        details["key_terms_found"] = len(key_terms)

        return key_terms if key_terms else None

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse date string into datetime object."""
        # Common date formats from OCR
        date_formats = [
            "%m/%d/%Y",  # 01/01/2025
            "%m-%d-%Y",  # 01-01-2025
            "%m/%d/%y",  # 01/01/25
            "%m-%d-%y",  # 01-01-25
            "%Y/%m/%d",  # 2025/01/01
            "%Y-%m-%d",  # 2025-01-01
        ]

        for fmt in date_formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # Handle 2-digit years
                if parsed.year < 1950:
                    parsed = parsed.replace(year=parsed.year + 100)
                return parsed
            except ValueError:
                continue

        return None

    def _calculate_confidence(
        self, agreement_data: AgreementData, details: dict[str, Any]
    ) -> float:
        """
        Calculate confidence score based on extracted fields.

        Scoring logic:
        - Signature detected + Agreement type + Date = 0.95 (high confidence)
        - Signature detected + Agreement type = 0.85 (good confidence)
        - Signature detected + Terms = 0.75 (medium confidence)
        - Signature detected only = 0.70 (acceptable confidence)
        - Agreement type + Terms (no signature) = 0.60 (low confidence)
        - Some terms found = 0.40 (very low confidence)
        - Nothing meaningful = 0.20 (minimal confidence)
        """
        score = 0.0

        # Check which fields were successfully extracted
        has_signature = agreement_data.signature_detected
        has_type = agreement_data.agreement_type is not None
        has_date = agreement_data.signing_date is not None
        has_terms = (
            agreement_data.key_terms is not None and len(agreement_data.key_terms) > 0
        )

        # Apply confidence rules
        if has_signature and has_type and has_date:
            # High confidence: signature + type + date
            score = 0.95
        elif has_signature and has_type:
            # Good confidence: signature + type
            score = 0.85
        elif has_signature and has_terms:
            # Medium confidence: signature + terms
            score = 0.75
        elif has_signature:
            # Acceptable confidence: signature only
            score = 0.70
        elif has_type and has_terms:
            # Low confidence: type + terms (no signature)
            score = 0.60
        elif has_terms:
            # Very low confidence: some terms found
            score = 0.40
        else:
            # Minimal confidence: nothing meaningful
            score = 0.20

        # Boost score based on signature quality
        if has_signature:
            signature_indicators = details.get("signature_indicators", 0)
            if signature_indicators >= 6:
                # Exceptionally strong signature evidence - very high boost
                score = min(1.0, score + 0.25)
            elif signature_indicators >= 4:
                # Very strong signature evidence - maximum boost
                score = min(1.0, score + 0.15)
            elif signature_indicators >= 3:
                # Strong signature evidence - good boost
                score = min(1.0, score + 0.10)
            elif signature_indicators >= 2:
                # Multiple signatures - moderate boost
                score = min(1.0, score + 0.05)

        # Ensure score is within bounds
        return min(1.0, max(0.0, score))

    def parse_from_ocr_result(
        self, ocr_result: dict[str, Any]
    ) -> AgreementParsingResult:
        """
        Parse Agreement from OCR service result.

        Args:
            ocr_result: Result from OCR service (Datalab/Marker)

        Returns:
            AgreementParsingResult with extracted agreement data
        """
        # Extract text from OCR result
        full_text = ocr_result.get("full_text", "")

        # Also try to get text from pages if available
        pages = ocr_result.get("pages", [])
        if not full_text and pages:
            page_texts = [page.get("text", "") for page in pages]
            full_text = "\n\n".join(page_texts)

        if not full_text:
            logger.warning("No text found in OCR result")
            return AgreementParsingResult(
                data=AgreementData(),
                confidence=0.0,
                agreement_signed=False,
                extraction_details={"error": "No text found in OCR result"},
            )

        return self.parse(full_text)


# Global Agreement parser instance
agreement_parser = AgreementParser()

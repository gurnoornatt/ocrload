"""
CDL Document Parser

Extracts structured data from Commercial Driver's License (CDL) documents
using regex patterns that handle various state formats. Implements confidence
scoring based on successful field extraction and validates expiration dates.
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

from app.models.database import CDLData


logger = logging.getLogger(__name__)


@dataclass
class ParsingResult:
    """Result of CDL parsing operation."""
    data: CDLData
    confidence: float
    cdl_verified: bool
    extraction_details: Dict[str, Any]


class CDLParser:
    """
    Parser for Commercial Driver's License documents.
    
    Extracts key information using regex patterns that handle various
    state formats and CDL layouts. Implements confidence scoring based
    on successful field extraction.
    
    Features:
    - Multi-state CDL format support
    - Robust regex patterns for OCR text variations
    - Confidence scoring based on field extraction success
    - Expiration date validation (>30 days from today)
    - Address and license class extraction
    - Error handling and logging
    """
    
    # Minimum days until expiration for verification
    MIN_EXPIRATION_DAYS = 30
    
    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.95  # Name + expiry found
    MEDIUM_CONFIDENCE_THRESHOLD = 0.70  # Some fields found
    
    def __init__(self):
        """Initialize CDL parser with regex patterns."""
        self._compile_regex_patterns()
    
    def _compile_regex_patterns(self):
        """Compile regex patterns for different CDL fields."""
        
        # Driver name patterns - handle various formats
        self.name_patterns = [
            # "NAME: John Smith" or "Name: JOHN SMITH"
            re.compile(r'(?:NAME|Name):\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})', re.IGNORECASE),
            # "SMITH, JOHN" format
            re.compile(r'([A-Z][A-Z]+,\s*[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)', re.IGNORECASE),
            # "First: John Last: Smith" format
            re.compile(r'(?:First|FIRST):\s*([A-Z][a-zA-Z]+).*?(?:Last|LAST):\s*([A-Z][a-zA-Z]+)', re.IGNORECASE | re.DOTALL),
            # "John Smith" on its own line (common in many states) - more restrictive
            re.compile(r'^([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)$', re.MULTILINE),
        ]
        
        # License number patterns - various state formats
        self.license_patterns = [
            # "DL: 123456789" or "LICENSE: A123456789"
            re.compile(r'(?:DL|LICENSE|LIC|CDL)[:# ]*([A-Z0-9]{7,15})', re.IGNORECASE),
            # "123456789" - standalone number (8-12 digits)
            re.compile(r'\b([A-Z0-9]{8,12})\b'),
            # State-specific patterns
            re.compile(r'(?:CA|TX|FL|NY|IL|PA|OH|GA|NC|MI)\s*([A-Z0-9]{7,12})', re.IGNORECASE),
        ]
        
        # Expiration date patterns - multiple formats
        self.expiration_patterns = [
            # "EXP: 12/25/2025" or "EXPIRES: 12-25-2025" or "EXPIRATION DATE: 12/25/2025"
            re.compile(r'(?:EXP|EXPIRES|EXPIRATION)\s*(?:DATE)?[:]*\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', re.IGNORECASE),
            # "DOB: MM/DD/YYYY EXP: MM/DD/YYYY" - capture the second date
            re.compile(r'DOB:\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*?(?:EXP|EXPIRES)[:]*\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', re.IGNORECASE),
            # "12/25/2025" standalone date - but must be in future and reasonable
            re.compile(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b'),
        ]
        
        # License class patterns
        self.class_patterns = [
            # "CLASS: A" or "CDL CLASS: B"
            re.compile(r'(?:CLASS|CDL CLASS)[:]*\s*([A-C])', re.IGNORECASE),
            # "A CDL" or "CLASS A"
            re.compile(r'(?:CLASS\s*)?([A-C])\s*(?:CDL|CLASS)', re.IGNORECASE),
        ]
        
        # Address patterns - various formats
        self.address_patterns = [
            # "ADDRESS: 123 Main St, City, ST 12345"
            re.compile(r'(?:ADDRESS|ADDR)[:]*\s*([0-9]+\s+[A-Za-z\s]+(?:ST|STREET|AVE|AVENUE|RD|ROAD|BLVD|BOULEVARD|DR|DRIVE|LN|LANE)[^0-9]*?[A-Z]{2}\s+\d{5})', re.IGNORECASE),
            # Multi-line address format - more specific
            re.compile(r'([0-9]+\s+[A-Za-z][A-Za-z\s]+(?:ST|STREET|AVE|AVENUE|RD|ROAD|BLVD|BOULEVARD|DR|DRIVE|LN|LANE))[^0-9]*?([A-Z]{2}\s+\d{5})', re.IGNORECASE | re.DOTALL),
            # Simple format: "123 Main St" - but exclude license numbers
            re.compile(r'([0-9]{1,5}\s+[A-Za-z][A-Za-z\s]+(?:ST|STREET|AVE|AVENUE|RD|ROAD|BLVD|BOULEVARD|DR|DRIVE|LN|LANE))(?![0-9])', re.IGNORECASE),
        ]
        
        # State patterns
        self.state_patterns = [
            # "STATE: CA" or "ST: CA"
            re.compile(r'(?:STATE|ST)[:]*\s*([A-Z]{2})', re.IGNORECASE),
            # State abbreviation in address
            re.compile(r'\b([A-Z]{2})\s+\d{5}'),
        ]
    
    def parse(self, ocr_text: str) -> ParsingResult:
        """
        Parse CDL document from OCR text.
        
        Args:
            ocr_text: Raw OCR text from CDL document
            
        Returns:
            ParsingResult with extracted data, confidence, and verification status
        """
        logger.info(f"Parsing CDL document from {len(ocr_text)} characters of OCR text")
        
        # Extract individual fields
        extraction_details = {}
        
        name = self._extract_name(ocr_text, extraction_details)
        license_number = self._extract_license_number(ocr_text, extraction_details)
        expiration_date = self._extract_expiration_date(ocr_text, extraction_details)
        license_class = self._extract_license_class(ocr_text, extraction_details)
        address = self._extract_address(ocr_text, extraction_details)
        state = self._extract_state(ocr_text, extraction_details)
        
        # Create CDL data object
        cdl_data = CDLData(
            driver_name=name,
            license_number=license_number,
            expiration_date=expiration_date,
            license_class=license_class,
            address=address,
            state=state
        )
        
        # Calculate confidence and verification status
        confidence = self._calculate_confidence(cdl_data, extraction_details)
        cdl_verified = self._is_cdl_verified(cdl_data)
        
        result = ParsingResult(
            data=cdl_data,
            confidence=confidence,
            cdl_verified=cdl_verified,
            extraction_details=extraction_details
        )
        
        logger.info(
            f"CDL parsing completed: confidence={confidence:.2f}, "
            f"verified={cdl_verified}, fields_found={len([f for f in [name, license_number, expiration_date, license_class, address, state] if f])}"
        )
        
        return result
    
    def _extract_name(self, text: str, details: Dict[str, Any]) -> Optional[str]:
        """Extract driver name from CDL text."""
        for i, pattern in enumerate(self.name_patterns):
            match = pattern.search(text)
            if match:
                if len(match.groups()) > 1:
                    # Handle "First: John Last: Smith" format
                    name = f"{match.group(1)} {match.group(2)}"
                else:
                    name = match.group(1).strip()
                
                # Clean up the name
                name = self._clean_name(name)
                if name and len(name) > 3:  # Minimum reasonable name length
                    details['name_pattern'] = i
                    details['name_raw'] = match.group(0)
                    logger.debug(f"Extracted name: {name} using pattern {i}")
                    return name
        
        details['name_pattern'] = None
        return None
    
    def _extract_license_number(self, text: str, details: Dict[str, Any]) -> Optional[str]:
        """Extract license number from CDL text."""
        for i, pattern in enumerate(self.license_patterns):
            matches = pattern.findall(text)
            for match in matches:
                # Filter out obvious non-license numbers
                if self._is_valid_license_number(match):
                    details['license_pattern'] = i
                    details['license_raw'] = match
                    logger.debug(f"Extracted license number: {match} using pattern {i}")
                    return match.upper()
        
        details['license_pattern'] = None
        return None
    
    def _extract_expiration_date(self, text: str, details: Dict[str, Any]) -> Optional[datetime]:
        """Extract expiration date from CDL text."""
        for i, pattern in enumerate(self.expiration_patterns):
            match = pattern.search(text)
            if match:
                date_str = match.group(1)
                parsed_date = self._parse_date(date_str)
                if parsed_date and parsed_date > datetime.now():  # Must be in the future
                    details['expiration_pattern'] = i
                    details['expiration_raw'] = date_str
                    logger.debug(f"Extracted expiration date: {parsed_date} using pattern {i}")
                    return parsed_date
        
        details['expiration_pattern'] = None
        return None
    
    def _extract_license_class(self, text: str, details: Dict[str, Any]) -> Optional[str]:
        """Extract license class from CDL text."""
        for i, pattern in enumerate(self.class_patterns):
            match = pattern.search(text)
            if match:
                license_class = match.group(1).upper()
                if license_class in ['A', 'B', 'C']:
                    details['class_pattern'] = i
                    details['class_raw'] = match.group(0)
                    logger.debug(f"Extracted license class: {license_class} using pattern {i}")
                    return license_class
        
        details['class_pattern'] = None
        return None
    
    def _extract_address(self, text: str, details: Dict[str, Any]) -> Optional[str]:
        """Extract address from CDL text."""
        for i, pattern in enumerate(self.address_patterns):
            match = pattern.search(text)
            if match:
                if len(match.groups()) > 1:
                    # Multi-part address
                    address = f"{match.group(1).strip()} {match.group(2).strip()}"
                else:
                    address = match.group(1).strip()
                
                # Clean up the address
                address = self._clean_address(address)
                if address and len(address) > 10:  # Minimum reasonable address length
                    details['address_pattern'] = i
                    details['address_raw'] = match.group(0)
                    logger.debug(f"Extracted address: {address} using pattern {i}")
                    return address
        
        details['address_pattern'] = None
        return None
    
    def _extract_state(self, text: str, details: Dict[str, Any]) -> Optional[str]:
        """Extract state from CDL text."""
        for i, pattern in enumerate(self.state_patterns):
            match = pattern.search(text)
            if match:
                state = match.group(1).upper()
                if len(state) == 2 and state.isalpha():
                    details['state_pattern'] = i
                    details['state_raw'] = match.group(0)
                    logger.debug(f"Extracted state: {state} using pattern {i}")
                    return state
        
        details['state_pattern'] = None
        return None
    
    def _clean_name(self, name: str) -> str:
        """Clean and normalize extracted name."""
        # Remove extra whitespace and clean up
        name = re.sub(r'\s+', ' ', name.strip())
        
        # Filter out obvious non-names
        name_words = name.split()
        
        # Remove words that look like license numbers, dates, or other data
        cleaned_words = []
        for word in name_words:
            # Skip words that are mostly numbers or contain common non-name patterns
            if (re.match(r'^[A-Z0-9]{7,}$', word) or  # License number pattern
                re.match(r'\d+[/-]\d+', word) or       # Date pattern
                word.upper() in ['LICENSE', 'CDL', 'EXP', 'EXPIRES', 'CLASS']):
                continue
            cleaned_words.append(word)
        
        if not cleaned_words:
            return name  # Return original if we filtered everything
        
        name = ' '.join(cleaned_words)
        
        # Handle "LAST, FIRST" format
        if ',' in name:
            parts = name.split(',')
            if len(parts) == 2:
                last, first = parts[0].strip(), parts[1].strip()
                name = f"{first} {last}"
        
        # Title case
        name = name.title()
        
        return name
    
    def _clean_address(self, address: str) -> str:
        """Clean and normalize extracted address."""
        # Remove extra whitespace and line breaks
        address = re.sub(r'\s+', ' ', address.strip())
        address = re.sub(r'[\n\r]+', ' ', address)
        
        return address
    
    def _is_valid_license_number(self, license_num: str) -> bool:
        """Validate if extracted text looks like a license number."""
        # Filter out obvious non-license patterns
        if not license_num:
            return False
        
        # Must be 7-15 characters
        if len(license_num) < 7 or len(license_num) > 15:
            return False
        
        # Should contain some digits
        if not any(c.isdigit() for c in license_num):
            return False
        
        # Common false positives to exclude
        false_positives = {
            'COMMERCIAL', 'DRIVER', 'LICENSE', 'EXPIRES', 'ADDRESS',
            'BIRTHDAY', 'WEIGHT', 'HEIGHT', 'EYES', 'HAIR'
        }
        
        if license_num.upper() in false_positives:
            return False
        
        return True
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string into datetime object."""
        # Common date formats from OCR
        date_formats = [
            '%m/%d/%Y',    # 12/25/2025
            '%m-%d-%Y',    # 12-25-2025
            '%m/%d/%y',    # 12/25/25
            '%m-%d-%y',    # 12-25-25
            '%Y/%m/%d',    # 2025/12/25
            '%Y-%m-%d',    # 2025-12-25
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
    
    def _calculate_confidence(self, cdl_data: CDLData, details: Dict[str, Any]) -> float:
        """
        Calculate confidence score based on extracted fields.
        
        Scoring logic:
        - Name + Expiration Date = 0.95 (high confidence)
        - Name OR Expiration Date + other fields = 0.70 (medium confidence)
        - Some fields found = 0.40-0.69 (low confidence)
        - No critical fields = 0.20 (very low confidence)
        """
        score = 0.0
        field_weights = {
            'name': 0.35,
            'expiration': 0.35,
            'license_number': 0.15,
            'license_class': 0.10,
            'address': 0.03,
            'state': 0.02
        }
        
        # Check which fields were successfully extracted
        extracted_fields = {
            'name': cdl_data.driver_name is not None,
            'expiration': cdl_data.expiration_date is not None,
            'license_number': cdl_data.license_number is not None,
            'license_class': cdl_data.license_class is not None,
            'address': cdl_data.address is not None,
            'state': cdl_data.state is not None
        }
        
        # Calculate base score
        for field, extracted in extracted_fields.items():
            if extracted:
                score += field_weights[field]
        
        # Apply confidence rules
        has_name_and_expiry = extracted_fields['name'] and extracted_fields['expiration']
        has_name_or_expiry = extracted_fields['name'] or extracted_fields['expiration']
        
        if has_name_and_expiry:
            # High confidence: critical fields present
            score = max(score, self.HIGH_CONFIDENCE_THRESHOLD)
        elif has_name_or_expiry and sum(extracted_fields.values()) >= 2:
            # Medium confidence: one critical field + others
            score = max(score, self.MEDIUM_CONFIDENCE_THRESHOLD)
        
        # Ensure score is within bounds
        return min(1.0, max(0.0, score))
    
    def _is_cdl_verified(self, cdl_data: CDLData) -> bool:
        """
        Determine if CDL is verified based on data quality and expiration.
        
        Requirements for verification:
        - Must have driver name and expiration date
        - Expiration date must be > 30 days from today
        """
        if not cdl_data.driver_name or not cdl_data.expiration_date:
            return False
        
        # Check expiration date
        days_until_expiry = (cdl_data.expiration_date - datetime.now()).days
        if days_until_expiry < self.MIN_EXPIRATION_DAYS:
            logger.warning(f"CDL expires in {days_until_expiry} days, less than required {self.MIN_EXPIRATION_DAYS}")
            return False
        
        return True
    
    def parse_from_ocr_result(self, ocr_result: Dict[str, Any]) -> ParsingResult:
        """
        Parse CDL from OCR service result.
        
        Args:
            ocr_result: Result from OCR service (Datalab/Marker)
            
        Returns:
            ParsingResult with extracted CDL data
        """
        # Extract text from OCR result
        full_text = ocr_result.get('full_text', '')
        
        # Also try to get text from pages if available
        pages = ocr_result.get('pages', [])
        if not full_text and pages:
            page_texts = [page.get('text', '') for page in pages]
            full_text = '\n\n'.join(page_texts)
        
        if not full_text:
            logger.warning("No text found in OCR result")
            return ParsingResult(
                data=CDLData(),
                confidence=0.0,
                cdl_verified=False,
                extraction_details={'error': 'No text found in OCR result'}
            )
        
        return self.parse(full_text)


# Global CDL parser instance
cdl_parser = CDLParser() 
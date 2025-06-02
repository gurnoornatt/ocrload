"""
Freight Invoice Document Parser

Extracts structured data from freight invoices including invoice numbers,
dates, billing information, line items, charges, and payment terms.
Implements confidence scoring and handles various invoice formats.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple, Union

from app.models.database import Invoice

logger = logging.getLogger(__name__)


@dataclass
class ParsingResult:
    """Result of invoice parsing operation."""

    data: Invoice
    confidence: float
    extraction_details: dict[str, Any]


@dataclass
class LineItem:
    """Represents a line item from an invoice."""
    
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total: Optional[float] = None
    item_code: Optional[str] = None


class InvoiceParser:
    """
    Parser for freight invoice documents.

    Extracts comprehensive invoice information using regex patterns that handle
    various freight invoice formats from different carriers and shippers.

    Features:
    - Multi-format freight invoice support
    - Robust regex patterns for OCR text variations
    - Line item extraction with nested charge details
    - Confidence scoring based on field extraction success
    - Date validation and amount parsing
    - Support for accessorial charges and fuel surcharges
    - Error handling and detailed logging
    """

    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.85  # Invoice number + total + vendor found
    MEDIUM_CONFIDENCE_THRESHOLD = 0.65  # Some key fields found
    LOW_CONFIDENCE_THRESHOLD = 0.40  # Minimal fields found

    def __init__(self):
        """Initialize invoice parser with regex patterns."""
        self._compile_regex_patterns()

    def _compile_regex_patterns(self):
        """Compile regex patterns for different invoice fields."""

        # Invoice number patterns - various formats
        self.invoice_number_patterns = [
            # "INVOICE #: 12345" or "Invoice Number: INV-2024-001"
            re.compile(
                r"(?:INVOICE|Invoice)\s*(?:#|Number|No\.?)[:]*\s*([A-Z0-9\-_]{3,20})",
                re.IGNORECASE,
            ),
            # "INV: 12345" or "INV# 12345"
            re.compile(r"INV[#:]?\s*([A-Z0-9\-_]{3,20})", re.IGNORECASE),
            # Standalone invoice pattern "Invoice 12345"
            re.compile(r"Invoice\s+([A-Z0-9\-_]{3,20})", re.IGNORECASE),
            # Bill number patterns
            re.compile(
                r"(?:BILL|Bill)\s*(?:#|Number|No\.?)[:]*\s*([A-Z0-9\-_]{3,20})",
                re.IGNORECASE,
            ),
        ]

        # Date patterns - invoice date, due date
        self.date_patterns = [
            # "Invoice Date: 12/25/2024" or "Date: 12-25-2024"
            re.compile(
                r"(?:Invoice\s+Date|Date|Billing\s+Date|Issue\s+Date)[:]*\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                re.IGNORECASE,
            ),
            # "Due Date: 01/15/2025"
            re.compile(
                r"(?:Due\s+Date|Payment\s+Due|Due)[:]*\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
                re.IGNORECASE,
            ),
            # ISO format dates
            re.compile(
                r"(?:Date|Due)[:]*\s*(\d{4}-\d{1,2}-\d{1,2})",
                re.IGNORECASE,
            ),
        ]

        # Vendor/Shipper patterns
        self.vendor_patterns = [
            # "Bill To:" or "Vendor:" followed by company name
            re.compile(
                r"(?:Bill\s+To|Vendor|From|Shipper|Carrier)[:]*\s*\n?\s*([A-Z][A-Za-z\s&.,'-]{2,50})",
                re.IGNORECASE | re.MULTILINE,
            ),
            # Company name patterns (capital letters, common suffixes)
            re.compile(
                r"([A-Z][A-Za-z\s&.,'-]*(?:LLC|Inc|Corp|Co|Company|Industries|Logistics|Transportation|Freight))",
                re.IGNORECASE,
            ),
        ]

        # Customer patterns
        self.customer_patterns = [
            # "Ship To:" or "Customer:" followed by company name
            re.compile(
                r"(?:Ship\s+To|Customer|Consignee|Deliver\s+To)[:]*\s*\n?\s*([A-Z][A-Za-z\s&.,'-]{2,50})",
                re.IGNORECASE | re.MULTILINE,
            ),
        ]

        # Address patterns - more comprehensive
        self.address_patterns = [
            # Full address with street, city, state, zip
            re.compile(
                r"([0-9]+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Way|Place|Pl)[^0-9]*?[A-Za-z\s]+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)",
                re.IGNORECASE | re.DOTALL,
            ),
            # Street address only
            re.compile(
                r"([0-9]+\s+[A-Za-z][A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Way|Place|Pl))",
                re.IGNORECASE,
            ),
        ]

        # Amount patterns - various currency formats
        self.amount_patterns = [
            # "Total: $1,234.56" or "Amount Due: $1234.56"
            re.compile(
                r"(?:Total|Amount\s+Due|Balance|Grand\s+Total|Invoice\s+Total)[:]*\s*\$?\s*([\d,]+\.?\d{0,2})",
                re.IGNORECASE,
            ),
            # Subtotal patterns
            re.compile(
                r"(?:Subtotal|Sub\s+Total)[:]*\s*\$?\s*([\d,]+\.?\d{0,2})",
                re.IGNORECASE,
            ),
            # Tax patterns
            re.compile(
                r"(?:Tax|Sales\s+Tax|VAT)[:]*\s*\$?\s*([\d,]+\.?\d{0,2})",
                re.IGNORECASE,
            ),
        ]

        # Payment terms patterns
        self.payment_terms_patterns = [
            # "Terms: Net 30" or "Payment Terms: COD"
            re.compile(
                r"(?:Terms|Payment\s+Terms|Net\s+Terms)[:]*\s*([A-Za-z0-9\s]{3,20})",
                re.IGNORECASE,
            ),
            # Common payment terms
            re.compile(
                r"\b(Net\s+\d+|COD|Cash\s+on\s+Delivery|Due\s+on\s+Receipt|Prepaid)\b",
                re.IGNORECASE,
            ),
        ]

        # Line item patterns - freight charges, accessorials, etc.
        self.line_item_patterns = [
            # "Description: Freight Charges   Qty: 1   Rate: $2500.00   Total: $2500.00"
            re.compile(
                r"([A-Za-z\s\-]+(?:Freight|Charge|Fee|Surcharge|Accessorial)[A-Za-z\s\-]*)\s+.*?\$?\s*([\d,]+\.?\d{0,2})",
                re.IGNORECASE,
            ),
            # Fuel surcharge patterns
            re.compile(
                r"(Fuel\s+Surcharge|FSC).*?\$?\s*([\d,]+\.?\d{0,2})",
                re.IGNORECASE,
            ),
            # Detention patterns
            re.compile(
                r"(Detention|Delay|Wait\s+Time).*?\$?\s*([\d,]+\.?\d{0,2})",
                re.IGNORECASE,
            ),
            # Lumper charges
            re.compile(
                r"(Lumper|Loading|Unloading).*?\$?\s*([\d,]+\.?\d{0,2})",
                re.IGNORECASE,
            ),
        ]

        # BOL/PRO number patterns
        self.bol_patterns = [
            re.compile(r"(?:BOL|B/L|Bill\s+of\s+Lading)[:]*\s*([A-Z0-9\-_]{3,20})", re.IGNORECASE),
            re.compile(r"(?:PRO|Pro\s+Number)[:]*\s*([A-Z0-9\-_]{3,20})", re.IGNORECASE),
        ]

    def parse(self, ocr_text: str, document_id: str) -> ParsingResult:
        """
        Parse freight invoice from OCR text.

        Args:
            ocr_text: Raw OCR text from invoice document
            document_id: UUID of the document being parsed

        Returns:
            ParsingResult with extracted data and confidence score
        """
        logger.info(f"Parsing freight invoice from {len(ocr_text)} characters of OCR text")

        # Extract individual fields
        extraction_details = {}

        invoice_number = self._extract_invoice_number(ocr_text, extraction_details)
        invoice_date = self._extract_invoice_date(ocr_text, extraction_details)
        due_date = self._extract_due_date(ocr_text, extraction_details)
        vendor_name = self._extract_vendor_name(ocr_text, extraction_details)
        vendor_address = self._extract_vendor_address(ocr_text, extraction_details)
        customer_name = self._extract_customer_name(ocr_text, extraction_details)
        customer_address = self._extract_customer_address(ocr_text, extraction_details)
        subtotal = self._extract_subtotal(ocr_text, extraction_details)
        tax_amount = self._extract_tax_amount(ocr_text, extraction_details)
        total_amount = self._extract_total_amount(ocr_text, extraction_details)
        payment_terms = self._extract_payment_terms(ocr_text, extraction_details)
        line_items = self._extract_line_items(ocr_text, extraction_details)

        # Create invoice data object
        invoice_data = Invoice(
            document_id=document_id,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            due_date=due_date,
            vendor_name=vendor_name,
            vendor_address=vendor_address,
            customer_name=customer_name,
            customer_address=customer_address,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            payment_terms=payment_terms,
            line_items=line_items,
        )

        # Calculate confidence
        confidence = self._calculate_confidence(invoice_data, extraction_details)

        result = ParsingResult(
            data=invoice_data,
            confidence=confidence,
            extraction_details=extraction_details,
        )

        logger.info(
            f"Invoice parsing completed: confidence={confidence:.2f}, "
            f"invoice_number={invoice_number}, total_amount={total_amount}"
        )

        return result

    def _extract_invoice_number(self, text: str, details: dict[str, Any]) -> Optional[str]:
        """Extract invoice number from text."""
        for i, pattern in enumerate(self.invoice_number_patterns):
            match = pattern.search(text)
            if match:
                invoice_number = match.group(1).strip()
                if self._is_valid_invoice_number(invoice_number):
                    details["invoice_number"] = {
                        "value": invoice_number,
                        "pattern_index": i,
                        "confidence": 0.9,
                    }
                    return invoice_number
        
        details["invoice_number"] = {"value": None, "confidence": 0.0}
        return None

    def _extract_invoice_date(self, text: str, details: dict[str, Any]) -> Optional[datetime]:
        """Extract invoice date from text."""
        # Look for invoice date specifically first
        invoice_date_pattern = re.compile(
            r"(?:Invoice\s+Date|Date|Billing\s+Date|Issue\s+Date)[:]*\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            re.IGNORECASE,
        )
        
        match = invoice_date_pattern.search(text)
        if match:
            date_str = match.group(1)
            parsed_date = self._parse_date(date_str)
            if parsed_date:
                details["invoice_date"] = {
                    "value": parsed_date,
                    "raw": date_str,
                    "confidence": 0.85,
                }
                return parsed_date

        # Fallback to general date patterns
        for pattern in self.date_patterns:
            match = pattern.search(text)
            if match:
                date_str = match.group(1)
                parsed_date = self._parse_date(date_str)
                if parsed_date and self._is_reasonable_invoice_date(parsed_date):
                    details["invoice_date"] = {
                        "value": parsed_date,
                        "raw": date_str,
                        "confidence": 0.7,
                    }
                    return parsed_date

        details["invoice_date"] = {"value": None, "confidence": 0.0}
        return None

    def _extract_due_date(self, text: str, details: dict[str, Any]) -> Optional[datetime]:
        """Extract due date from text."""
        due_date_pattern = re.compile(
            r"(?:Due\s+Date|Payment\s+Due|Due)[:]*\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            re.IGNORECASE,
        )
        
        match = due_date_pattern.search(text)
        if match:
            date_str = match.group(1)
            parsed_date = self._parse_date(date_str)
            if parsed_date:
                details["due_date"] = {
                    "value": parsed_date,
                    "raw": date_str,
                    "confidence": 0.85,
                }
                return parsed_date

        details["due_date"] = {"value": None, "confidence": 0.0}
        return None

    def _extract_vendor_name(self, text: str, details: dict[str, Any]) -> Optional[str]:
        """Extract vendor/shipper name from text."""
        for i, pattern in enumerate(self.vendor_patterns):
            match = pattern.search(text)
            if match:
                vendor_name = self._clean_company_name(match.group(1))
                if vendor_name and len(vendor_name) > 2:
                    details["vendor_name"] = {
                        "value": vendor_name,
                        "pattern_index": i,
                        "confidence": 0.8,
                    }
                    return vendor_name

        details["vendor_name"] = {"value": None, "confidence": 0.0}
        return None

    def _extract_customer_name(self, text: str, details: dict[str, Any]) -> Optional[str]:
        """Extract customer/consignee name from text."""
        for i, pattern in enumerate(self.customer_patterns):
            match = pattern.search(text)
            if match:
                customer_name = self._clean_company_name(match.group(1))
                if customer_name and len(customer_name) > 2:
                    details["customer_name"] = {
                        "value": customer_name,
                        "pattern_index": i,
                        "confidence": 0.8,
                    }
                    return customer_name

        details["customer_name"] = {"value": None, "confidence": 0.0}
        return None

    def _extract_vendor_address(self, text: str, details: dict[str, Any]) -> Optional[str]:
        """Extract vendor address from text."""
        return self._extract_address_near_term(text, "vendor", details)

    def _extract_customer_address(self, text: str, details: dict[str, Any]) -> Optional[str]:
        """Extract customer address from text."""
        return self._extract_address_near_term(text, "customer", details)

    def _extract_address_near_term(self, text: str, term_type: str, details: dict[str, Any]) -> Optional[str]:
        """Extract address near vendor/customer terms."""
        search_terms = {
            "vendor": ["Bill To", "Vendor", "From", "Shipper", "Carrier"],
            "customer": ["Ship To", "Customer", "Consignee", "Deliver To"]
        }
        
        terms = search_terms.get(term_type, [])
        
        for term in terms:
            # Look for address after the term
            pattern = re.compile(
                rf"{re.escape(term)}[:]*\s*\n?\s*[A-Za-z\s&.,'-]+\n?\s*([0-9]+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Way|Place|Pl)[^0-9]*?[A-Za-z\s]+,\s*[A-Z]{{2}}\s+\d{{5}}(?:-\d{{4}})?)",
                re.IGNORECASE | re.DOTALL,
            )
            
            match = pattern.search(text)
            if match:
                address = self._clean_address(match.group(1))
                details[f"{term_type}_address"] = {
                    "value": address,
                    "confidence": 0.75,
                }
                return address

        details[f"{term_type}_address"] = {"value": None, "confidence": 0.0}
        return None

    def _extract_total_amount(self, text: str, details: dict[str, Any]) -> Optional[float]:
        """Extract total amount from text."""
        # Look for total amount patterns in order of preference
        total_patterns = [
            re.compile(r"(?:Grand\s+Total|Invoice\s+Total|Total\s+Amount|Final\s+Total)[:]*\s*\$?\s*([\d,]+\.?\d{0,2})", re.IGNORECASE),
            re.compile(r"(?:Total|Amount\s+Due|Balance)[:]*\s*\$?\s*([\d,]+\.?\d{0,2})", re.IGNORECASE),
        ]
        
        for i, pattern in enumerate(total_patterns):
            match = pattern.search(text)
            if match:
                amount_str = match.group(1)
                amount = self._parse_amount(amount_str)
                if amount and amount > 0:
                    details["total_amount"] = {
                        "value": amount,
                        "raw": amount_str,
                        "pattern_index": i,
                        "confidence": 0.9 - (i * 0.1),
                    }
                    return amount

        details["total_amount"] = {"value": None, "confidence": 0.0}
        return None

    def _extract_subtotal(self, text: str, details: dict[str, Any]) -> Optional[float]:
        """Extract subtotal amount from text."""
        pattern = re.compile(r"(?:Subtotal|Sub\s+Total)[:]*\s*\$?\s*([\d,]+\.?\d{0,2})", re.IGNORECASE)
        match = pattern.search(text)
        
        if match:
            amount_str = match.group(1)
            amount = self._parse_amount(amount_str)
            if amount and amount > 0:
                details["subtotal"] = {
                    "value": amount,
                    "raw": amount_str,
                    "confidence": 0.8,
                }
                return amount

        details["subtotal"] = {"value": None, "confidence": 0.0}
        return None

    def _extract_tax_amount(self, text: str, details: dict[str, Any]) -> Optional[float]:
        """Extract tax amount from text."""
        pattern = re.compile(r"(?:Tax|Sales\s+Tax|VAT)[:]*\s*\$?\s*([\d,]+\.?\d{0,2})", re.IGNORECASE)
        match = pattern.search(text)
        
        if match:
            amount_str = match.group(1)
            amount = self._parse_amount(amount_str)
            if amount and amount >= 0:
                details["tax_amount"] = {
                    "value": amount,
                    "raw": amount_str,
                    "confidence": 0.8,
                }
                return amount

        details["tax_amount"] = {"value": None, "confidence": 0.0}
        return None

    def _extract_payment_terms(self, text: str, details: dict[str, Any]) -> Optional[str]:
        """Extract payment terms from text."""
        for i, pattern in enumerate(self.payment_terms_patterns):
            match = pattern.search(text)
            if match:
                terms = match.group(1).strip()
                if len(terms) > 2:
                    details["payment_terms"] = {
                        "value": terms,
                        "pattern_index": i,
                        "confidence": 0.8,
                    }
                    return terms

        details["payment_terms"] = {"value": None, "confidence": 0.0}
        return None

    def _extract_line_items(self, text: str, details: dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract line items from text."""
        line_items = []
        
        for pattern in self.line_item_patterns:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, tuple) and len(match) >= 2:
                    description = match[0].strip()
                    amount_str = match[1].strip()
                    amount = self._parse_amount(amount_str)
                    
                    if amount and amount > 0:
                        line_item = {
                            "description": description,
                            "total": amount,
                            "raw_amount": amount_str,
                        }
                        line_items.append(line_item)

        details["line_items"] = {
            "value": line_items,
            "count": len(line_items),
            "confidence": 0.7 if line_items else 0.0,
        }
        
        return line_items

    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Parse amount string to float."""
        if not amount_str:
            return None
            
        try:
            # Remove currency symbols, commas, and whitespace
            cleaned = re.sub(r'[$,\s]', '', amount_str)
            
            # Handle decimal places
            if '.' in cleaned:
                return float(cleaned)
            else:
                # If no decimal, assume it's whole dollars
                return float(cleaned)
                
        except (ValueError, InvalidOperation):
            logger.warning(f"Could not parse amount: {amount_str}")
            return None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object."""
        if not date_str:
            return None

        # Common date formats
        date_formats = [
            "%m/%d/%Y",
            "%m-%d-%Y", 
            "%m/%d/%y",
            "%m-%d-%y",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
        ]

        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(date_str.strip(), fmt)
                
                # Handle 2-digit years
                if parsed_date.year < 1950:
                    parsed_date = parsed_date.replace(year=parsed_date.year + 100)
                    
                return parsed_date
            except ValueError:
                continue

        logger.warning(f"Could not parse date: {date_str}")
        return None

    def _is_reasonable_invoice_date(self, date: datetime) -> bool:
        """Check if date is reasonable for an invoice (not too far in past/future)."""
        now = datetime.now()
        one_year_ago = now - timedelta(days=365)
        six_months_future = now + timedelta(days=180)
        
        return one_year_ago <= date <= six_months_future

    def _is_valid_invoice_number(self, invoice_num: str) -> bool:
        """Validate invoice number format."""
        if not invoice_num or len(invoice_num) < 3:
            return False
            
        # Should contain alphanumeric characters
        if not re.match(r'^[A-Z0-9\-_]+$', invoice_num, re.IGNORECASE):
            return False
            
        return True

    def _clean_company_name(self, name: str) -> str:
        """Clean and normalize company name."""
        if not name:
            return ""
            
        # Remove extra whitespace and normalize
        name = re.sub(r'\s+', ' ', name.strip())
        
        # Remove common OCR artifacts
        name = re.sub(r'[^\w\s&.,\'-]', '', name)
        
        return name.title()

    def _clean_address(self, address: str) -> str:
        """Clean and normalize address."""
        if not address:
            return ""
            
        # Remove extra whitespace and normalize
        address = re.sub(r'\s+', ' ', address.strip())
        
        # Remove common OCR artifacts but keep address-specific punctuation
        address = re.sub(r'[^\w\s,.\'-]', '', address)
        
        return address

    def _calculate_confidence(self, invoice_data: Invoice, details: dict[str, Any]) -> float:
        """Calculate confidence score based on extracted fields."""
        field_weights = {
            "invoice_number": 0.25,
            "total_amount": 0.20,
            "vendor_name": 0.15,
            "invoice_date": 0.10,
            "customer_name": 0.10,
            "line_items": 0.10,
            "subtotal": 0.05,
            "due_date": 0.05,
        }

        total_confidence = 0.0
        
        for field, weight in field_weights.items():
            field_detail = details.get(field, {})
            field_confidence = field_detail.get("confidence", 0.0)
            total_confidence += field_confidence * weight

        # Bonus for having multiple line items
        line_items = details.get("line_items", {})
        if line_items.get("count", 0) > 1:
            total_confidence += 0.05

        # Ensure confidence is between 0 and 1
        return min(max(total_confidence, 0.0), 1.0)

    def parse_from_ocr_result(self, ocr_result: dict[str, Any], document_id: str) -> ParsingResult:
        """
        Parse invoice from OCR result dictionary.

        Args:
            ocr_result: Dictionary containing OCR results with 'text' key
            document_id: UUID of the document being parsed

        Returns:
            ParsingResult with extracted invoice data
        """
        if not ocr_result or "text" not in ocr_result:
            logger.error("Invalid OCR result provided to invoice parser")
            empty_invoice = Invoice(document_id=document_id)
            return ParsingResult(
                data=empty_invoice,
                confidence=0.0,
                extraction_details={"error": "Invalid OCR result"},
            )

        return self.parse(ocr_result["text"], document_id) 
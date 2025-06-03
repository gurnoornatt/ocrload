"""
Lumper Receipt Parser

Processes lumper receipts to extract key fields including facility information,
service details, billing information, and driver/carrier details.
Handles both printed and handwritten receipts with varied layouts.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.models.database import LumperReceipt
from app.services.semantic_lumper_extractor import SemanticLumperExtractor

logger = logging.getLogger(__name__)


class LumperReceiptParser:
    """Parser for lumper receipt documents."""
    
    def __init__(self):
        """Initialize the lumper receipt parser."""
        self.semantic_extractor = SemanticLumperExtractor()
    
    def extract_receipt_number(self, text: str) -> Optional[str]:
        """Extract receipt or ticket number from text."""
        patterns = [
            r"(?:receipt|ticket|invoice)\s*#?\s*:?\s*([A-Z0-9\-_]+)",
            r"receipt\s+no\.?\s*:?\s*([A-Z0-9\-_]+)",
            r"ticket\s+no\.?\s*:?\s*([A-Z0-9\-_]+)",
            r"ref\s*#?\s*:?\s*([A-Z0-9\-_]+)",
            r"number\s*:?\s*([A-Z0-9\-_]+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                receipt_num = match.group(1).strip()
                if len(receipt_num) >= 3:  # Minimum valid length
                    logger.debug(f"Found receipt number: {receipt_num}")
                    return receipt_num
        
        return None
    
    def extract_facility_info(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract facility name and address from text."""
        facility_name = None
        facility_address = None
        
        # Facility name patterns
        name_patterns = [
            r"(?:warehouse|facility|location|site)\s*:?\s*([^\n\r]+)",
            r"(?:at|@)\s+([A-Z][A-Za-z\s&.,]+(?:warehouse|facility|center|depot))",
            r"([A-Z][A-Za-z\s&.,]*(?:warehouse|facility|center|depot|distribution))",
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if len(name) > 3 and not name.isdigit():
                    facility_name = name
                    logger.debug(f"Found facility name: {facility_name}")
                    break
        
        # Address patterns
        address_patterns = [
            r"(\d+\s+[A-Za-z\s,]+\s+(?:street|st|avenue|ave|road|rd|drive|dr|blvd|boulevard)(?:\s*,?\s*[A-Z]{2}\s+\d{5})?)",
            r"address\s*:?\s*([^\n\r]+)",
            r"located\s+at\s*:?\s*([^\n\r]+)",
        ]
        
        for pattern in address_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                address = match.group(1).strip()
                if len(address) > 10:
                    facility_address = address
                    logger.debug(f"Found facility address: {facility_address}")
                    break
        
        return facility_name, facility_address
    
    def extract_person_info(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract driver name and carrier name from text."""
        driver_name = None
        carrier_name = None
        
        # Driver name patterns
        driver_patterns = [
            r"driver\s*:?\s*([A-Za-z\s,.]+?)(?:\n|\r|$|carrier|company)",
            r"trucker\s*:?\s*([A-Za-z\s,.]+?)(?:\n|\r|$|carrier|company)",
            r"operator\s*:?\s*([A-Za-z\s,.]+?)(?:\n|\r|$|carrier|company)",
        ]
        
        for pattern in driver_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Clean up common artifacts
                name = re.sub(r'[^\w\s,.]', '', name)
                if len(name) > 2 and not name.isdigit():
                    driver_name = name
                    logger.debug(f"Found driver name: {driver_name}")
                    break
        
        # Carrier/company patterns
        carrier_patterns = [
            r"carrier\s*:?\s*([A-Za-z\s&.,]+?)(?:\n|\r|$|bol|pro)",
            r"company\s*:?\s*([A-Za-z\s&.,]+?)(?:\n|\r|$|bol|pro)",
            r"trucking\s*:?\s*([A-Za-z\s&.,]+?)(?:\n|\r|$|bol|pro)",
            r"fleet\s*:?\s*([A-Za-z\s&.,]+?)(?:\n|\r|$|bol|pro)",
        ]
        
        for pattern in carrier_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                name = re.sub(r'[^\w\s&,.]', '', name)
                if len(name) > 3 and not name.isdigit():
                    carrier_name = name
                    logger.debug(f"Found carrier name: {carrier_name}")
                    break
        
        return driver_name, carrier_name
    
    def extract_service_details(self, text: str) -> Tuple[Optional[str], Optional[float], Optional[float]]:
        """Extract service type, labor hours, and hourly rate."""
        service_type = None
        labor_hours = None
        hourly_rate = None
        
        # Service type patterns
        service_patterns = [
            r"service\s*:?\s*([A-Za-z\s,]+?)(?:\n|\r|$|hours|rate)",
            r"work\s+type\s*:?\s*([A-Za-z\s,]+?)(?:\n|\r|$|hours|rate)",
            r"labor\s*:?\s*([A-Za-z\s,]+?)(?:\n|\r|$|hours|rate)",
            r"(?:loading|unloading|lumping|handling)\s*([A-Za-z\s,]*)",
        ]
        
        for pattern in service_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                service = match.group(1).strip()
                if len(service) > 2:
                    service_type = service
                    logger.debug(f"Found service type: {service_type}")
                    break
        
        # Labor hours patterns
        hours_patterns = [
            r"hours?\s*:?\s*(\d+(?:\.\d+)?)",
            r"time\s*:?\s*(\d+(?:\.\d+)?)\s*(?:hrs?|hours?)",
            r"duration\s*:?\s*(\d+(?:\.\d+)?)",
            r"(\d+(?:\.\d+)?)\s*(?:hrs?|hours?)",
        ]
        
        for pattern in hours_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    hours = float(match.group(1))
                    if 0 < hours <= 24:  # Reasonable range
                        labor_hours = hours
                        logger.debug(f"Found labor hours: {labor_hours}")
                        break
                except ValueError:
                    continue
        
        # Hourly rate patterns
        rate_patterns = [
            r"rate\s*:?\s*\$?(\d+(?:\.\d+)?)",
            r"per\s+hour\s*:?\s*\$?(\d+(?:\.\d+)?)",
            r"\$(\d+(?:\.\d+)?)\s*(?:/hr|per\s+hour|hr)",
            r"hourly\s*:?\s*\$?(\d+(?:\.\d+)?)",
        ]
        
        for pattern in rate_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    rate = float(match.group(1))
                    if 0 < rate <= 1000:  # Reasonable range
                        hourly_rate = rate
                        logger.debug(f"Found hourly rate: {hourly_rate}")
                        break
                except ValueError:
                    continue
        
        return service_type, labor_hours, hourly_rate
    
    def extract_financial_info(self, text: str) -> Optional[float]:
        """Extract total amount from text."""
        # Total amount patterns
        total_patterns = [
            r"total\s*:?\s*\$?(\d+(?:\.\d+)?)",
            r"amount\s*:?\s*\$?(\d+(?:\.\d+)?)",
            r"charge\s*:?\s*\$?(\d+(?:\.\d+)?)",
            r"due\s*:?\s*\$?(\d+(?:\.\d+)?)",
            r"\$(\d+(?:\.\d+)?)(?:\s|$)",
        ]
        
        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    amount = float(match.group(1))
                    if amount > 0:
                        logger.debug(f"Found total amount: ${amount}")
                        return amount
                except ValueError:
                    continue
        
        return None
    
    def extract_bol_number(self, text: str) -> Optional[str]:
        """Extract BOL number if present."""
        patterns = [
            r"bol\s*#?\s*:?\s*([A-Z0-9\-_]+)",
            r"bill\s+of\s+lading\s*#?\s*:?\s*([A-Z0-9\-_]+)",
            r"b/l\s*#?\s*:?\s*([A-Z0-9\-_]+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                bol_num = match.group(1).strip()
                if len(bol_num) >= 3:
                    logger.debug(f"Found BOL number: {bol_num}")
                    return bol_num
        
        return None
    
    def extract_date(self, text: str) -> Optional[datetime]:
        """Extract receipt date from text."""
        # Date patterns
        date_patterns = [
            r"date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"(\d{4}-\d{1,2}-\d{1,2})",
        ]
        
        for pattern in date_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                date_str = match.group(1)
                try:
                    # Try different date formats
                    for fmt in ["%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y", "%Y-%m-%d"]:
                        try:
                            date_obj = datetime.strptime(date_str, fmt)
                            # Convert 2-digit years
                            if date_obj.year < 1950:
                                date_obj = date_obj.replace(year=date_obj.year + 100)
                            logger.debug(f"Found date: {date_obj.date()}")
                            return date_obj
                        except ValueError:
                            continue
                except Exception:
                    continue
        
        return None
    
    def parse_with_regex(self, text: str) -> Dict[str, Any]:
        """Parse lumper receipt using regex patterns."""
        logger.info("Starting regex-based lumper receipt parsing")
        
        # Extract all fields using regex
        receipt_number = self.extract_receipt_number(text)
        receipt_date = self.extract_date(text)
        facility_name, facility_address = self.extract_facility_info(text)
        driver_name, carrier_name = self.extract_person_info(text)
        service_type, labor_hours, hourly_rate = self.extract_service_details(text)
        total_amount = self.extract_financial_info(text)
        bol_number = self.extract_bol_number(text)
        
        # Build result
        result = {
            "receipt_number": receipt_number,
            "receipt_date": receipt_date.strftime("%Y-%m-%d") if receipt_date else None,
            "facility_name": facility_name,
            "facility_address": facility_address,
            "driver_name": driver_name,
            "carrier_name": carrier_name,
            "bol_number": bol_number,
            "service_type": service_type,
            "labor_hours": labor_hours,
            "hourly_rate": hourly_rate,
            "total_amount": total_amount,
            "equipment_used": None,  # Hard to extract with regex
            "special_services": None,
            "notes": None,
        }
        
        # Calculate confidence based on fields found
        total_fields = len([v for v in result.values() if v is not None])
        confidence = min(total_fields / 10.0, 1.0)  # 10 main fields
        
        logger.info(f"Regex parsing completed with {total_fields} fields found, confidence: {confidence:.2f}")
        return result, confidence
    
    async def parse_lumper_receipt(
        self, 
        text: str, 
        use_ai: bool = True, 
        confidence_threshold: float = 0.7
    ) -> Tuple[Dict[str, Any], float, bool]:
        """
        Parse lumper receipt using hybrid approach (regex + AI).
        
        Args:
            text: OCR text from lumper receipt
            use_ai: Whether to use AI extraction
            confidence_threshold: Minimum confidence to accept results
            
        Returns:
            Tuple of (parsed_data, confidence_score, success)
        """
        logger.info(f"Starting lumper receipt parsing (AI: {use_ai})")
        
        try:
            if use_ai:
                # Try AI extraction first
                extracted_data, ai_confidence, cross_validation = await self.semantic_extractor.extract_lumper_fields(text)
                
                if ai_confidence >= confidence_threshold:
                    # Convert to dict format
                    result = {
                        "receipt_number": extracted_data.receipt_number,
                        "receipt_date": extracted_data.receipt_date,
                        "facility_name": extracted_data.facility_name,
                        "facility_address": extracted_data.facility_address,
                        "driver_name": extracted_data.driver_name,
                        "carrier_name": extracted_data.carrier_name,
                        "bol_number": extracted_data.bol_number,
                        "service_type": extracted_data.service_type,
                        "labor_hours": extracted_data.labor_hours,
                        "hourly_rate": extracted_data.hourly_rate,
                        "total_amount": extracted_data.total_amount,
                        "equipment_used": extracted_data.equipment_used,
                        "special_services": extracted_data.special_services,
                        "notes": extracted_data.notes,
                    }
                    
                    logger.info(f"AI extraction successful with confidence: {ai_confidence:.2f}")
                    return result, ai_confidence, True
                else:
                    logger.warning(f"AI extraction confidence ({ai_confidence:.2f}) below threshold ({confidence_threshold})")
            
            # Fallback to regex parsing
            regex_result, regex_confidence = self.parse_with_regex(text)
            
            if regex_confidence >= confidence_threshold * 0.5:  # Lower threshold for regex
                logger.info(f"Regex extraction used with confidence: {regex_confidence:.2f}")
                return regex_result, regex_confidence, True
            else:
                logger.warning(f"Both AI and regex extraction failed to meet confidence thresholds")
                return regex_result, regex_confidence, False
                
        except Exception as e:
            logger.error(f"Lumper receipt parsing failed: {e}")
            return {}, 0.0, False
    
    def validate_parsed_data(self, data: Dict[str, Any]) -> List[str]:
        """Validate parsed lumper receipt data and return validation issues."""
        issues = []
        
        # Check required fields
        if not data.get("receipt_number"):
            issues.append("Missing receipt number")
        
        if not data.get("facility_name"):
            issues.append("Missing facility name")
        
        if not data.get("total_amount") or data.get("total_amount", 0) <= 0:
            issues.append("Missing or invalid total amount")
        
        # Check logical consistency
        if data.get("labor_hours") and data.get("hourly_rate") and data.get("total_amount"):
            calculated_total = data["labor_hours"] * data["hourly_rate"]
            actual_total = data["total_amount"]
            if abs(calculated_total - actual_total) / actual_total > 0.15:  # 15% tolerance
                issues.append("Labor calculation doesn't match total amount")
        
        # Check date format
        if data.get("receipt_date"):
            try:
                datetime.strptime(data["receipt_date"], "%Y-%m-%d")
            except (ValueError, TypeError):
                issues.append("Invalid date format")
        
        return issues 
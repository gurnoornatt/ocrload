#!/usr/bin/env python3
"""
COI Parser Unit Tests

Tests individual methods and edge cases of the COI parser to ensure
proper field extraction, validation, and error handling.
"""

import pytest
from datetime import datetime, timedelta

from app.services.document_parsers.coi_parser import COIParser


class TestCOIParser:
    """Unit tests for COI parser individual methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = COIParser()
    
    def test_policy_number_extraction(self):
        """Test policy number extraction patterns."""
        test_cases = [
            ("Policy Number: ABC-123-456", "ABC-123-456"),
            ("Policy No: PGR-9876543210", "PGR-9876543210"),
            ("Policy #: SF-445566", "SF-445566"),
            ("Certificate No: ALL-2025-789123", "ALL-2025-789123"),
            ("POLICY: TPC-L234567890", "TPC-L234567890"),
            ("Random text 123456789 more text", "123456789"),
            ("CERTIFICATE OF INSURANCE", None),  # Should not match standalone
            ("Policy Number: 2025", "2025"),  # Valid policy number (years 2020-2035 can be policy numbers)
            ("Policy Number: CERTIFICATE", None),  # False positive
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_policy_number(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_policy_number_validation(self):
        """Test policy number validation logic."""
        valid_policies = ["ABC-123-456", "PGR-9876543210", "GEICO-CL-7890123", "12345678", "2025", "2030"]  # Added valid years
        invalid_policies = ["CERTIFICATE", "POLICY", "1985", "2040", "12/31/2025", "1000000", "IFICATE"]  # Changed to clearly invalid years
        
        for policy in valid_policies:
            assert self.parser._is_valid_policy_number(policy), f"Should be valid: {policy}"
        
        for policy in invalid_policies:
            assert not self.parser._is_valid_policy_number(policy), f"Should be invalid: {policy}"
    
    def test_insurance_company_extraction(self):
        """Test insurance company extraction patterns."""
        test_cases = [
            ("Insurer: State Farm Fire and Casualty Company", "State Farm Fire And Casualty Company"),
            ("Insurance Company: Progressive Commercial Inc", "Progressive Commercial Inc"),
            ("Carrier: Government Employees Insurance Company", "Government Employees Insurance Company"),
            ("State Farm", "State Farm"),
            ("Random text", None),
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_insurance_company(text, details)
            # Normalize for comparison (the method returns title case)
            if result and expected:
                assert result.lower() == expected.lower(), f"Failed for '{text}': expected {expected}, got {result}"
            else:
                assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_company_name_cleaning(self):
        """Test company name cleaning logic."""
        test_cases = [
            ("State Farm Fire and Casualty Company Policy", "State Farm Fire And Casualty Company"),
            ("Progressive Commercial Insurance", "Progressive Commercial Insurance"),  # Insurance should be preserved in legitimate company names
            ("Company Name,", "Company Name"),
            ("CERTIFICATE INSURANCE", "Insurance"),  # Should filter out false positives like "CERTIFICATE"
        ]
        
        for input_name, expected in test_cases:
            result = self.parser._clean_company_name(input_name)
            assert result == expected, f"Failed for '{input_name}': expected '{expected}', got '{result}'"
    
    def test_currency_amount_parsing(self):
        """Test currency amount parsing with various formats."""
        test_cases = [
            ("1,000,000", "General Liability: $1,000,000", 100000000),  # $1M in cents
            ("2", "General Liability: $2 Million", 200000000),  # $2M in cents
            ("500", "Auto Liability: $500 Thousand", 50000000),  # $500K in cents
            ("1.5", "Coverage: $1.5M", 150000000),  # $1.5M in cents
            ("invalid", "Coverage: $invalid", None),
        ]
        
        for amount_str, full_match, expected in test_cases:
            result = self.parser._parse_currency_amount(amount_str, full_match)
            assert result == expected, f"Failed for '{amount_str}' in '{full_match}': expected {expected}, got {result}"
    
    def test_general_liability_extraction(self):
        """Test general liability amount extraction."""
        test_cases = [
            ("General Liability: $1,000,000", 100000000),
            ("GL: $2M", 200000000),
            ("Each Occurrence: $500,000", 50000000),
            ("Bodily Injury: $1,000,000", 100000000),
            ("Random text", None),
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_general_liability_amount(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_auto_liability_extraction(self):
        """Test auto liability amount extraction."""
        test_cases = [
            ("Auto Liability: $1,000,000", 100000000),
            ("Commercial Auto: $750,000", 75000000),
            ("Combined Single Limit: $2,000,000", 200000000),
            ("Liability Limit: $1,000,000", 100000000),
            ("Random text", None),
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_auto_liability_amount(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_date_parsing(self):
        """Test date parsing with various formats."""
        test_cases = [
            ("01/01/2025", datetime(2025, 1, 1)),
            ("12-31-2025", datetime(2025, 12, 31)),
            ("01/01/25", datetime(2025, 1, 1)),
            ("2025/01/01", datetime(2025, 1, 1)),
            ("2025-01-01", datetime(2025, 1, 1)),
            ("invalid_date", None),
        ]
        
        for date_str, expected in test_cases:
            result = self.parser._parse_date(date_str)
            assert result == expected, f"Failed for '{date_str}': expected {expected}, got {result}"
    
    def test_effective_date_extraction(self):
        """Test effective date extraction patterns."""
        test_cases = [
            ("Effective Date: 01/01/2025", datetime(2025, 1, 1)),
            ("Effective: 01/01/2025", datetime(2025, 1, 1)),
            ("Policy Period: 01/01/2025 to 01/01/2026", datetime(2025, 1, 1)),
            ("From: 01/01/2025", datetime(2025, 1, 1)),
            ("Random text", None),
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_effective_date(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_expiration_date_extraction(self):
        """Test expiration date extraction patterns."""
        future_date = datetime.now() + timedelta(days=365)
        future_date_str = future_date.strftime('%m/%d/%Y')
        
        test_cases = [
            (f"Expiration Date: {future_date_str}", future_date.replace(hour=0, minute=0, second=0, microsecond=0)),
            (f"Expires: {future_date_str}", future_date.replace(hour=0, minute=0, second=0, microsecond=0)),
            (f"To: {future_date_str}", future_date.replace(hour=0, minute=0, second=0, microsecond=0)),
            ("Expiration Date: 01/01/2020", None),  # Past date should be rejected
            ("Random text", None),
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_expiration_date(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_confidence_calculation(self):
        """Test confidence score calculation logic."""
        from app.models.database import COIData
        
        # High confidence: all fields present
        full_coi = COIData(
            policy_number="ABC-123-456",
            insurance_company="Test Insurance",
            general_liability_amount=100000000,
            auto_liability_amount=100000000,
            effective_date=datetime(2025, 1, 1),
            expiration_date=datetime(2026, 1, 1)
        )
        confidence = self.parser._calculate_confidence(full_coi, {})
        assert confidence >= 0.90, f"Full COI should have high confidence: {confidence}"
        
        # Medium confidence: policy + amounts + dates
        medium_coi = COIData(
            policy_number="ABC-123-456",
            general_liability_amount=100000000,
            expiration_date=datetime(2026, 1, 1)
        )
        confidence = self.parser._calculate_confidence(medium_coi, {})
        assert 0.70 <= confidence < 0.90, f"Medium COI should have medium confidence: {confidence}"
        
        # Low confidence: minimal fields
        low_coi = COIData(
            insurance_company="Test Insurance",
            general_liability_amount=100000000
        )
        confidence = self.parser._calculate_confidence(low_coi, {})
        assert confidence < 0.70, f"Low COI should have low confidence: {confidence}"
    
    def test_insurance_verification_logic(self):
        """Test insurance verification requirements."""
        from app.models.database import COIData
        
        # Valid insurance: has policy, amount, and future expiration
        valid_coi = COIData(
            policy_number="ABC-123-456",
            general_liability_amount=100000000,
            expiration_date=datetime.now() + timedelta(days=60)
        )
        assert self.parser._is_insurance_verified(valid_coi), "Valid COI should be verified"
        
        # Invalid: no policy number
        no_policy = COIData(
            general_liability_amount=100000000,
            expiration_date=datetime.now() + timedelta(days=60)
        )
        assert not self.parser._is_insurance_verified(no_policy), "COI without policy should not be verified"
        
        # Invalid: no liability amounts
        no_amounts = COIData(
            policy_number="ABC-123-456",
            expiration_date=datetime.now() + timedelta(days=60)
        )
        assert not self.parser._is_insurance_verified(no_amounts), "COI without amounts should not be verified"
        
        # Invalid: expiring soon
        expiring_soon = COIData(
            policy_number="ABC-123-456",
            general_liability_amount=100000000,
            expiration_date=datetime.now() + timedelta(days=15)
        )
        assert not self.parser._is_insurance_verified(expiring_soon), "COI expiring soon should not be verified"
    
    def test_ocr_result_parsing(self):
        """Test parsing from OCR service results."""
        # Test with full_text
        ocr_result_1 = {
            'full_text': 'CERTIFICATE OF INSURANCE\nPolicy Number: TEST-123456\nGeneral Liability: $1,000,000\nExpiration Date: 12/31/2025',
            'average_confidence': 0.95
        }
        
        result = self.parser.parse_from_ocr_result(ocr_result_1)
        assert result.data.policy_number == "TEST-123456"
        assert result.data.general_liability_amount == 100000000
        assert result.confidence > 0.5
        
        # Test with pages structure
        ocr_result_2 = {
            'pages': [
                {'text': 'CERTIFICATE OF INSURANCE\nPolicy Number: TEST-789012'},
                {'text': 'General Liability: $2,000,000\nExpiration Date: 12/31/2025'}
            ]
        }
        
        result = self.parser.parse_from_ocr_result(ocr_result_2)
        assert result.data.policy_number == "TEST-789012"
        assert result.data.general_liability_amount == 200000000
        
        # Test with no text
        ocr_result_3 = {'pages': []}
        
        result = self.parser.parse_from_ocr_result(ocr_result_3)
        assert result.confidence == 0.0
        assert not result.insurance_verified
        assert 'error' in result.extraction_details


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 
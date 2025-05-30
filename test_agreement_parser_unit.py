#!/usr/bin/env python3
"""
Agreement Parser Unit Tests

Tests individual methods and edge cases of the Agreement parser to ensure
proper field extraction, signature detection, and confidence scoring.
"""

import pytest
from datetime import datetime, timedelta

from app.services.document_parsers.agreement_parser import AgreementParser


class TestAgreementParser:
    """Unit tests for Agreement parser individual methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = AgreementParser()
    
    def test_signature_detection(self):
        """Test signature detection patterns."""
        test_cases = [
            ("Digitally Signed by: John Doe", True),
            ("Signature: Jane Smith", True), 
            ("Driver Signature: Mike Johnson", True),
            ("Signed on: 01/01/2025", True),
            ("X___________________", True),  # Signature line with X
            ("I agree to the terms and conditions", True),
            ("Random text without signature", False),
            ("Driver Signature:", True),  # Empty signature placeholder still counts
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._detect_signature(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_strong_signature_indicators(self):
        """Test strong signature indicator detection."""
        # Test digital signature (strong indicator)
        text = "Digitally Signed by: John Doe"
        details = {}
        result = self.parser._detect_signature(text, details)
        assert result is True, "Digital signature should be detected as strong indicator"
        
        # Test electronic agreement (strong indicator)
        text = "I agree to the terms and conditions of this contract"
        details = {}
        result = self.parser._detect_signature(text, details)
        assert result is True, "Electronic agreement should be strong indicator"
        
        # Test signature line with name (strong indicator)
        text = "Signature: John Smith"
        details = {}
        result = self.parser._detect_signature(text, details)
        assert result is True, "Signature line with name should be strong indicator"
    
    def test_agreement_type_extraction(self):
        """Test agreement type extraction patterns."""
        test_cases = [
            ("Driver Agreement", "Driver Agreement"),
            ("Independent Contractor Agreement", "Independent Contractor Agreement"),
            ("Terms and Conditions", "Terms and Conditions"),
            ("Employment Contract", "Employment Contract"),
            ("Non-Disclosure Agreement", "Non-disclosure Agreement"),
            ("Transportation Agreement", "Transportation Agreement"),
            ("Freight Broker Agreement", "Freight Broker Agreement"),
            ("Random text", None),
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_agreement_type(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_key_terms_extraction(self):
        """Test key terms extraction patterns."""
        agreement_text = """
        LIABILITY INSURANCE COVERAGE: $1,000,000 minimum required
        PAYMENT TERMS: $2.50 per mile compensation
        EQUIPMENT REQUIREMENTS: Class A CDL and compliant vehicle required
        TERMINATION: 30 days written notice required
        COMPLIANCE: Must maintain DOT compliance standards
        """
        
        details = {}
        result = self.parser._extract_key_terms(agreement_text, details)
        
        assert result is not None, "Should extract key terms"
        assert len(result) > 0, "Should find multiple key terms"
        assert details['key_terms_found'] > 0, "Should report number of terms found"
    
    def test_signing_date_extraction(self):
        """Test signing date extraction patterns."""
        test_cases = [
            ("Date Signed: 01/01/2025", datetime(2025, 1, 1)),
            ("Signed on: 12/31/2024", datetime(2024, 12, 31)),
            ("Signature Date: 06-15-2025", datetime(2025, 6, 15)),
            ("Agreement Date: 03/20/2025", datetime(2025, 3, 20)),
            ("Random text", None),
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_signing_date(text, details)
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
    
    def test_confidence_calculation(self):
        """Test confidence score calculation logic."""
        from app.models.database import AgreementData
        
        # High confidence: signature + type + date
        full_agreement = AgreementData(
            signature_detected=True,
            agreement_type="Driver Agreement",
            signing_date=datetime(2025, 1, 1),
            key_terms=["payment terms", "liability requirements"]
        )
        confidence = self.parser._calculate_confidence(full_agreement, {})
        assert confidence >= 0.90, f"Full agreement should have high confidence: {confidence}"
        
        # Good confidence: signature + type
        good_agreement = AgreementData(
            signature_detected=True,
            agreement_type="Driver Agreement"
        )
        confidence = self.parser._calculate_confidence(good_agreement, {})
        assert 0.80 <= confidence < 0.90, f"Good agreement should have good confidence: {confidence}"
        
        # Medium confidence: signature + terms
        medium_agreement = AgreementData(
            signature_detected=True,
            key_terms=["payment terms", "equipment requirements"]
        )
        confidence = self.parser._calculate_confidence(medium_agreement, {})
        assert 0.70 <= confidence < 0.85, f"Medium agreement should have medium confidence: {confidence}"
        
        # Low confidence: no signature
        low_agreement = AgreementData(
            agreement_type="Driver Agreement",
            key_terms=["some terms"]
        )
        confidence = self.parser._calculate_confidence(low_agreement, {})
        assert confidence < 0.70, f"Low agreement should have low confidence: {confidence}"
    
    def test_agreement_signed_threshold(self):
        """Test agreement_signed flag setting based on confidence threshold."""
        from app.models.database import AgreementData
        
        # High confidence agreement should have agreement_signed = True
        high_conf_agreement = AgreementData(
            signature_detected=True,
            agreement_type="Driver Agreement",
            signing_date=datetime(2025, 1, 1)
        )
        
        text = "Digitally Signed by: John Doe\nDriver Agreement\nDate Signed: 01/01/2025"
        result = self.parser.parse(text)
        
        assert result.confidence >= 0.90, f"Should have high confidence: {result.confidence}"
        assert result.agreement_signed is True, "Should set agreement_signed to True for high confidence"
        
        # Low confidence agreement should have agreement_signed = False
        low_conf_text = "Some random text that might be an agreement"
        result = self.parser.parse(low_conf_text)
        
        assert result.confidence < 0.90, f"Should have low confidence: {result.confidence}"
        assert result.agreement_signed is False, "Should set agreement_signed to False for low confidence"
    
    def test_signature_pattern_types(self):
        """Test signature pattern type classification."""
        # Test pattern type mapping
        assert self.parser._get_signature_pattern_type(0) == 'digital_signature'
        assert self.parser._get_signature_pattern_type(1) == 'signature_line_driver'
        assert self.parser._get_signature_pattern_type(2) == 'signature_line'
        assert self.parser._get_signature_pattern_type(3) == 'signed_by'
        assert self.parser._get_signature_pattern_type(4) == 'signature_marks'
        assert self.parser._get_signature_pattern_type(5) == 'signed_date'
        assert self.parser._get_signature_pattern_type(6) == 'signed_on'
        assert self.parser._get_signature_pattern_type(7) == 'electronic_agreement'
        assert self.parser._get_signature_pattern_type(999) == 'unknown'
    
    def test_signature_quality_boost(self):
        """Test confidence boost for multiple signature indicators."""
        # Create text with multiple signature indicators
        multi_signature_text = """
        Digitally Signed by: John Doe
        Driver Signature: John Doe
        Signed on: 01/01/2025
        X_____________________
        I agree to the terms and conditions
        """
        
        result = self.parser.parse(multi_signature_text)
        
        # Should have high confidence due to multiple signature indicators
        assert result.confidence >= 0.95, f"Multiple signatures should boost confidence: {result.confidence}"
        assert result.data.signature_detected is True
        assert result.agreement_signed is True
    
    def test_ocr_result_parsing(self):
        """Test parsing from OCR service results."""
        # Test with full_text
        ocr_result_1 = {
            'full_text': 'Driver Agreement\nDigitally Signed by: John Doe\nDate Signed: 01/01/2025',
            'average_confidence': 0.95
        }
        
        result = self.parser.parse_from_ocr_result(ocr_result_1)
        assert result.data.signature_detected is True
        assert result.data.agreement_type == "Driver Agreement"
        assert result.confidence > 0.8
        assert result.agreement_signed is True
        
        # Test with pages structure
        ocr_result_2 = {
            'pages': [
                {'text': 'Transportation Agreement'},
                {'text': 'Signature: Jane Smith\nSigned on: 12/31/2024'}
            ]
        }
        
        result = self.parser.parse_from_ocr_result(ocr_result_2)
        assert result.data.signature_detected is True
        assert result.data.agreement_type == "Transportation Agreement"
        
        # Test with no text
        ocr_result_3 = {'pages': []}
        
        result = self.parser.parse_from_ocr_result(ocr_result_3)
        assert result.confidence == 0.0
        assert result.agreement_signed is False
        assert 'error' in result.extraction_details
    
    def test_parse_complete_agreement(self):
        """Test parsing a complete agreement document."""
        complete_agreement_text = """
        INDEPENDENT CONTRACTOR AGREEMENT
        
        This agreement is between ABC Transport Company and the Driver.
        
        PAYMENT TERMS: Driver will receive $2.50 per mile compensation
        EQUIPMENT REQUIREMENTS: Driver must maintain Class A CDL
        LIABILITY INSURANCE: Minimum $1,000,000 coverage required
        TERMINATION: Either party may terminate with 30 days notice
        DOT COMPLIANCE: Driver must maintain all DOT requirements
        
        By signing below, I agree to all terms and conditions:
        
        Driver Signature: John Smith
        Date Signed: 01/15/2025
        
        Digitally Signed by: John Smith
        """
        
        result = self.parser.parse(complete_agreement_text)
        
        # Should extract all major components
        assert result.data.signature_detected is True, "Should detect signature"
        assert result.data.agreement_type == "Independent Contractor Agreement", f"Should extract agreement type: {result.data.agreement_type}"
        assert result.data.signing_date == datetime(2025, 1, 15), f"Should extract signing date: {result.data.signing_date}"
        assert result.data.key_terms is not None, "Should extract key terms"
        assert len(result.data.key_terms) > 0, "Should find multiple key terms"
        
        # Should have high confidence and be marked as signed
        assert result.confidence >= 0.90, f"Should have high confidence: {result.confidence}"
        assert result.agreement_signed is True, "Should be marked as signed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 
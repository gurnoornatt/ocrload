#!/usr/bin/env python3
"""
Agreement Parser Unit Tests

Unit tests for testing specific methods and edge cases in the Agreement parser.
These are isolated unit tests that don't depend on external services.
"""

import os
import sys
import unittest
from datetime import datetime

# Add the app directory to the path to avoid service imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Import only the parser and data model directly
from app.models.database import AgreementData
from app.services.document_parsers.agreement_parser import AgreementParser


class TestAgreementParserMethods(unittest.TestCase):
    """Unit tests for Agreement parser methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.parser = AgreementParser()

    def test_signature_detection_basic(self):
        """Test basic signature detection patterns."""
        test_cases = [
            ("Digitally Signed by: John Smith", True),
            ("Signature: Jane Doe", True),
            ("Driver Signature: Bob Johnson", True),
            ("X___________________", True),  # Signature line
            ("Random text without signature", False),
        ]

        for text, expected in test_cases:
            with self.subTest(text=text):
                details = {}
                result = self.parser._detect_signature(text, details)
                self.assertEqual(result, expected)

    def test_agreement_type_extraction(self):
        """Test agreement type extraction patterns."""
        test_cases = [
            ("Driver Agreement", "Driver Agreement"),
            ("Transportation Agreement", "Transportation Agreement"),
            ("Freight Broker Agreement", "Freight Broker Agreement"),
            ("Terms and Conditions", "Terms and Conditions"),
            ("Random text", None),
        ]

        for text, expected in test_cases:
            with self.subTest(text=text):
                details = {}
                result = self.parser._extract_agreement_type(text, details)
                self.assertEqual(result, expected)

    def test_signing_date_extraction(self):
        """Test signing date extraction patterns."""
        test_cases = [
            ("Date Signed: 01/01/2025", datetime(2025, 1, 1)),
            ("Signed on: 12/31/2024", datetime(2024, 12, 31)),
            ("Agreement Date: 06-15-2025", datetime(2025, 6, 15)),
            ("Random text", None),
        ]

        for text, expected in test_cases:
            with self.subTest(text=text):
                details = {}
                result = self.parser._extract_signing_date(text, details)
                self.assertEqual(result, expected)

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

        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_confidence_calculation(self):
        """Test confidence calculation logic."""
        # High confidence: signature + type + date + terms
        full_agreement = AgreementData(
            signature_detected=True,
            agreement_type="Driver Agreement",
            signing_date=datetime(2025, 1, 1),
            key_terms=["payment terms", "liability requirements"],
        )
        confidence = self.parser._calculate_confidence(full_agreement, {})
        self.assertGreaterEqual(confidence, 0.80)

        # Medium confidence: signature + type
        medium_agreement = AgreementData(
            signature_detected=True, agreement_type="Driver Agreement"
        )
        confidence = self.parser._calculate_confidence(medium_agreement, {})
        self.assertGreaterEqual(confidence, 0.50)
        self.assertLess(confidence, 0.90)

        # Low confidence: no signature
        low_agreement = AgreementData(
            signature_detected=False,
            agreement_type="Driver Agreement",
            key_terms=["some terms"],
        )
        confidence = self.parser._calculate_confidence(low_agreement, {})
        self.assertLess(confidence, 0.70)

        # Very low confidence: minimal fields
        minimal_agreement = AgreementData(signature_detected=False)
        confidence = self.parser._calculate_confidence(minimal_agreement, {})
        self.assertLess(confidence, 0.50)

    def test_agreement_parsing_signed(self):
        """Test full agreement parsing with signed document."""
        sample_text = """
        DRIVER AGREEMENT

        This agreement is between ABC Transport Company and the Driver.

        PAYMENT TERMS: Driver will receive $2.50 per mile compensation
        EQUIPMENT REQUIREMENTS: Driver must maintain Class A CDL
        LIABILITY INSURANCE: Minimum $1,000,000 coverage required

        By signing below, I agree to all terms and conditions:

        Driver Signature: John Smith
        Date Signed: 01/15/2025

        Digitally Signed by: John Smith
        """

        result = self.parser.parse(sample_text)

        # Should detect signature
        self.assertTrue(result.data.signature_detected)

        # Should extract agreement type
        self.assertIsNotNone(result.data.agreement_type)
        self.assertEqual(result.data.agreement_type, "Driver Agreement")

        # Should extract signing date
        self.assertIsNotNone(result.data.signing_date)
        self.assertEqual(result.data.signing_date, datetime(2025, 1, 15))

        # Should extract key terms
        self.assertIsNotNone(result.data.key_terms)
        self.assertGreater(len(result.data.key_terms), 0)

        # Should have high confidence
        self.assertGreater(result.confidence, 0.8)

        # Should be marked as signed
        self.assertTrue(result.agreement_signed)

    def test_agreement_parsing_unsigned(self):
        """Test parsing of unsigned agreement."""
        sample_text = """
        TRANSPORTATION AGREEMENT

        This is a standard transportation agreement.

        TERMS AND CONDITIONS:
        - Payment terms: Net 30 days
        - Equipment requirements apply

        Please review all terms before proceeding.
        """

        result = self.parser.parse(sample_text)

        # Should extract agreement type
        self.assertIsNotNone(result.data.agreement_type)
        self.assertEqual(result.data.agreement_type, "Transportation Agreement")

        # Should not detect signature (no signature indicators present)
        self.assertFalse(result.data.signature_detected)

        # Should have lower confidence due to lack of signature
        self.assertLess(result.confidence, 0.9)

        # Should not be marked as signed
        self.assertFalse(result.agreement_signed)

    def test_pattern_type_identification(self):
        """Test signature pattern type identification."""
        # Test pattern type mapping exists
        pattern_type = self.parser._get_signature_pattern_type(0)
        self.assertEqual(pattern_type, "digital_signature")

        pattern_type = self.parser._get_signature_pattern_type(1)
        self.assertEqual(pattern_type, "signature_line_driver")

        pattern_type = self.parser._get_signature_pattern_type(2)
        self.assertEqual(pattern_type, "signature_line")


if __name__ == "__main__":
    print("🧪 AGREEMENT PARSER UNIT TESTS")
    print("=" * 50)

    # Run tests
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""
COI Parser Unit Tests

Unit tests for testing specific methods and edge cases in the COI parser.
These are isolated unit tests that don't depend on external services.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta

# Add the app directory to the path to avoid service imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Import only the parser and data model directly
from app.models.database import COIData
from app.services.document_parsers.coi_parser import COIParser


class TestCOIParserMethods(unittest.TestCase):
    """Unit tests for COI parser methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.parser = COIParser()

    def test_clean_company_name_basic(self):
        """Test company name cleaning with basic cases."""
        test_cases = [
            ("ACME INSURANCE COMPANY", "Acme Insurance Company"),
            ("acme insurance", "Acme Insurance"),
            ("  PROGRESSIVE COMMERCIAL  ", "Progressive Commercial"),
            ("STATE FARM MUTUAL", "State Farm Mutual"),
            ("PROGRESSIVE COMMERCIAL INSURANCE", "Progressive Commercial Insurance"),
            ("Company Name,", "Company Name"),
            ("CERTIFICATE INSURANCE", "Insurance"),  # Should filter out false positives
        ]

        for input_name, expected in test_cases:
            result = self.parser._clean_company_name(input_name)
            assert (
                result == expected
            ), f"Failed for '{input_name}': expected '{expected}', got '{result}'"

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
            assert (
                result == expected
            ), f"Failed for '{amount_str}' in '{full_match}': expected {expected}, got {result}"

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
            assert (
                result == expected
            ), f"Failed for '{text}': expected {expected}, got {result}"

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
            assert (
                result == expected
            ), f"Failed for '{text}': expected {expected}, got {result}"

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
            assert (
                result == expected
            ), f"Failed for '{date_str}': expected {expected}, got {result}"

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
            assert (
                result == expected
            ), f"Failed for '{text}': expected {expected}, got {result}"

    def test_expiration_date_extraction(self):
        """Test expiration date extraction patterns."""
        future_date = datetime.now() + timedelta(days=365)
        future_date_str = future_date.strftime("%m/%d/%Y")

        test_cases = [
            (
                f"Expiration Date: {future_date_str}",
                future_date.replace(hour=0, minute=0, second=0, microsecond=0),
            ),
            (
                f"Expires: {future_date_str}",
                future_date.replace(hour=0, minute=0, second=0, microsecond=0),
            ),
            (
                f"To: {future_date_str}",
                future_date.replace(hour=0, minute=0, second=0, microsecond=0),
            ),
            ("Expiration Date: 01/01/2020", None),  # Past date should be rejected
            ("Random text", None),
        ]

        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_expiration_date(text, details)
            assert (
                result == expected
            ), f"Failed for '{text}': expected {expected}, got {result}"

    def test_confidence_calculation(self):
        """Test confidence score calculation logic."""
        # High confidence: all fields present
        full_coi = COIData(
            policy_number="ABC-123-456",
            insurance_company="Test Insurance",
            general_liability_amount=100000000,
            auto_liability_amount=100000000,
            effective_date=datetime(2025, 1, 1),
            expiration_date=datetime(2026, 1, 1),
        )
        confidence = self.parser._calculate_confidence(full_coi, {})
        assert confidence >= 0.90, f"Full COI should have high confidence: {confidence}"

        # Medium confidence: policy + amounts + dates
        medium_coi = COIData(
            policy_number="ABC-123-456",
            general_liability_amount=100000000,
            expiration_date=datetime(2026, 1, 1),
        )
        confidence = self.parser._calculate_confidence(medium_coi, {})
        assert (
            0.70 <= confidence < 0.90
        ), f"Medium COI should have medium confidence: {confidence}"

        # Low confidence: minimal fields
        low_coi = COIData(
            insurance_company="Test Insurance", general_liability_amount=100000000
        )
        confidence = self.parser._calculate_confidence(low_coi, {})
        assert confidence < 0.70, f"Low COI should have low confidence: {confidence}"

    def test_insurance_verification_logic(self):
        """Test insurance verification requirements."""
        # Valid insurance: has policy, amount, and future expiration
        valid_coi = COIData(
            policy_number="ABC-123-456",
            general_liability_amount=100000000,
            expiration_date=datetime.now() + timedelta(days=60),
        )
        assert self.parser._is_insurance_verified(
            valid_coi
        ), "Valid COI should be verified"

        # Invalid: no policy number
        no_policy = COIData(
            general_liability_amount=100000000,
            expiration_date=datetime.now() + timedelta(days=60),
        )
        assert not self.parser._is_insurance_verified(
            no_policy
        ), "COI without policy should not be verified"

        # Invalid: no liability amounts
        no_amounts = COIData(
            policy_number="ABC-123-456",
            expiration_date=datetime.now() + timedelta(days=60),
        )
        assert not self.parser._is_insurance_verified(
            no_amounts
        ), "COI without amounts should not be verified"

        # Invalid: expiring soon
        expiring_soon = COIData(
            policy_number="ABC-123-456",
            general_liability_amount=100000000,
            expiration_date=datetime.now() + timedelta(days=15),
        )
        assert not self.parser._is_insurance_verified(
            expiring_soon
        ), "COI expiring soon should not be verified"

    def test_coi_expired_parsing(self):
        """Test COI expired in 2023 -> insurance_verified=False."""
        # Sample COI text with expired insurance (2023)
        expired_coi_text = """
        CERTIFICATE OF INSURANCE

        POLICY NUMBER: TEST-EXPIRED-2023
        INSURANCE COMPANY: ACME INSURANCE COMPANY
        INSURED: TEST TRUCKING COMPANY

        GENERAL LIABILITY: $1,000,000
        COMMERCIAL AUTO LIABILITY: $1,000,000

        POLICY PERIOD:
        FROM: 01/01/2023
        TO: 12/31/2023
        EXPIRES: 12/31/2023

        This is to certify that the policies of insurance listed above have been issued.
        """

        result = self.parser.parse(expired_coi_text)

        # Should parse basic info correctly
        self.assertIsNotNone(result.data.policy_number)
        self.assertIsNotNone(result.data.insurance_company)
        self.assertIsNotNone(result.data.general_liability_amount)

        # Should NOT be verified due to expiration in 2023
        self.assertFalse(
            result.insurance_verified, "Expired COI should not be verified"
        )

        # Should have good confidence despite being expired
        self.assertGreater(result.confidence, 0.7)

    def test_coi_valid_parsing(self):
        """Test valid COI parsing."""
        # Sample COI text with valid insurance
        valid_coi_text = """
        CERTIFICATE OF INSURANCE

        POLICY NUMBER: TEST-VALID-2025
        INSURANCE COMPANY: PROGRESSIVE COMMERCIAL INSURANCE
        INSURED: TEST TRUCKING COMPANY

        GENERAL LIABILITY: $1,000,000
        COMMERCIAL AUTO LIABILITY: $1,000,000

        POLICY PERIOD:
        FROM: 01/01/2025
        TO: 12/31/2025
        EXPIRES: 12/31/2025

        This is to certify that the policies of insurance listed above have been issued.
        """

        result = self.parser.parse(valid_coi_text)

        # Should parse correctly
        self.assertIsNotNone(result.data.policy_number)
        self.assertIsNotNone(result.data.insurance_company)
        self.assertIsNotNone(result.data.general_liability_amount)
        self.assertIsNotNone(result.data.expiration_date)

        # Should be verified if expiration is far enough in future
        if (
            result.data.expiration_date
            and result.data.expiration_date > datetime.now() + timedelta(days=30)
        ):
            self.assertTrue(result.insurance_verified, "Valid COI should be verified")

        # Should have good confidence
        self.assertGreater(result.confidence, 0.7)


if __name__ == "__main__":
    print("🧪 COI PARSER UNIT TESTS")
    print("=" * 50)

    # Run tests
    unittest.main(verbosity=2)

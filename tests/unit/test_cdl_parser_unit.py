#!/usr/bin/env python3
"""
CDL Parser Unit Tests

Unit tests for testing specific methods and edge cases in the CDL parser.
These are isolated unit tests that don't depend on external services.
"""

import unittest
from datetime import datetime, timedelta
import sys
import os

# Add the app directory to the path to avoid service imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Import only the parser and data model directly
from app.services.document_parsers.cdl_parser import CDLParser
from app.models.database import CDLData


class TestCDLParserMethods(unittest.TestCase):
    """Unit tests for CDL parser methods."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = CDLParser()
    
    def test_clean_name_basic(self):
        """Test name cleaning with basic cases."""
        # Normal name
        self.assertEqual(self.parser._clean_name("JOHN SMITH"), "John Smith")
        
        # Name with extra spaces
        self.assertEqual(self.parser._clean_name("  JOHN   SMITH  "), "John Smith")
        
        # Last, First format
        self.assertEqual(self.parser._clean_name("SMITH, JOHN"), "John Smith")
        
        # Name with noise words
        self.assertEqual(self.parser._clean_name("JOHN SMITH LICENSE"), "John Smith")
        self.assertEqual(self.parser._clean_name("JOHN SMITH CDL"), "John Smith")
    
    def test_clean_name_edge_cases(self):
        """Test name cleaning edge cases."""
        # Name with license number
        self.assertEqual(self.parser._clean_name("JOHN SMITH D1234567"), "John Smith")
        
        # Name with date
        self.assertEqual(self.parser._clean_name("JOHN SMITH 12/25/2025"), "John Smith")
        
        # Empty name
        self.assertEqual(self.parser._clean_name(""), "")
        
        # Only noise words
        cleaned = self.parser._clean_name("LICENSE CDL EXPIRES")
        self.assertEqual(cleaned, "LICENSE CDL EXPIRES")  # Returns original if all filtered
    
    def test_parse_date_formats(self):
        """Test date parsing with various formats."""
        test_cases = [
            ("12/25/2025", datetime(2025, 12, 25)),
            ("12-25-2025", datetime(2025, 12, 25)),
            ("12/25/25", datetime(2025, 12, 25)),
            ("2025/12/25", datetime(2025, 12, 25)),
            ("2025-12-25", datetime(2025, 12, 25)),
        ]
        
        for date_str, expected in test_cases:
            with self.subTest(date_str=date_str):
                result = self.parser._parse_date(date_str)
                self.assertEqual(result, expected)
    
    def test_parse_date_invalid(self):
        """Test date parsing with invalid dates."""
        invalid_dates = [
            "invalid",
            "13/25/2025",  # Invalid month
            "12/32/2025",  # Invalid day
            "",
            "not a date",
        ]
        
        for date_str in invalid_dates:
            with self.subTest(date_str=date_str):
                result = self.parser._parse_date(date_str)
                self.assertIsNone(result)
    
    def test_is_valid_license_number(self):
        """Test license number validation."""
        # Valid license numbers
        valid_licenses = [
            "D1234567",
            "S123456789",
            "ABC123456",
            "12345678",
        ]
        
        for license_num in valid_licenses:
            with self.subTest(license_num=license_num):
                self.assertTrue(self.parser._is_valid_license_number(license_num))
        
        # Invalid license numbers
        invalid_licenses = [
            "",
            "ABC",  # Too short
            "ABCDEFGHIJK1234567890",  # Too long
            "COMMERCIAL",  # False positive
            "LICENSE",  # False positive
            "ABCDEFGH",  # No digits
        ]
        
        for license_num in invalid_licenses:
            with self.subTest(license_num=license_num):
                self.assertFalse(self.parser._is_valid_license_number(license_num))
    
    def test_calculate_confidence(self):
        """Test confidence calculation logic."""
        # High confidence: name + expiration
        cdl_data = CDLData(
            driver_name="John Smith",
            expiration_date=datetime(2025, 12, 25),
            license_number="D1234567",
            license_class="A"
        )
        confidence = self.parser._calculate_confidence(cdl_data, {})
        self.assertGreaterEqual(confidence, 0.95)
        
        # Medium confidence: name + other fields
        cdl_data = CDLData(
            driver_name="John Smith",
            license_number="D1234567",
            license_class="A"
        )
        confidence = self.parser._calculate_confidence(cdl_data, {})
        self.assertGreaterEqual(confidence, 0.70)
        self.assertLess(confidence, 0.95)
        
        # Low confidence: few fields
        cdl_data = CDLData(
            license_class="A",
            address="123 Main St"
        )
        confidence = self.parser._calculate_confidence(cdl_data, {})
        self.assertLess(confidence, 0.70)
        
        # Very low confidence: no critical fields
        cdl_data = CDLData()
        confidence = self.parser._calculate_confidence(cdl_data, {})
        self.assertLessEqual(confidence, 0.20)
    
    def test_is_cdl_verified(self):
        """Test CDL verification logic."""
        # Valid CDL
        future_date = datetime.now() + timedelta(days=90)
        cdl_data = CDLData(
            driver_name="John Smith",
            expiration_date=future_date
        )
        self.assertTrue(self.parser._is_cdl_verified(cdl_data))
        
        # CDL expiring soon
        soon_date = datetime.now() + timedelta(days=20)
        cdl_data = CDLData(
            driver_name="John Smith",
            expiration_date=soon_date
        )
        self.assertFalse(self.parser._is_cdl_verified(cdl_data))
        
        # Missing name
        cdl_data = CDLData(
            expiration_date=future_date
        )
        self.assertFalse(self.parser._is_cdl_verified(cdl_data))
        
        # Missing expiration
        cdl_data = CDLData(
            driver_name="John Smith"
        )
        self.assertFalse(self.parser._is_cdl_verified(cdl_data))
    
    def test_clean_address(self):
        """Test address cleaning."""
        # Multi-line address
        address = "123 Main St\nCity, ST 12345"
        cleaned = self.parser._clean_address(address)
        self.assertEqual(cleaned, "123 Main St City, ST 12345")
        
        # Address with extra spaces
        address = "  123   Main  St   "
        cleaned = self.parser._clean_address(address)
        self.assertEqual(cleaned, "123 Main St")
    
    def test_cdl_parsing_integration(self):
        """Test full CDL parsing with sample text."""
        # Test sample CDL text that should result in cdl_verified=True
        sample_text = """
        COMMERCIAL DRIVER LICENSE
        NAME: JOHN SMITH
        LICENSE: D1234567
        CLASS: A
        EXPIRES: 12/31/2025
        ADDRESS: 123 MAIN ST
        CITY: ANYTOWN
        STATE: CA
        """
        
        result = self.parser.parse(sample_text)
        
        # Verify basic parsing worked
        self.assertIsNotNone(result.data.driver_name)
        self.assertIsNotNone(result.data.license_number)
        self.assertIsNotNone(result.data.expiration_date)
        self.assertIsNotNone(result.data.license_class)
        
        # Should have reasonable confidence
        self.assertGreater(result.confidence, 0.7)
        
        # Should be verified if expiration is far enough in future
        if result.data.expiration_date and result.data.expiration_date > datetime.now() + timedelta(days=30):
            self.assertTrue(result.cdl_verified)
    
    def test_cdl_parsing_expired(self):
        """Test CDL parsing with expired license."""
        # Test sample with expired CDL that should result in cdl_verified=False
        sample_text = """
        COMMERCIAL DRIVER LICENSE
        NAME: JANE DOE
        LICENSE: S987654321
        CLASS: B
        EXPIRES: 01/31/2023
        ADDRESS: 456 ELM ST
        """
        
        result = self.parser.parse(sample_text)
        
        # Should parse basic info
        self.assertIsNotNone(result.data.driver_name)
        self.assertIsNotNone(result.data.license_number)
        
        # Should not be verified due to expiration
        self.assertFalse(result.cdl_verified)


if __name__ == '__main__':
    print("🧪 CDL PARSER UNIT TESTS")
    print("=" * 50)
    
    # Run tests
    unittest.main(verbosity=2) 
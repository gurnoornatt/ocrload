#!/usr/bin/env python3
"""
Unit Tests for Rate Confirmation Parser

Tests individual methods and components of the RateConfirmationParser
with mocked inputs. Focuses on specific parsing logic validation.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from app.services.document_parsers.rate_confirmation_parser import (
    RateConfirmationParser,
    RateConfirmationParsingResult
)
from app.models.database import RateConData


class TestRateConfirmationParser:
    """Unit tests for Rate Confirmation parser individual methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = RateConfirmationParser()
    
    def test_initialization(self):
        """Test parser initialization and regex compilation."""
        assert self.parser is not None
        assert hasattr(self.parser, 'rate_patterns')
        assert hasattr(self.parser, 'location_patterns')
        assert hasattr(self.parser, 'date_patterns')
        assert len(self.parser.rate_patterns) > 0
        assert len(self.parser.location_patterns) > 0
        assert len(self.parser.date_patterns) > 0
    
    def test_rate_amount_extraction(self):
        """Test rate amount extraction with various formats."""
        test_cases = [
            ("Rate: $2,500.00", 250000),  # $2,500 -> 250000 cents
            ("Total Amount: $1,250", 125000),  # $1,250 -> 125000 cents
            ("Pay: $3,000", 300000),  # $3,000 -> 300000 cents (realistic rate)
            ("$1,500.50", 150050),  # $1,500.50 -> 150050 cents
            ("2000 dollars", 200000),  # 2000 dollars -> 200000 cents
            ("No rate here", None),  # No rate found
            ("Rate: invalid", None),  # Invalid rate format
            ("Pay: 25", None),  # Too low - unrealistic rate
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_rate_amount(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_location_extraction(self):
        """Test origin and destination location extraction."""
        test_cases = [
            # Explicit markers
            ("FROM: Chicago, IL\nTO: Detroit, MI", ("Chicago, IL", "Detroit, MI")),
            ("Origin: Los Angeles, CA\nDestination: Phoenix, AZ", ("Los Angeles, CA", "Phoenix, AZ")),
            ("Pickup: Houston, TX\nDelivery: Dallas, TX", ("Houston, TX", "Dallas, TX")),
            
            # "From X to Y" pattern
            ("From Chicago, IL to Detroit, MI", ("Chicago, IL", "Detroit, MI")),
            ("from Atlanta, GA to Miami, FL", ("Atlanta, GA", "Miami, FL")),
            
            # Generic patterns - first found is origin, second is destination
            ("Denver, CO Seattle, WA", ("Denver, CO", "Seattle, WA")),
            ("Denver, CO", ("Denver, CO", None)),  # Only one location
            
            # No locations
            ("No locations here", (None, None)),
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_locations(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_date_extraction(self):
        """Test pickup and delivery date extraction."""
        test_cases = [
            ("Pickup: 01/15/2025\nDelivery: 01/16/2025", 
             (datetime(2025, 1, 15), datetime(2025, 1, 16))),
            ("Load Date: 12-25-2024\nUnload: 12-26-2024", 
             (datetime(2024, 12, 25), datetime(2024, 12, 26))),
            ("01/01/2025", (datetime(2025, 1, 1), None)),  # Only pickup date
            ("No dates here", (None, None)),
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_dates(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_weight_extraction(self):
        """Test weight extraction with various formats."""
        test_cases = [
            ("Weight: 45,000 lbs", 45000.0),
            ("45000 pounds", 45000.0),
            ("Weight 25,500", 25500.0),
            ("80000 lbs", 80000.0),  # Max reasonable weight
            ("50 lbs", None),  # Too light
            ("100000 lbs", None),  # Too heavy
            ("No weight here", None),
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_weight(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_commodity_extraction(self):
        """Test commodity description extraction."""
        test_cases = [
            ("Commodity: Steel Coils", "Steel Coils"),
            ("Product: Auto Parts", "Auto Parts"),
            ("Freight: General Merchandise", "General Merchandise"),
            ("Description: Electronics", "Electronics"),
            ("Commodity: AB", None),  # Too short
            ("Commodity: " + "A" * 101, None),  # Too long
            ("No commodity here", None),
        ]
        
        for text, expected in test_cases:
            details = {}
            result = self.parser._extract_commodity(text, details)
            assert result == expected, f"Failed for '{text}': expected {expected}, got {result}"
    
    def test_date_parsing(self):
        """Test date parsing with various formats."""
        test_cases = [
            ("01/15/2025", datetime(2025, 1, 15)),
            ("12-31-2025", datetime(2025, 12, 31)),
            ("01/15/25", datetime(2025, 1, 15)),
            ("2025/01/15", datetime(2025, 1, 15)),
            ("2025-01-15", datetime(2025, 1, 15)),
            ("invalid_date", None),
        ]
        
        for date_str, expected in test_cases:
            result = self.parser._parse_date(date_str)
            assert result == expected, f"Failed for '{date_str}': expected {expected}, got {result}"
    
    def test_confidence_calculation(self):
        """Test confidence score calculation logic."""
        # High confidence: rate + both locations + dates
        full_ratecon = RateConData(
            rate_amount=250000,  # $2,500
            origin="Chicago, IL",
            destination="Detroit, MI",
            pickup_date=datetime(2025, 1, 15),
            delivery_date=datetime(2025, 1, 16),
            weight=45000.0,
            commodity="Steel Coils"
        )
        confidence = self.parser._calculate_confidence(full_ratecon, {})
        assert confidence >= 0.90, f"Full rate confirmation should have high confidence: {confidence}"
        
        # Good confidence: rate + both locations
        good_ratecon = RateConData(
            rate_amount=250000,
            origin="Chicago, IL",
            destination="Detroit, MI"
        )
        confidence = self.parser._calculate_confidence(good_ratecon, {})
        assert 0.80 <= confidence < 0.90, f"Good rate confirmation should have good confidence: {confidence}"
        
        # Medium confidence: rate + one location
        medium_ratecon = RateConData(
            rate_amount=250000,
            origin="Chicago, IL"
        )
        confidence = self.parser._calculate_confidence(medium_ratecon, {})
        assert 0.65 <= confidence < 0.80, f"Medium rate confirmation should have medium confidence: {confidence}"
        
        # Low confidence: rate only
        low_ratecon = RateConData(
            rate_amount=250000
        )
        confidence = self.parser._calculate_confidence(low_ratecon, {})
        assert 0.50 <= confidence < 0.70, f"Low rate confirmation should have low confidence: {confidence}"
    
    def test_ratecon_verified_threshold(self):
        """Test ratecon_verified flag setting based on requirements."""
        # High confidence with required fields should be verified
        verified_ratecon = RateConData(
            rate_amount=250000,
            origin="Chicago, IL",
            destination="Detroit, MI",
            pickup_date=datetime(2025, 1, 15)
        )
        confidence = 0.90
        is_verified = self.parser._is_ratecon_verified(verified_ratecon, confidence)
        assert is_verified is True, "Should be verified with high confidence and required fields"
        
        # Missing required fields should not be verified
        incomplete_ratecon = RateConData(
            rate_amount=250000,
            origin="Chicago, IL"
            # Missing destination
        )
        confidence = 0.90
        is_verified = self.parser._is_ratecon_verified(incomplete_ratecon, confidence)
        assert is_verified is False, "Should not be verified without required fields"
        
        # Low confidence should not be verified
        low_conf_ratecon = RateConData(
            rate_amount=250000,
            origin="Chicago, IL",
            destination="Detroit, MI"
        )
        confidence = 0.70  # Below RATECON_VERIFIED_THRESHOLD (0.80)
        is_verified = self.parser._is_ratecon_verified(low_conf_ratecon, confidence)
        assert is_verified is False, "Should not be verified with low confidence"
    
    def test_parse_basic_functionality(self):
        """Test basic parse functionality with simple rate confirmation."""
        test_text = """
        RATE CONFIRMATION
        
        Rate: $2,500.00
        From: Chicago, IL
        To: Detroit, MI
        Pickup: 01/15/2025
        Delivery: 01/16/2025
        Weight: 45,000 lbs
        Commodity: Steel Coils
        """
        
        result = self.parser.parse(test_text)
        
        assert isinstance(result, RateConfirmationParsingResult)
        assert result.data.rate_amount == 250000  # $2,500 in cents
        assert result.data.origin == "Chicago, IL"
        assert result.data.destination == "Detroit, MI"
        assert result.data.pickup_date == datetime(2025, 1, 15)
        assert result.data.delivery_date == datetime(2025, 1, 16)
        assert result.data.weight == 45000.0
        assert result.data.commodity == "Steel Coils"
        assert result.confidence >= 0.90
        assert result.ratecon_verified is True
    
    def test_parse_minimal_content(self):
        """Test parsing with minimal rate confirmation content."""
        test_text = "Rate: $1,500 From Chicago, IL to Detroit, MI"
        
        result = self.parser.parse(test_text)
        
        assert result.data.rate_amount == 150000  # $1,500 in cents
        assert result.data.origin == "Chicago, IL"
        assert result.data.destination == "Detroit, MI"
        assert result.confidence >= 0.70  # Should still be medium confidence
        assert result.ratecon_verified is True
    
    def test_parse_empty_content(self):
        """Test parsing with empty or invalid content."""
        test_cases = ["", "   ", "No rate confirmation content here"]
        
        for test_text in test_cases:
            result = self.parser.parse(test_text)
            
            assert isinstance(result, RateConfirmationParsingResult)
            assert result.confidence <= 0.50  # Should be low confidence
            assert result.ratecon_verified is False
    
    @patch('app.services.document_parsers.rate_confirmation_parser.PDF_AVAILABLE', False)
    def test_parse_pdf_without_pdfplumber(self):
        """Test PDF parsing when pdfplumber is not available."""
        pdf_content = b"dummy pdf content"
        
        result = self.parser.parse_pdf(pdf_content)
        
        assert isinstance(result, RateConfirmationParsingResult)
        assert result.confidence == 0.0
        assert result.ratecon_verified is False
        assert 'pdfplumber not available' in result.extraction_details['error']
    
    def test_parse_from_ocr_result(self):
        """Test parsing from OCR service result format."""
        ocr_result = {
            'full_text': 'Rate: $2,000 From Houston, TX To Dallas, TX',
            'average_confidence': 0.95,
            'extraction_method': 'datalab_api'
        }
        
        result = self.parser.parse_from_ocr_result(ocr_result)
        
        assert isinstance(result, RateConfirmationParsingResult)
        assert result.data.rate_amount == 200000  # $2,000 in cents
        assert result.data.origin == "Houston, TX"
        assert result.data.destination == "Dallas, TX"
    
    def test_parse_from_ocr_result_with_pages(self):
        """Test parsing from OCR result with pages format."""
        ocr_result = {
            'pages': [
                {'text': 'Rate: $3,000'},
                {'text': 'From Atlanta, GA To Miami, FL'}
            ],
            'average_confidence': 0.88
        }
        
        result = self.parser.parse_from_ocr_result(ocr_result)
        
        assert result.data.rate_amount == 300000  # $3,000 in cents
        assert result.data.origin == "Atlanta, GA"
        assert result.data.destination == "Miami, FL"
    
    def test_parse_from_empty_ocr_result(self):
        """Test parsing from empty OCR result."""
        ocr_result = {'full_text': '', 'pages': []}
        
        result = self.parser.parse_from_ocr_result(ocr_result)
        
        assert result.confidence == 0.0
        assert result.ratecon_verified is False
        assert 'No text found in OCR result' in result.extraction_details['error']


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 
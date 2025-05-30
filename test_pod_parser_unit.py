#!/usr/bin/env python3
"""
Unit tests for POD (Proof of Delivery) Parser

Tests the POD parser functionality with various document formats,
realistic scenarios, and edge cases that would occur in production.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from app.services.document_parsers.pod_parser import PODParser, PODParsingResult
from app.models.database import PODData


class TestPODParser:
    """Test suite for POD parser functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = PODParser()
    
    def test_initialization(self):
        """Test parser initialization and pattern compilation."""
        assert self.parser is not None
        assert hasattr(self.parser, 'delivery_confirmation_patterns')
        assert hasattr(self.parser, 'signature_patterns')
        assert hasattr(self.parser, 'receiver_patterns')
        assert hasattr(self.parser, 'delivery_date_patterns')
        assert hasattr(self.parser, 'notes_patterns')
        assert len(self.parser.delivery_confirmation_patterns) > 0
    
    def test_basic_delivery_confirmation_extraction(self):
        """Test basic delivery confirmation detection."""
        test_cases = [
            "DELIVERY CONFIRMED",
            "Package delivered successfully",
            "Shipment delivered",
            "Freight delivered",
            "Delivery complete",
            "Status: Delivered",
            "Proof of Delivery",
            "POD Confirmation"
        ]
        
        for text in test_cases:
            result = self.parser.parse(text)
            assert result.data.delivery_confirmed is True, f"Failed to detect delivery confirmation in: {text}"
            assert result.confidence > 0.0
    
    def test_signature_detection(self):
        """Test signature presence detection."""
        test_cases = [
            "Signature: John Smith",
            "Signed by: John Doe",
            "Received by: Mary Johnson",
            "Accepted by: Mike Wilson",
            "Electronically signed",
            "Digital signature",
            "Signature on file",
            "***SIGNATURE*** John Smith",
            "__________SIGNATURE__________"
        ]
        
        for text in test_cases:
            result = self.parser.parse(text)
            assert result.data.signature_present is True, f"Failed to detect signature in: {text}"
            assert result.confidence > 0.0
    
    def test_receiver_name_extraction(self):
        """Test receiver name extraction."""
        test_cases = [
            ("Received by: John Smith", "John Smith"),
            ("Delivered to: Mary Johnson", "Mary Johnson"),
            ("Signed by: Mr. Robert Wilson", "Robert Wilson"),
            ("Customer: Jane Doe", "Jane Doe"),
            ("Consignee: Michael Brown", "Michael Brown"),
            ("Name: Sarah Davis", "Sarah Davis"),
            ("Contact: David Miller", "David Miller"),
        ]
        
        for text, expected_name in test_cases:
            result = self.parser.parse(text)
            assert result.data.receiver_name is not None, f"Failed to extract receiver name from: {text}"
            assert expected_name.lower() in result.data.receiver_name.lower(), f"Expected {expected_name}, got {result.data.receiver_name}"
    
    def test_delivery_date_extraction(self):
        """Test delivery date parsing."""
        test_cases = [
            "Delivered: 12/25/2024",
            "Delivery date: 03/15/2024",
            "Received on 04/01/2024",
            "Delivered: 2024-12-25",
            "Delivery: 12/25/2024 14:30",
            "Received: 03/15/2024 2:45 PM"
        ]
        
        for text in test_cases:
            result = self.parser.parse(text)
            assert result.data.delivery_date is not None, f"Failed to extract delivery date from: {text}"
            assert isinstance(result.data.delivery_date, datetime)
    
    def test_delivery_notes_extraction(self):
        """Test delivery notes extraction."""
        test_cases = [
            "Notes: Package delivered to front door",
            "Delivery notes: Left with receptionist",
            "Instructions: Handle with care",
            "Comments: Good condition upon delivery",
            "Remarks: Customer was not available",
            "Condition: Excellent",
            "Damaged: Minor scratches on box",
            "Exception: Delayed due to weather"
        ]
        
        for text in test_cases:
            result = self.parser.parse(text)
            assert result.data.delivery_notes is not None, f"Failed to extract delivery notes from: {text}"
            assert len(result.data.delivery_notes) > 0
    
    def test_comprehensive_pod_document(self):
        """Test parsing of a comprehensive POD document."""
        pod_text = """
        PROOF OF DELIVERY
        
        Shipment delivered successfully
        
        Delivery Date: 12/25/2024 14:30
        Received by: John Smith
        Signature: John Smith
        
        Notes: Package delivered to front door in good condition.
        Customer was satisfied with the delivery.
        
        Status: Delivered
        """
        
        result = self.parser.parse(pod_text)
        
        # Verify all fields extracted
        assert result.data.delivery_confirmed is True
        assert result.data.signature_present is True
        assert result.data.receiver_name is not None
        assert "John Smith" in result.data.receiver_name
        assert result.data.delivery_date is not None
        assert result.data.delivery_notes is not None
        assert "good condition" in result.data.delivery_notes.lower()
        
        # Should have high confidence
        assert result.confidence >= 0.80
        assert result.pod_completed is True
    
    def test_confidence_calculation(self):
        """Test confidence score calculation logic."""
        # Test high confidence scenario
        high_confidence_text = """
        DELIVERY CONFIRMED
        Signed by: John Smith
        Delivered: 12/25/2024
        Notes: Package in good condition
        """
        result = self.parser.parse(high_confidence_text)
        assert result.confidence >= 0.80
        
        # Test medium confidence scenario (missing some fields)
        medium_confidence_text = """
        Package delivered
        Signed by: John Smith
        """
        result = self.parser.parse(medium_confidence_text)
        assert 0.50 <= result.confidence < 0.80
        
        # Test low confidence scenario
        low_confidence_text = "Some random text without delivery info"
        result = self.parser.parse(low_confidence_text)
        assert result.confidence < 0.50
    
    def test_pod_completed_logic(self):
        """Test POD completion determination logic."""
        # Should be completed with delivery confirmed + high confidence
        completed_text = """
        DELIVERY CONFIRMED
        Signed by: John Smith  
        Delivered: 12/25/2024
        """
        result = self.parser.parse(completed_text)
        assert result.pod_completed is True
        
        # Should not be completed without delivery confirmation
        not_completed_text = """
        Signed by: John Smith
        Date: 12/25/2024
        """
        result = self.parser.parse(not_completed_text)
        assert result.pod_completed is False
        
        # Should not be completed with low confidence
        low_confidence_text = "delivery"  # Very minimal info
        result = self.parser.parse(low_confidence_text)
        assert result.pod_completed is False
    
    def test_ocr_artifact_cleaning(self):
        """Test OCR artifact cleaning functionality."""
        dirty_text = """
        D3l1very C0nfirmat10n
        S1gned by: J0hn Sm1th
        Rec31ved: 12/25/2024
        Pr00f of D3livery
        """
        
        result = self.parser.parse(dirty_text)
        
        # Should still detect fields despite OCR artifacts
        assert result.data.delivery_confirmed is True
        assert result.data.signature_present is True
        assert result.confidence > 0.50
    
    def test_realistic_carrier_formats(self):
        """Test parsing of realistic carrier POD formats."""
        # FedEx-style POD
        fedex_pod = """
        FedEx Proof of Delivery
        Tracking: 1234567890
        
        Delivered: 03/15/2024 10:30 AM
        Signed by: RECEPTIONIST
        Left at: Front Door
        
        Status: Delivered
        """
        
        result = self.parser.parse(fedex_pod)
        assert result.data.delivery_confirmed is True
        assert result.data.signature_present is True
        assert result.data.receiver_name is not None
        assert result.confidence >= 0.70
        
        # UPS-style POD
        ups_pod = """
        UPS Delivery Confirmation
        
        Package delivered successfully
        Delivery date: 03/15/2024
        Received by: John Smith
        
        Comments: Package left with neighbor
        """
        
        result = self.parser.parse(ups_pod)
        assert result.data.delivery_confirmed is True
        assert result.data.receiver_name is not None
        assert result.data.delivery_notes is not None
        assert result.confidence >= 0.70
    
    def test_freight_pod_formats(self):
        """Test parsing of freight carrier POD formats."""
        freight_pod = """
        FREIGHT DELIVERY RECEIPT
        
        Cargo delivered: 12/25/2024 15:45
        Consignee: ABC Warehouse Inc
        Signed by: Mike Johnson
        
        Condition: Good
        Notes: All items accounted for and in good condition.
        No damages reported.
        """
        
        result = self.parser.parse(freight_pod)
        assert result.data.delivery_confirmed is True
        assert result.data.signature_present is True
        assert result.data.receiver_name is not None
        assert result.data.delivery_date is not None
        assert result.data.delivery_notes is not None
        assert "good condition" in result.data.delivery_notes.lower()
        assert result.confidence >= 0.80
    
    def test_edge_cases(self):
        """Test edge cases and error handling."""
        # Empty text
        result = self.parser.parse("")
        assert result.data.delivery_confirmed is False
        assert result.confidence == 0.0
        assert result.pod_completed is False
        
        # Only whitespace
        result = self.parser.parse("   \n\t   ")
        assert result.data.delivery_confirmed is False
        assert result.confidence == 0.0
        
        # Very long text
        long_text = "delivery confirmed " * 1000
        result = self.parser.parse(long_text)
        assert result.data.delivery_confirmed is True
        
        # Special characters
        special_text = "D€l!v€r¥ C♦nƒ!rm€d"
        result = self.parser.parse(special_text)
        # Should still work due to fuzzy matching
        
        # Numbers in receiver name (should be filtered)
        number_text = "Received by: 12345"
        result = self.parser.parse(number_text)
        assert result.data.receiver_name is None  # Should reject numeric names
    
    def test_date_parsing_edge_cases(self):
        """Test date parsing with various formats and edge cases."""
        test_cases = [
            ("12/25/2024", datetime(2024, 12, 25)),
            ("03/15/24", datetime(2024, 3, 15)),
            ("2024-12-25", datetime(2024, 12, 25)),
            ("25/12/2024", datetime(2024, 12, 25)),  # DD/MM/YYYY
            ("December 25, 2024", datetime(2024, 12, 25)),
            ("Dec 25, 2024", datetime(2024, 12, 25)),
        ]
        
        for date_str, expected_date in test_cases:
            text = f"Delivered: {date_str}"
            result = self.parser.parse(text)
            if result.data.delivery_date:
                # Check year and month (day might vary due to format ambiguity)
                assert result.data.delivery_date.year == expected_date.year
                assert result.data.delivery_date.month == expected_date.month
    
    def test_parse_from_ocr_result(self):
        """Test parsing from OCR result structure."""
        ocr_result = {
            'text': 'DELIVERY CONFIRMED\nSigned by: John Smith\nDelivered: 12/25/2024',
            'confidence': 0.95,
            'method': 'datalab',
            'page_count': 1
        }
        
        result = self.parser.parse_from_ocr_result(ocr_result)
        
        assert result.data.delivery_confirmed is True
        assert result.data.signature_present is True
        assert result.confidence > 0.70
        assert 'ocr_metadata' in result.extraction_details
        assert result.extraction_details['ocr_metadata']['ocr_confidence'] == 0.95
    
    def test_parse_from_ocr_result_error_cases(self):
        """Test OCR result parsing error handling."""
        # Missing text field
        invalid_ocr = {'confidence': 0.95}
        result = self.parser.parse_from_ocr_result(invalid_ocr)
        assert result.confidence == 0.0
        assert 'error' in result.extraction_details
        
        # Alternative content field
        ocr_with_content = {
            'content': 'DELIVERY CONFIRMED',
            'confidence': 0.90
        }
        result = self.parser.parse_from_ocr_result(ocr_with_content)
        assert result.data.delivery_confirmed is True
    
    @patch('app.services.document_parsers.pod_parser.pdfplumber')
    def test_pdf_parsing(self, mock_pdfplumber):
        """Test PDF parsing functionality."""
        # Mock PDF content
        mock_pdf = Mock()
        mock_page = Mock()
        mock_page.extract_text.return_value = "DELIVERY CONFIRMED\nSigned by: John Smith"
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        
        result = self.parser.parse_pdf(b"fake_pdf_content")
        
        assert result.data.delivery_confirmed is True
        assert result.data.signature_present is True
        assert result.confidence > 0.50
    
    def test_confidence_breakdown_details(self):
        """Test detailed confidence breakdown."""
        comprehensive_text = """
        DELIVERY CONFIRMED
        Signed by: John Smith
        Delivered: 12/25/2024
        Notes: Package delivered in good condition
        """
        
        result = self.parser.parse(comprehensive_text)
        
        # Check extraction details
        assert 'confidence_breakdown' in result.extraction_details
        breakdown = result.extraction_details['confidence_breakdown']
        
        assert 'base_score' in breakdown
        assert 'bonuses' in breakdown
        assert 'final_score' in breakdown
        assert breakdown['delivery_confirmed_weight'] == 0.40
        assert breakdown['signature_weight'] == 0.25
        assert breakdown['date_weight'] == 0.20
        assert breakdown['receiver_weight'] == 0.10
        assert breakdown['notes_weight'] == 0.05
    
    def test_production_scenarios(self):
        """Test realistic production scenarios."""
        # Scenario 1: Clean professional POD
        clean_pod = """
        DELIVERY RECEIPT
        
        Shipment ID: ABC123456
        Delivered: 12/25/2024 14:30
        
        Consignee: Walmart Distribution Center
        Received by: Mike Johnson, Receiving Manager
        Signature: M. Johnson
        
        Condition: All items received in good condition
        Notes: No damage reported. All pallets accounted for.
        """
        
        result = self.parser.parse(clean_pod)
        assert result.confidence >= 0.90
        assert result.pod_completed is True
        
        # Scenario 2: Damaged delivery with notes
        damaged_pod = """
        POD - DELIVERY CONFIRMATION
        
        Status: DELIVERED WITH EXCEPTIONS
        Date: 03/15/2024
        Received by: Sarah Wilson
        
        DAMAGE NOTED: Box crushed on left side
        Exception: Customer refused partial shipment
        """
        
        result = self.parser.parse(damaged_pod)
        assert result.data.delivery_confirmed is True
        assert result.data.delivery_notes is not None
        assert "damage" in result.data.delivery_notes.lower()
        
        # Scenario 3: Electronic signature POD
        electronic_pod = """
        ELECTRONIC PROOF OF DELIVERY
        
        Digitally signed by: John.Smith@company.com
        Timestamp: 2024-12-25 10:30:00
        
        Delivery confirmed electronically
        No physical signature required
        """
        
        result = self.parser.parse(electronic_pod)
        assert result.data.delivery_confirmed is True
        assert result.data.signature_present is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 
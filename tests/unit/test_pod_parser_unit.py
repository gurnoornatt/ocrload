#!/usr/bin/env python3
"""
POD Parser Unit Tests

Unit tests for testing specific methods and edge cases in the POD parser.
These are isolated unit tests that don't depend on external services.
"""

import unittest
from datetime import datetime
import sys
import os

# Add the app directory to the path to avoid service imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Import only the parser and data model directly
from app.services.document_parsers.pod_parser import PODParser
from app.models.database import PODData


class TestPODParserMethods(unittest.TestCase):
    """Unit tests for POD parser methods."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.parser = PODParser()
    
    def test_pod_parsing_complete(self):
        """Test POD parsing with complete delivery confirmation."""
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
        self.assertTrue(result.data.delivery_confirmed)
        self.assertTrue(result.data.signature_present)
        self.assertIsNotNone(result.data.receiver_name)
        self.assertIn("John Smith", result.data.receiver_name)
        self.assertIsNotNone(result.data.delivery_date)
        self.assertIsNotNone(result.data.delivery_notes)
        self.assertIn("good condition", result.data.delivery_notes.lower())
        
        # Should have high confidence
        self.assertGreater(result.confidence, 0.7)
        self.assertTrue(result.pod_completed)
    
    def test_pod_parsing_incomplete(self):
        """Test POD parsing with incomplete information."""
        incomplete_text = """
        Package shipment info
        Signed by: John Smith
        Date: 12/25/2024
        """
        
        result = self.parser.parse(incomplete_text)
        
        # Should detect signature due to "Signed by" pattern
        self.assertTrue(result.data.signature_present)
        
        # Should parse the receiver name from "Signed by: John Smith"
        if result.data.receiver_name:
            self.assertIn("John Smith", result.data.receiver_name)
        
        # Should not be marked as completed due to lack of delivery confirmation  
        self.assertFalse(result.pod_completed)
    
    def test_pod_parsing_minimal(self):
        """Test POD parsing with minimal delivery information."""
        minimal_text = """
        Delivery status: Delivered
        No additional information available.
        """
        
        result = self.parser.parse(minimal_text)
        
        # Should detect delivery confirmation
        self.assertTrue(result.data.delivery_confirmed)
        
        # Should have lower confidence due to missing fields
        self.assertLess(result.confidence, 0.7)
    
    def test_pod_parsing_signature_variations(self):
        """Test POD parsing with various signature formats."""
        signature_texts = [
            "Signature: John Doe",
            "Signed by: Mary Johnson", 
            "Received by: Mike Wilson",
            "Electronically signed by system",
            "Digital signature verified"
        ]
        
        for text in signature_texts:
            with self.subTest(text=text):
                full_text = f"""
                PROOF OF DELIVERY
                Delivery confirmed
                {text}
                """
                result = self.parser.parse(full_text)
                self.assertTrue(result.data.signature_present)
                self.assertTrue(result.data.delivery_confirmed)
    
    def test_pod_parsing_date_variations(self):
        """Test POD parsing with various date formats."""
        date_texts = [
            "Delivered: 12/25/2024",
            "Delivery date: 03/15/2024", 
            "Received on 04/01/2024",
            "Delivered: 2024-12-25",
            "Delivery: 01-05-2024 10:30 AM"
        ]
        
        for text in date_texts:
            with self.subTest(text=text):
                full_text = f"""
                PROOF OF DELIVERY
                Delivery confirmed
                {text}
                """
                result = self.parser.parse(full_text)
                self.assertTrue(result.data.delivery_confirmed)
                self.assertIsNotNone(result.data.delivery_date)
    
    def test_pod_parsing_notes_variations(self):
        """Test POD parsing with various notes formats."""
        notes_texts = [
            "Notes: Package delivered to front door",
            "Delivery notes: Left with receptionist",
            "Instructions: Handle with care", 
            "Comments: Good condition upon delivery",
            "Remarks: Customer not present, left secure"
        ]
        
        for text in notes_texts:
            with self.subTest(text=text):
                full_text = f"""
                PROOF OF DELIVERY
                Delivery confirmed
                {text}
                """
                result = self.parser.parse(full_text)
                self.assertTrue(result.data.delivery_confirmed)
                self.assertIsNotNone(result.data.delivery_notes)
    
    def test_pod_parsing_no_delivery_confirmation(self):
        """Test POD parsing when no delivery confirmation is found."""
        no_delivery_text = """
        Shipment information only
        Customer: John Smith
        Date: 12/25/2024
        Random text without any confirmation words
        """
        
        result = self.parser.parse(no_delivery_text)
        
        # Should not confirm delivery 
        self.assertFalse(result.data.delivery_confirmed)
        self.assertFalse(result.pod_completed)
        
        # Should have low confidence
        self.assertLess(result.confidence, 0.5)
    
    def test_pod_parsing_empty_text(self):
        """Test POD parsing with empty or whitespace text."""
        empty_texts = ["", "   ", "\n\n\t  \n"]
        
        for text in empty_texts:
            with self.subTest(text=repr(text)):
                result = self.parser.parse(text)
                self.assertFalse(result.data.delivery_confirmed)
                self.assertFalse(result.data.signature_present)
                self.assertIsNone(result.data.receiver_name)
                self.assertIsNone(result.data.delivery_date)
                self.assertIsNone(result.data.delivery_notes)
                self.assertEqual(result.confidence, 0.0)
                self.assertFalse(result.pod_completed)
    
    def test_pod_parsing_confidence_scoring(self):
        """Test confidence scoring logic with different completeness levels."""
        # High completeness
        high_complete_text = """
        PROOF OF DELIVERY
        Delivery confirmed successfully
        Signature: John Smith
        Received by: John Smith
        Delivery date: 12/25/2024
        Notes: Package in excellent condition
        """
        result_high = self.parser.parse(high_complete_text)
        
        # Medium completeness
        medium_complete_text = """
        PROOF OF DELIVERY
        Delivery confirmed
        Signature: John Smith
        """
        result_medium = self.parser.parse(medium_complete_text)
        
        # Low completeness
        low_complete_text = """
        Some document
        Delivery confirmed
        """
        result_low = self.parser.parse(low_complete_text)
        
        # Verify confidence ordering
        self.assertGreater(result_high.confidence, result_medium.confidence)
        self.assertGreater(result_medium.confidence, result_low.confidence)
        
        # High completeness should have high confidence
        self.assertGreater(result_high.confidence, 0.7)
        
        # Low completeness should have low confidence
        self.assertLess(result_low.confidence, 0.7)


if __name__ == '__main__':
    print("🧪 POD PARSER UNIT TESTS")
    print("=" * 50)
    
    # Run tests
    unittest.main(verbosity=2) 
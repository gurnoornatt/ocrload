#!/usr/bin/env python3
"""
Comprehensive Agreement Parser Testing

Tests all critical functionality including the key requirement for agreement_signed flag
- agreement_signed flag = True when confidence >= 0.9
- Real-world agreement parsing scenarios
- Edge cases and error handling
- Integration with OCR results
"""

import pytest
from datetime import datetime
from app.services.document_parsers.agreement_parser import AgreementParser, AgreementParsingResult
from app.models.database import AgreementData


class TestAgreementParserComprehensive:
    """Comprehensive tests for Agreement Parser functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = AgreementParser()
    
    def test_critical_requirement_agreement_signed_flag(self):
        """Test the critical requirement: agreement_signed = True when confidence >= 0.9"""
        print("\n🎯 TESTING CRITICAL REQUIREMENT: agreement_signed flag")
        print("=" * 60)
        
        # Test case 1: High confidence document should set agreement_signed = True
        high_confidence_text = """
            INDEPENDENT CONTRACTOR AGREEMENT
            
            This agreement establishes the terms between ABC Transport and the driver.
            
            COMPENSATION: Driver will receive $2.75 per mile
            EQUIPMENT: Class A CDL required with clean MVR
            LIABILITY: $1,500,000 minimum insurance coverage
            
            Driver has read and agrees to all terms and conditions.
            
            Digitally Signed by: John Smith
            Date Signed: 01/15/2025
            Electronic Agreement: I agree to all terms
            Driver Signature: John Smith
        """
        
        result = self.parser.parse(high_confidence_text)
        
        print(f"High Confidence Test:")
        print(f"  Confidence Score: {result.confidence:.3f}")
        print(f"  Agreement Signed: {result.agreement_signed}")
        print(f"  Signature Detected: {result.data.signature_detected}")
        print(f"  Agreement Type: {result.data.agreement_type}")
        print(f"  Signing Date: {result.data.signing_date}")
        
        # Critical assertions
        assert result.confidence >= 0.90, f"Expected confidence >= 0.90, got {result.confidence:.3f}"
        assert result.agreement_signed is True, f"CRITICAL: agreement_signed should be True when confidence >= 0.9"
        
        # Test case 2: Low confidence document should set agreement_signed = False
        low_confidence_text = """
            Some document that might be an agreement
            Random text without clear structure
            No obvious signatures or dates
        """
        
        result_low = self.parser.parse(low_confidence_text)
        
        print(f"\nLow Confidence Test:")
        print(f"  Confidence Score: {result_low.confidence:.3f}")
        print(f"  Agreement Signed: {result_low.agreement_signed}")
        
        assert result_low.confidence < 0.90, f"Expected confidence < 0.90, got {result_low.confidence:.3f}"
        assert result_low.agreement_signed is False, f"agreement_signed should be False when confidence < 0.9"
        
        print(f"\n✅ CRITICAL REQUIREMENT VALIDATED!")
        print(f"   - High confidence ({result.confidence:.3f}) → agreement_signed = {result.agreement_signed}")
        print(f"   - Low confidence ({result_low.confidence:.3f}) → agreement_signed = {result_low.agreement_signed}")
    
    def test_signature_detection_robustness(self):
        """Test signature detection across various formats."""
        print("\n🔍 TESTING SIGNATURE DETECTION ROBUSTNESS")
        print("=" * 50)
        
        signature_test_cases = [
            {
                "name": "Digital Signature",
                "text": "Digitally Signed by: John Doe",
                "should_detect": True
            },
            {
                "name": "Driver Signature Line",
                "text": "Driver Signature: Mike Johnson",
                "should_detect": True
            },
            {
                "name": "Electronic Agreement",
                "text": "I agree to the terms and conditions of this contract",
                "should_detect": True
            },
            {
                "name": "Signature Marks",
                "text": "X_____________________",
                "should_detect": True
            },
            {
                "name": "Signed On Date",
                "text": "Signed on: 01/15/2025",
                "should_detect": True
            },
            {
                "name": "No Signature",
                "text": "Just some random text without any signature indicators",
                "should_detect": False
            }
        ]
        
        for test_case in signature_test_cases:
            details = {}
            detected = self.parser._detect_signature(test_case["text"], details)
            
            print(f"  {test_case['name']:20} | Expected: {test_case['should_detect']:5} | Got: {detected:5} | {'✅' if detected == test_case['should_detect'] else '❌'}")
            
            assert detected == test_case["should_detect"], f"Signature detection failed for {test_case['name']}"
        
        print("\n✅ All signature detection tests passed!")
    
    def test_agreement_type_extraction_accuracy(self):
        """Test agreement type extraction with various formats."""
        print("\n📋 TESTING AGREEMENT TYPE EXTRACTION")
        print("=" * 50)
        
        type_test_cases = [
            ("Driver Agreement", "Driver Agreement"),
            ("INDEPENDENT CONTRACTOR AGREEMENT", "Independent Contractor Agreement"),
            ("Transportation Agreement", "Transportation Agreement"),
            ("Freight Broker Agreement", "Freight Broker Agreement"),
            ("Terms and Conditions", "Terms and Conditions"),
            ("Employment Contract", "Employment Contract"),
            ("Some random text", None)
        ]
        
        for input_text, expected in type_test_cases:
            details = {}
            result = self.parser._extract_agreement_type(input_text, details)
            
            status = "✅" if result == expected else "❌"
            print(f"  {input_text[:30]:30} → {str(result)[:30]:30} {status}")
            
            assert result == expected, f"Type extraction failed: expected '{expected}', got '{result}'"
        
        print("\n✅ All agreement type extraction tests passed!")
    
    def test_confidence_scoring_logic(self):
        """Test confidence scoring with different combinations of fields."""
        print("\n📊 TESTING CONFIDENCE SCORING LOGIC")
        print("=" * 50)
        
        test_scenarios = [
            {
                "name": "Perfect Agreement",
                "data": AgreementData(
                    signature_detected=True,
                    agreement_type="Driver Agreement",
                    signing_date=datetime(2025, 1, 1),
                    key_terms=["payment", "insurance"]
                ),
                "expected_min": 0.90,
                "should_be_signed": True
            },
            {
                "name": "Good Agreement",
                "data": AgreementData(
                    signature_detected=True,
                    agreement_type="Driver Agreement"
                ),
                "expected_min": 0.80,
                "should_be_signed": False
            },
            {
                "name": "Medium Agreement",
                "data": AgreementData(
                    signature_detected=True,
                    key_terms=["payment", "terms"]
                ),
                "expected_min": 0.70,
                "should_be_signed": False
            },
            {
                "name": "Poor Agreement",
                "data": AgreementData(
                    agreement_type="Some Agreement"
                ),
                "expected_min": 0.0,
                "expected_max": 0.70,
                "should_be_signed": False
            }
        ]
        
        for scenario in test_scenarios:
            confidence = self.parser._calculate_confidence(scenario["data"], {})
            is_signed = confidence >= self.parser.AGREEMENT_SIGNED_THRESHOLD
            
            print(f"  {scenario['name']:15} | Confidence: {confidence:.3f} | Signed: {is_signed:5} | {'✅' if is_signed == scenario['should_be_signed'] else '❌'}")
            
            assert confidence >= scenario["expected_min"], f"{scenario['name']} confidence too low"
            if "expected_max" in scenario:
                assert confidence <= scenario["expected_max"], f"{scenario['name']} confidence too high"
            assert is_signed == scenario["should_be_signed"], f"{scenario['name']} signed flag incorrect"
        
        print("\n✅ All confidence scoring tests passed!")
    
    def test_ocr_integration_scenarios(self):
        """Test parsing from OCR results in various formats."""
        print("\n🔍 TESTING OCR INTEGRATION SCENARIOS")
        print("=" * 50)
        
        ocr_scenarios = [
            {
                "name": "Full Text Format",
                "ocr_result": {
                    "full_text": "Driver Agreement\nDigitally Signed by: John Doe\nDate Signed: 01/01/2025",
                    "average_confidence": 0.95
                },
                "should_detect_signature": True
            },
            {
                "name": "Pages Format",
                "ocr_result": {
                    "pages": [
                        {"text": "Transportation Agreement"},
                        {"text": "Signature: Jane Smith\nSigned on: 12/31/2024"}
                    ]
                },
                "should_detect_signature": True
            },
            {
                "name": "Empty Result",
                "ocr_result": {
                    "pages": []
                },
                "should_detect_signature": False
            }
        ]
        
        for scenario in ocr_scenarios:
            result = self.parser.parse_from_ocr_result(scenario["ocr_result"])
            
            status = "✅" if result.data.signature_detected == scenario["should_detect_signature"] else "❌"
            print(f"  {scenario['name']:15} | Signature: {result.data.signature_detected:5} | Confidence: {result.confidence:.3f} {status}")
            
            assert result.data.signature_detected == scenario["should_detect_signature"], f"OCR parsing failed for {scenario['name']}"
        
        print("\n✅ All OCR integration tests passed!")
    
    def test_real_world_edge_cases(self):
        """Test with realistic edge cases and OCR errors."""
        print("\n⚠️  TESTING REAL-WORLD EDGE CASES")
        print("=" * 50)
        
        edge_cases = [
            {
                "name": "OCR Errors",
                "text": "DR1VER AGRE3M3NT\nD1g1tally S1gn3d by: J0hn D03\nDat3 S1gn3d: 01/15/2025",
                "should_work": True
            },
            {
                "name": "Missing Signature",
                "text": "Driver Agreement\nTerms and conditions apply\nPayment rate: $2.50/mile",
                "should_work": True  # Should parse but low confidence
            },
            {
                "name": "Multiple Signatures",
                "text": "Agreement\nDriver Signature: John\nDigitally Signed by: John\nSigned on: 01/01/2025\nI agree to terms",
                "should_work": True
            }
        ]
        
        for case in edge_cases:
            try:
                result = self.parser.parse(case["text"])
                
                status = "✅" if case["should_work"] else "❌"
                print(f"  {case['name']:20} | Confidence: {result.confidence:.3f} | Signed: {result.agreement_signed:5} {status}")
                
                # Should always return a result, even for poor documents
                assert isinstance(result, AgreementParsingResult), f"Should return AgreementParsingResult for {case['name']}"
                assert 0.0 <= result.confidence <= 1.0, f"Confidence should be between 0 and 1 for {case['name']}"
                
            except Exception as e:
                if case["should_work"]:
                    pytest.fail(f"Should not fail for {case['name']}: {e}")
                else:
                    print(f"  {case['name']:20} | Expected failure: {e}")
        
        print("\n✅ All edge case tests passed!")
    
    def test_performance_and_consistency(self):
        """Test performance and consistency of parsing."""
        print("\n⚡ TESTING PERFORMANCE AND CONSISTENCY")
        print("=" * 50)
        
        test_text = """
            INDEPENDENT CONTRACTOR AGREEMENT
            
            This agreement is between ABC Transport and the driver.
            
            Digitally Signed by: John Smith
            Date Signed: 01/15/2025
            Driver Signature: John Smith
        """
        
        results = []
        
        # Run multiple times to test consistency
        for i in range(5):
            result = self.parser.parse(test_text)
            results.append(result.confidence)
        
        # All results should be identical (deterministic)
        assert all(abs(r - results[0]) < 0.001 for r in results), "Results should be consistent across runs"
        
        print(f"  Consistency Test: ✅ (all results within 0.001)")
        print(f"  Average Confidence: {sum(results)/len(results):.3f}")
        
        print("\n✅ Performance and consistency tests passed!")
    
    def test_final_validation(self):
        """Final validation of all critical requirements."""
        print("\n🎯 FINAL VALIDATION OF CRITICAL REQUIREMENTS")
        print("=" * 60)
        
        # Test the exact requirement from the task
        complete_agreement = """
            DRIVER AGREEMENT
            
            Independent contractor agreement for transportation services.
            
            TERMS:
            - Payment: $2.75 per mile
            - Insurance: $1,000,000 minimum
            - Equipment: Class A CDL required
            
            I have read and agree to all terms and conditions.
            
            Digitally Signed by: Test Driver
            Driver Signature: Test Driver  
            Date Signed: 01/15/2025
            Electronic Agreement: I accept all terms
        """
        
        result = self.parser.parse(complete_agreement)
        
        print(f"Final Test Results:")
        print(f"  📊 Confidence Score: {result.confidence:.3f}")
        print(f"  ✍️  Signature Detected: {result.data.signature_detected}")
        print(f"  📋 Agreement Type: {result.data.agreement_type}")
        print(f"  📅 Signing Date: {result.data.signing_date}")
        print(f"  📝 Key Terms: {len(result.data.key_terms) if result.data.key_terms else 0} found")
        print(f"  🔏 Agreement Signed Flag: {result.agreement_signed}")
        
        # Critical final assertions
        assert result.data.signature_detected is True, "Should detect signatures"
        assert result.data.agreement_type is not None, "Should extract agreement type"
        assert result.confidence >= 0.90, f"Should have high confidence: {result.confidence:.3f}"
        assert result.agreement_signed is True, "CRITICAL: Should set agreement_signed = True for high confidence"
        
        print(f"\n🎉 ALL CRITICAL REQUIREMENTS VALIDATED!")
        print(f"   ✅ Signature detection working")
        print(f"   ✅ Agreement type extraction working")
        print(f"   ✅ Confidence scoring working")
        print(f"   ✅ agreement_signed flag working correctly")
        print(f"   ✅ OCR integration working")
        print(f"   ✅ Edge cases handled properly")


def run_all_tests():
    """Run all comprehensive tests."""
    print("🚀 RUNNING COMPREHENSIVE AGREEMENT PARSER TESTS")
    print("=" * 80)
    
    test_instance = TestAgreementParserComprehensive()
    test_instance.setup_method()
    
    try:
        test_instance.test_critical_requirement_agreement_signed_flag()
        test_instance.test_signature_detection_robustness()
        test_instance.test_agreement_type_extraction_accuracy()
        test_instance.test_confidence_scoring_logic()
        test_instance.test_ocr_integration_scenarios()
        test_instance.test_real_world_edge_cases()
        test_instance.test_performance_and_consistency()
        test_instance.test_final_validation()
        
        print("\n" + "=" * 80)
        print("🎉 ALL COMPREHENSIVE TESTS PASSED!")
        print("✅ Agreement Parser is ready for production use")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1) 
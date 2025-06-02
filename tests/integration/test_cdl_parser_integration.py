#!/usr/bin/env python3
"""
CDL Parser Real Integration Tests

Tests the CDL parser with realistic CDL document text samples from various
states and formats. Validates field extraction, confidence scoring, and
verification logic against actual CDL document patterns.
"""

import asyncio
import io
import os
import sys
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont

from app.services.document_parsers import CDLParser
from app.services.ocr_clients import UnifiedOCRClient


def create_cdl_text_samples():
    """Create realistic CDL text samples from different states."""

    # Sample 1: California CDL format
    ca_cdl = """
COMMERCIAL DRIVER LICENSE
STATE OF CALIFORNIA
CLASS A CDL

NAME: JOHN MICHAEL SMITH
LICENSE: D1234567
EXP: 12/25/2025
ADDRESS: 123 MAIN ST
CITY: LOS ANGELES CA 90210

DOB: 01/15/1985
EYES: BRN HAIR: BLK
HEIGHT: 5-11 WEIGHT: 180
"""

    # Sample 2: Texas CDL format
    tx_cdl = """
TEXAS
COMMERCIAL DRIVER LICENSE

SMITH, JOHN MICHAEL
DL: 12345678
CLASS: B
EXPIRES: 06/30/2026

ADDR: 456 OAK AVENUE
HOUSTON TX 77001

ISSUED: 07/01/2021
DOB: 01/15/1985
"""

    # Sample 3: Florida CDL format
    fl_cdl = """
FLORIDA COMMERCIAL DRIVER LICENSE

First: JOHN
Last: SMITH
CDL CLASS: A
LICENSE NUMBER: S123456789

EXPIRATION DATE: 12/15/2025
ADDRESS: 789 PALM STREET
MIAMI FL 33101

RESTRICTIONS: NONE
"""

    # Sample 4: New York CDL format
    ny_cdl = """
NEW YORK STATE
COMMERCIAL DRIVER LICENSE

JOHN M SMITH
LIC: 123456789
CLASS A CDL
EXP: 09/12/2025

789 BROADWAY
NEW YORK NY 10003

DOB: 01/15/1985
SEX: M HGT: 5'11" WT: 180
"""

    # Sample 5: Illinois CDL format (edge case - expires soon)
    il_cdl_expiring = """
ILLINOIS
COMMERCIAL DRIVER LICENSE

NAME: JOHN SMITH
CDL NUMBER: S123456789
CLASS: C
EXPIRES: 12/15/2025

ADDRESS: 321 LAKE SHORE DR
CHICAGO IL 60601
"""

    # Sample 6: Poor quality OCR (missing some fields)
    poor_ocr = """
COMMERCIAL DRIVER LICENSE

JOHN SMITH
CLASS: A

ADDRESS: 123 SOMEWHERE ST
SOMECITY ST 12345

... some illegible text ...
EXP: 12/30/2025
"""

    return {
        "ca_complete": ca_cdl,
        "tx_complete": tx_cdl,
        "fl_complete": fl_cdl,
        "ny_complete": ny_cdl,
        "il_expiring_soon": il_cdl_expiring,
        "poor_ocr": poor_ocr,
    }


def create_cdl_image_with_text(text_content, width=600, height=400):
    """Create a test CDL image with the given text content."""
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)

    try:
        # Try to use a realistic font
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 14)
        header_font = ImageFont.truetype("/System/Library/Fonts/Arial Bold.ttf", 16)
    except:
        # Fallback to default font
        font = ImageFont.load_default()
        header_font = font

    # Draw text line by line
    lines = text_content.strip().split("\n")
    y_position = 20

    for line in lines:
        line = line.strip()
        if not line:
            y_position += 10
            continue

        # Use header font for titles
        current_font = (
            header_font
            if any(
                title in line.upper() for title in ["COMMERCIAL", "LICENSE", "STATE"]
            )
            else font
        )

        draw.text((20, y_position), line, fill="black", font=current_font)
        y_position += 20

        # Don't exceed image bounds
        if y_position > height - 30:
            break

    # Convert to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    return img_bytes.getvalue()


async def test_cdl_parser_text_parsing():
    """Test CDL parser with text samples directly."""
    print("🧪 TESTING CDL PARSER - TEXT PARSING")
    print("=" * 50)

    parser = CDLParser()
    text_samples = create_cdl_text_samples()

    results = {}

    for sample_name, text in text_samples.items():
        print(f"\n📝 Testing: {sample_name}")

        try:
            result = parser.parse(text)

            print("✅ Parsing successful!")
            print(f"📊 Confidence: {result.confidence:.2f}")
            print(f"🔍 CDL Verified: {result.cdl_verified}")
            print(f"👤 Name: {result.data.driver_name}")
            print(f"🆔 License: {result.data.license_number}")
            print(f"📅 Expires: {result.data.expiration_date}")
            print(f"🚛 Class: {result.data.license_class}")
            print(f"🏠 Address: {result.data.address}")
            print(f"🗺️  State: {result.data.state}")

            # Validate results
            fields_found = sum(
                [
                    result.data.driver_name is not None,
                    result.data.license_number is not None,
                    result.data.expiration_date is not None,
                    result.data.license_class is not None,
                    result.data.address is not None,
                    result.data.state is not None,
                ]
            )

            print(f"📈 Fields extracted: {fields_found}/6")

            results[sample_name] = {
                "success": True,
                "confidence": result.confidence,
                "verified": result.cdl_verified,
                "fields_found": fields_found,
                "result": result,
            }

        except Exception as e:
            print(f"❌ Error: {e}")
            results[sample_name] = {"success": False, "error": str(e)}

    return results


async def test_cdl_parser_with_ocr():
    """Test CDL parser with real OCR integration."""
    print("\n\n🔄 TESTING CDL PARSER - WITH OCR INTEGRATION")
    print("=" * 50)

    api_key = os.getenv("DATALAB_API_KEY")
    if not api_key:
        print("❌ DATALAB_API_KEY not set - skipping OCR integration test")
        return {}

    parser = CDLParser()
    text_samples = create_cdl_text_samples()

    # Test with a complete sample
    test_sample = text_samples["ca_complete"]

    try:
        print("📝 Creating CDL image for OCR...")
        cdl_image = create_cdl_image_with_text(test_sample)

        print("🔍 Processing with OCR...")
        async with UnifiedOCRClient() as ocr_client:
            ocr_result = await ocr_client.process_file_content(
                file_content=cdl_image, filename="test_cdl.png", mime_type="image/png"
            )

        print(
            f"✅ OCR completed with confidence: {ocr_result.get('average_confidence', 0):.2f}"
        )

        print("📊 Parsing CDL from OCR result...")
        parsing_result = parser.parse_from_ocr_result(ocr_result)

        print("✅ CDL parsing completed!")
        print(f"📊 Parsing confidence: {parsing_result.confidence:.2f}")
        print(f"🔍 CDL Verified: {parsing_result.cdl_verified}")
        print(f"👤 Name: {parsing_result.data.driver_name}")
        print(f"🆔 License: {parsing_result.data.license_number}")
        print(f"📅 Expires: {parsing_result.data.expiration_date}")
        print(f"🚛 Class: {parsing_result.data.license_class}")

        return {
            "ocr_confidence": ocr_result.get("average_confidence", 0),
            "parsing_confidence": parsing_result.confidence,
            "cdl_verified": parsing_result.cdl_verified,
            "extraction_method": ocr_result.get("extraction_method"),
            "fields_extracted": sum(
                [
                    parsing_result.data.driver_name is not None,
                    parsing_result.data.license_number is not None,
                    parsing_result.data.expiration_date is not None,
                    parsing_result.data.license_class is not None,
                    parsing_result.data.address is not None,
                    parsing_result.data.state is not None,
                ]
            ),
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        return {"error": str(e)}


async def test_confidence_scoring():
    """Test confidence scoring logic."""
    print("\n\n📊 TESTING CONFIDENCE SCORING")
    print("=" * 50)

    parser = CDLParser()

    test_cases = [
        {
            "name": "Perfect CDL",
            "text": """
NAME: JOHN SMITH
LICENSE: D1234567
EXP: 12/25/2025
CLASS: A
ADDRESS: 123 MAIN ST
STATE: CA
""",
            "expected_min_confidence": 0.90,
        },
        {
            "name": "Name + Expiry only",
            "text": """
NAME: JOHN SMITH
EXP: 12/25/2025
""",
            "expected_min_confidence": 0.90,  # Should hit high confidence threshold
        },
        {
            "name": "Name + License only",
            "text": """
NAME: JOHN SMITH
LICENSE: D1234567
""",
            "expected_min_confidence": 0.60,  # Medium confidence
        },
        {
            "name": "No critical fields",
            "text": """
CLASS: A
ADDRESS: 123 MAIN ST
STATE: CA
""",
            "expected_min_confidence": 0.0,
            "expected_max_confidence": 0.50,
        },
    ]

    all_passed = True

    for test_case in test_cases:
        print(f"\n📝 Testing: {test_case['name']}")

        result = parser.parse(test_case["text"])
        confidence = result.confidence

        print(f"📊 Confidence: {confidence:.2f}")

        # Check minimum confidence
        min_conf = test_case["expected_min_confidence"]
        max_conf = test_case.get("expected_max_confidence", 1.0)

        if min_conf <= confidence <= max_conf:
            print(f"✅ Confidence in expected range [{min_conf:.2f}, {max_conf:.2f}]")
        else:
            print(
                f"❌ Confidence {confidence:.2f} not in expected range [{min_conf:.2f}, {max_conf:.2f}]"
            )
            all_passed = False

    return all_passed


async def test_verification_logic():
    """Test CDL verification logic."""
    print("\n\n🔍 TESTING CDL VERIFICATION LOGIC")
    print("=" * 50)

    parser = CDLParser()

    # Test with valid CDL (expires far in future)
    future_date = datetime.now() + timedelta(days=90)
    future_date_str = future_date.strftime("%m/%d/%Y")

    valid_cdl = f"""
NAME: JOHN SMITH
LICENSE: D1234567
EXP: {future_date_str}
"""

    print("📝 Testing valid CDL (expires in 90 days)...")
    result = parser.parse(valid_cdl)
    print(f"🔍 Verified: {result.cdl_verified}")
    print(f"📅 Expiration: {result.data.expiration_date}")

    if not result.cdl_verified:
        print("❌ Valid CDL should be verified")
        return False

    # Test with CDL expiring soon
    soon_date = datetime.now() + timedelta(days=20)  # Less than 30 days
    soon_date_str = soon_date.strftime("%m/%d/%Y")

    expiring_cdl = f"""
NAME: JOHN SMITH
LICENSE: D1234567
EXP: {soon_date_str}
"""

    print("\n📝 Testing CDL expiring in 20 days...")
    result = parser.parse(expiring_cdl)
    print(f"🔍 Verified: {result.cdl_verified}")
    print(f"📅 Expiration: {result.data.expiration_date}")

    if result.cdl_verified:
        print("❌ CDL expiring in <30 days should not be verified")
        return False

    # Test with missing critical fields
    incomplete_cdl = """
LICENSE: D1234567
CLASS: A
"""

    print("\n📝 Testing incomplete CDL (no name or expiration)...")
    result = parser.parse(incomplete_cdl)
    print(f"🔍 Verified: {result.cdl_verified}")

    if result.cdl_verified:
        print("❌ Incomplete CDL should not be verified")
        return False

    print("✅ All verification tests passed!")
    return True


async def test_edge_cases():
    """Test edge cases and error handling."""
    print("\n\n🚨 TESTING EDGE CASES")
    print("=" * 50)

    parser = CDLParser()

    # Test with empty text
    print("📝 Testing empty text...")
    result = parser.parse("")
    if result.confidence > 0:
        print("❌ Empty text should have 0 confidence")
        return False
    print("✅ Empty text handled correctly")

    # Test with garbage text
    print("\n📝 Testing garbage text...")
    result = parser.parse("asdfghjkl qwertyuiop zxcvbnm")
    if result.confidence > 0.3:
        print("❌ Garbage text should have very low confidence")
        return False
    print("✅ Garbage text handled correctly")

    # Test with malformed dates
    print("\n📝 Testing malformed dates...")
    malformed_date_text = """
NAME: JOHN SMITH
EXP: 99/99/9999
LICENSE: D1234567
"""
    result = parser.parse(malformed_date_text)
    if result.data.expiration_date is not None:
        print("❌ Malformed date should not be parsed")
        return False
    print("✅ Malformed dates handled correctly")

    print("✅ All edge case tests passed!")
    return True


async def main():
    """Run all CDL parser integration tests."""
    print("🚀 CDL PARSER REAL INTEGRATION TESTS")
    print("=" * 70)

    test_results = {}

    # Test 1: Text parsing
    try:
        test_results["text_parsing"] = await test_cdl_parser_text_parsing()
        print("\n✅ Text parsing tests completed")
    except Exception as e:
        print(f"\n❌ Text parsing tests failed: {e}")
        test_results["text_parsing"] = {"error": str(e)}

    # Test 2: OCR integration
    try:
        test_results["ocr_integration"] = await test_cdl_parser_with_ocr()
        print("\n✅ OCR integration tests completed")
    except Exception as e:
        print(f"\n❌ OCR integration tests failed: {e}")
        test_results["ocr_integration"] = {"error": str(e)}

    # Test 3: Confidence scoring
    try:
        test_results["confidence_scoring"] = await test_confidence_scoring()
        print("\n✅ Confidence scoring tests completed")
    except Exception as e:
        print(f"\n❌ Confidence scoring tests failed: {e}")
        test_results["confidence_scoring"] = False

    # Test 4: Verification logic
    try:
        test_results["verification_logic"] = await test_verification_logic()
        print("\n✅ Verification logic tests completed")
    except Exception as e:
        print(f"\n❌ Verification logic tests failed: {e}")
        test_results["verification_logic"] = False

    # Test 5: Edge cases
    try:
        test_results["edge_cases"] = await test_edge_cases()
        print("\n✅ Edge case tests completed")
    except Exception as e:
        print(f"\n❌ Edge case tests failed: {e}")
        test_results["edge_cases"] = False

    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)

    total_tests = 0
    passed_tests = 0

    # Count text parsing results
    if "text_parsing" in test_results and isinstance(
        test_results["text_parsing"], dict
    ):
        for sample_name, result in test_results["text_parsing"].items():
            if isinstance(result, dict) and result.get("success"):
                total_tests += 1
                if result.get("confidence", 0) > 0.5:
                    passed_tests += 1
                print(f"✅ {sample_name}: confidence={result.get('confidence', 0):.2f}")
            else:
                total_tests += 1
                print(f"❌ {sample_name}: failed")

    # Count other tests
    for test_name in ["confidence_scoring", "verification_logic", "edge_cases"]:
        total_tests += 1
        if test_results.get(test_name):
            passed_tests += 1
            print(f"✅ {test_name}: passed")
        else:
            print(f"❌ {test_name}: failed")

    # OCR integration
    total_tests += 1
    if "ocr_integration" in test_results and not test_results["ocr_integration"].get(
        "error"
    ):
        passed_tests += 1
        print("✅ ocr_integration: passed")
    else:
        print("❌ ocr_integration: failed")

    print(f"\n🎯 RESULTS: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("🎉 ALL TESTS PASSED! CDL Parser is ready for production!")
        return True
    else:
        print("🔧 Some tests failed. Review and fix issues before production use.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    if not success:
        sys.exit(1)

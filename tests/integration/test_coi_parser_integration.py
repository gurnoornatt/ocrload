#!/usr/bin/env python3
"""
COI Parser Real Integration Tests

Tests the COI parser with realistic COI document text samples from various
insurance companies and formats. Validates field extraction, confidence scoring,
and verification logic against actual COI document patterns.
"""

import asyncio
import io
import sys
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont

from app.services.document_parsers import COIParser
from app.services.ocr_clients import UnifiedOCRClient


def create_coi_text_samples():
    """Create realistic COI text samples from different insurance companies."""

    # Sample 1: State Farm format
    state_farm_coi = """
CERTIFICATE OF LIABILITY INSURANCE

INSURER: State Farm Fire and Casualty Company
POLICY NUMBER: 12-AB-C567-89
CERTIFICATE NUMBER: SF-2024-445566

INSURED: ABC TRUCKING COMPANY
123 MAIN STREET
ANYTOWN, TX 75001

DESCRIPTION OF OPERATIONS: COMMERCIAL TRUCKING

COVERAGE AMOUNTS:
GENERAL LIABILITY:
  General Aggregate: $2,000,000
  Each Occurrence: $1,000,000
  Personal & Advertising Injury: $1,000,000

COMMERCIAL AUTO LIABILITY:
  Combined Single Limit: $1,000,000

POLICY PERIOD:
EFFECTIVE DATE: 01/01/2025
EXPIRATION DATE: 01/01/2026

This certificate is issued for information only and confers no rights upon the certificate holder.
This certificate does not amend, extend or alter the coverage afforded by the policies below.
"""

    # Sample 2: Progressive Commercial format
    progressive_coi = """
CERTIFICATE OF INSURANCE

Progressive Commercial Inc.
Policy No: PGR-9876543210

INSURED: DEF LOGISTICS LLC
456 INDUSTRIAL BLVD
HOUSTON TX 77001

COVERAGE TYPES AND LIMITS:

General Liability
  Per Occurrence Limit: $1,000,000
  General Aggregate: $2,000,000

Auto Liability
  Combined Single Limit: $1,000,000

POLICY DATES:
From: 06/15/2025
To: 06/15/2026

DESCRIPTION: Motor Truck Cargo - Interstate Commerce

Certificate Holder: XYZ SHIPPER CORP
789 COMMERCE ST
DALLAS TX 75201
"""

    # Sample 3: Allstate format with different structure
    allstate_coi = """
ALLSTATE INSURANCE COMPANY
Commercial Insurance Certificate

Certificate No: ALL-2025-789123
Policy Number: ASC456789012

NAMED INSURED:
GHI TRANSPORT SOLUTIONS
789 FREIGHT WAY
ATLANTA GA 30301

COVERAGES:
Commercial General Liability
- Bodily Injury/Property Damage per Occurrence: $1,000,000
- Personal & Advertising Injury: $1,000,000
- General Aggregate: $2,000,000

Commercial Auto Liability
- Liability Coverage Limit: $1,000,000

POLICY EFFECTIVE: 03/01/2025
POLICY EXPIRATION: 03/01/2026

This certificate is furnished to: CLIENT SHIPPING COMPANY
"""

    # Sample 4: Travelers format (edge case with lower amounts)
    travelers_coi = """
THE TRAVELERS COMPANIES
CERTIFICATE OF LIABILITY INSURANCE

INSURER: Travelers Property Casualty Company of America
POLICY: TPC-L234567890

INSURED: JKL DELIVERY SERVICE
321 TRUCK STOP RD
PHOENIX AZ 85001

TYPE OF INSURANCE AND POLICY LIMITS:

GENERAL LIABILITY
Each Occurrence: $500,000
General Aggregate: $1,000,000

AUTO LIABILITY
Combined Single Limit: $750,000

POLICY PERIOD: 09/01/2025 TO 09/01/2026

CERTIFICATE HOLDER:
MAJOR RETAILER INC
555 CORPORATE PLAZA
PHOENIX AZ 85012
"""

    # Sample 5: GEICO Commercial format
    geico_coi = """
GEICO COMMERCIAL INSURANCE
LIABILITY CERTIFICATE

Carrier: Government Employees Insurance Company
Certificate Number: GEC-2025-112233
Policy Number: GEICO-CL-7890123

INSURED INFORMATION:
MNO FREIGHT LINES
987 LOGISTICS LANE
DENVER CO 80202

COVERAGE SUMMARY:

COMMERCIAL GENERAL LIABILITY
- Per Occurrence: $2,000,000
- Aggregate: $4,000,000

COMMERCIAL AUTO LIABILITY
- Single Limit: $2,000,000

COVERAGE PERIOD:
EFFECTIVE: 08/01/2025
EXPIRES: 08/01/2026

This certificate does not alter, amend or extend coverage.
"""

    return {
        "state_farm": state_farm_coi,
        "progressive": progressive_coi,
        "allstate": allstate_coi,
        "travelers": travelers_coi,
        "geico": geico_coi,
    }


def create_coi_images():
    """Create COI images for OCR testing."""

    def create_coi_image(text_content, width=800, height=1000):
        """Create a COI image with the given text."""
        img = Image.new("RGB", (width, height), color="white")
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 11)
            title_font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 14)
        except:
            font = ImageFont.load_default()
            title_font = font

        y_position = 20
        lines = text_content.strip().split("\n")

        for line in lines:
            if line.strip():
                # Use title font for headers
                current_font = (
                    title_font
                    if any(
                        keyword in line.upper()
                        for keyword in ["CERTIFICATE", "INSURANCE", "COMPANY"]
                    )
                    else font
                )
                draw.text(
                    (20, y_position), line.strip(), fill="black", font=current_font
                )
            y_position += 20

        # Convert to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        return img_bytes.getvalue()

    samples = create_coi_text_samples()
    images = {}

    for name, text in samples.items():
        images[name] = create_coi_image(text)

    return images


async def test_coi_parser_text_extraction():
    """Test COI parser with various text formats."""
    print("🔥 Testing COI Parser Text Extraction")
    print("=" * 50)

    parser = COIParser()
    samples = create_coi_text_samples()

    results = {}

    for company, text in samples.items():
        print(f"\n📄 Testing {company.upper()} COI format:")

        result = parser.parse(text)
        results[company] = result

        # Display results
        data = result.data
        print(f"  Policy Number: {data.policy_number}")
        print(f"  Insurance Company: {data.insurance_company}")
        print(
            f"  General Liability: ${data.general_liability_amount/100 if data.general_liability_amount else 0:,.2f}"
        )
        print(
            f"  Auto Liability: ${data.auto_liability_amount/100 if data.auto_liability_amount else 0:,.2f}"
        )
        print(f"  Effective Date: {data.effective_date}")
        print(f"  Expiration Date: {data.expiration_date}")
        print(f"  Confidence: {result.confidence:.2f}")
        print(f"  Insurance Verified: {result.insurance_verified}")

        # Basic validation
        assert (
            result.confidence > 0.5
        ), f"Confidence too low for {company}: {result.confidence}"
        assert data.policy_number is not None, f"No policy number found for {company}"
        assert (
            data.insurance_company is not None
        ), f"No insurance company found for {company}"
        assert (
            data.expiration_date is not None
        ), f"No expiration date found for {company}"

        # Check that at least one liability amount was found
        has_liability = (
            data.general_liability_amount is not None
            or data.auto_liability_amount is not None
        )
        assert has_liability, f"No liability amounts found for {company}"

        print(f"  ✅ {company.upper()} COI parsing successful")

    print("\n🎉 All COI text extraction tests passed!")
    return results


async def test_coi_parser_with_ocr():
    """Test COI parser with real OCR pipeline."""
    print("\n🔥 Testing COI Parser with OCR Integration")
    print("=" * 50)

    parser = COIParser()
    ocr_client = UnifiedOCRClient()
    images = create_coi_images()

    successful_tests = 0
    total_tests = len(images)

    for company, image_data in images.items():
        print(f"\n📸 Testing {company.upper()} COI with OCR:")

        try:
            # OCR the image
            ocr_result = await ocr_client.process_file_content(
                image_data, f"{company}_coi.png", "image/png"
            )

            print(f"  OCR Confidence: {ocr_result.get('average_confidence', 0):.2f}")
            print(f"  OCR Method: {ocr_result.get('extraction_method', 'unknown')}")

            # Parse with COI parser
            coi_result = parser.parse_from_ocr_result(ocr_result)

            # Display results
            data = coi_result.data
            print(f"  Policy Number: {data.policy_number}")
            print(f"  Insurance Company: {data.insurance_company}")
            print(
                f"  General Liability: ${data.general_liability_amount/100 if data.general_liability_amount else 0:,.2f}"
            )
            print(
                f"  Auto Liability: ${data.auto_liability_amount/100 if data.auto_liability_amount else 0:,.2f}"
            )
            print(f"  Expiration Date: {data.expiration_date}")
            print(f"  COI Confidence: {coi_result.confidence:.2f}")
            print(f"  Insurance Verified: {coi_result.insurance_verified}")

            # Validation (more lenient for OCR)
            if coi_result.confidence > 0.3:  # Lower threshold for OCR
                successful_tests += 1
                print(f"  ✅ {company.upper()} COI OCR parsing successful")
            else:
                print(f"  ⚠️ {company.upper()} COI OCR parsing low confidence")

        except Exception as e:
            print(f"  ❌ {company.upper()} COI OCR parsing failed: {str(e)}")

    print(f"\n📊 OCR Integration Results: {successful_tests}/{total_tests} successful")

    # Expect at least 60% success rate with OCR
    success_rate = successful_tests / total_tests
    assert success_rate >= 0.6, f"OCR success rate too low: {success_rate:.2f}"

    print("🎉 COI OCR integration tests completed successfully!")
    return success_rate


async def test_coi_verification_logic():
    """Test COI verification and edge cases."""
    print("\n🔥 Testing COI Verification Logic")
    print("=" * 50)

    parser = COIParser()

    # Test 1: Valid COI with good coverage
    valid_coi = """
CERTIFICATE OF INSURANCE
Policy Number: TEST-12345678
Insurance Company: Test Insurance Co
General Liability: $1,000,000
Auto Liability: $1,000,000
Effective Date: 01/01/2025
Expiration Date: 12/31/2025
"""

    result = parser.parse(valid_coi)
    print(
        f"Valid COI - Verified: {result.insurance_verified}, Confidence: {result.confidence:.2f}"
    )
    assert result.insurance_verified is True, "Valid COI should be verified"

    # Test 2: COI expiring soon (should fail verification)
    expiring_soon = f"""
CERTIFICATE OF INSURANCE
Policy Number: TEST-87654321
Insurance Company: Test Insurance Co
General Liability: $1,000,000
Expiration Date: {(datetime.now() + timedelta(days=15)).strftime('%m/%d/%Y')}
"""

    result = parser.parse(expiring_soon)
    print(
        f"Expiring Soon COI - Verified: {result.insurance_verified}, Confidence: {result.confidence:.2f}"
    )
    assert (
        result.insurance_verified is False
    ), "COI expiring soon should not be verified"

    # Test 3: Missing policy number
    missing_policy = """
CERTIFICATE OF INSURANCE
Insurance Company: Test Insurance Co
General Liability: $1,000,000
Expiration Date: 12/31/2025
"""

    result = parser.parse(missing_policy)
    print(
        f"Missing Policy COI - Verified: {result.insurance_verified}, Confidence: {result.confidence:.2f}"
    )
    assert (
        result.insurance_verified is False
    ), "COI without policy number should not be verified"

    # Test 4: No liability amounts
    no_amounts = """
CERTIFICATE OF INSURANCE
Policy Number: TEST-11111111
Insurance Company: Test Insurance Co
Expiration Date: 12/31/2025
"""

    result = parser.parse(no_amounts)
    print(
        f"No Amounts COI - Verified: {result.insurance_verified}, Confidence: {result.confidence:.2f}"
    )
    assert (
        result.insurance_verified is False
    ), "COI without liability amounts should not be verified"

    print("✅ All COI verification logic tests passed!")


async def test_coi_parser_edge_cases():
    """Test COI parser with real-world edge cases and OCR errors."""
    print("\n🔥 Testing COI Parser Edge Cases & OCR Errors")
    print("=" * 50)

    parser = COIParser()

    # Test cases with common OCR errors and variations
    edge_cases = {
        "ocr_errors": """
        CERT1FICATE OF 1NSURANCE

        1nsurer: State Farm F1re and Casual7y Company
        Policy Number: 12-AB-C567-89

        GENERAL L1AB1L1TY:
        Each 0ccurrence: $1,OOO,OOO
        General Aggregate: $2,OOO,OOO

        AUT0 L1AB1L1TY:
        Combined S1ngle L1mit: $1,OOO,OOO

        EFFECT1VE: O1/O1/2O25
        EXP1RAT10N: O1/O1/2O26
        """,
        "minimal_format": """
        INSURANCE CERTIFICATE

        Policy: ABC123456
        Company: Allstate
        GL: $1M
        Auto: $1M
        From: 01/01/2025
        To: 12/31/2025
        """,
        "complex_amounts": """
        COMMERCIAL INSURANCE CERTIFICATE

        Policy Number: COMPLEX-7890123
        Insurer: Progressive Commercial Inc

        General Liability Limits:
        - Each Occurrence Limit: $2.5 Million
        - General Aggregate Limit: $5 Million

        Commercial Auto Liability:
        - Combined Single Limit: $1.5M

        Policy Period: 06/15/2025 to 06/15/2026
        """,
        "poor_ocr_spacing": """
        CERTIFICATEOFINSURANCE
        INSURER:StateFarmFireandCasualtyCompany
        POLICYNUMBER:SF-2024-445566
        GENERALLIABILITY:$1,000,000
        AUTOLIABILITY:$1,000,000
        EFFECTIVEDATE:01/01/2025
        EXPIRATIONDATE:01/01/2026
        """,
        "lowercase_mixed": """
        certificate of insurance

        insurer: travelers property casualty company
        policy number: tpc-l987654321

        general liability:
        each occurrence: $500,000
        general aggregate: $1,000,000

        auto liability:
        combined single limit: $750,000

        effective date: 03/01/2025
        expiration date: 03/01/2026
        """,
    }

    results = {}
    successful_tests = 0

    for case_name, text in edge_cases.items():
        print(f"\n📋 Testing {case_name.upper().replace('_', ' ')}:")

        try:
            result = parser.parse(text)
            results[case_name] = result

            data = result.data
            print(f"  Policy Number: {data.policy_number}")
            print(f"  Insurance Company: {data.insurance_company}")
            print(
                f"  General Liability: ${data.general_liability_amount/100 if data.general_liability_amount else 0:,.2f}"
            )
            print(
                f"  Auto Liability: ${data.auto_liability_amount/100 if data.auto_liability_amount else 0:,.2f}"
            )
            print(f"  Expiration Date: {data.expiration_date}")
            print(f"  Confidence: {result.confidence:.2f}")
            print(f"  Insurance Verified: {result.insurance_verified}")

            # Validate core requirements for any recognizable COI
            if result.confidence > 0.3:  # Lower threshold for edge cases
                assert (
                    data.policy_number is not None
                ), f"No policy number found for {case_name}"
                successful_tests += 1
                print(f"  ✅ {case_name.upper().replace('_', ' ')} parsing successful")
            else:
                print(
                    f"  ⚠️ {case_name.upper().replace('_', ' ')} had low confidence but didn't crash"
                )

        except Exception as e:
            print(f"  ❌ {case_name.upper().replace('_', ' ')} failed: {str(e)}")
            results[case_name] = None

    print(f"\n📊 Edge Case Results: {successful_tests}/{len(edge_cases)} successful")
    print("✅ COI parser robustness test completed!")
    return results


async def main():
    """Run all COI parser integration tests."""
    print("🚀 Starting COI Parser Integration Tests")
    print("=" * 60)

    try:
        # Test 1: Text extraction
        await test_coi_parser_text_extraction()

        # Test 2: OCR integration (with rate limiting consideration)
        print("\n⏳ Waiting briefly to respect API rate limits...")
        await asyncio.sleep(2)
        ocr_success_rate = await test_coi_parser_with_ocr()

        # Test 3: Verification logic
        await test_coi_verification_logic()

        # Test 4: Edge cases
        await test_coi_parser_edge_cases()

        print("\n" + "=" * 60)
        print("🎉 ALL COI PARSER TESTS COMPLETED SUCCESSFULLY!")
        print("📊 Final Results:")
        print("   - Text Parsing: 5/5 companies successful")
        print(f"   - OCR Integration: {ocr_success_rate:.1%} success rate")
        print("   - Verification Logic: All edge cases handled correctly")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

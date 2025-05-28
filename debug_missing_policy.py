#!/usr/bin/env python3

from app.services.document_parsers.coi_parser import COIParser

# Test missing policy number
missing_policy = """
CERTIFICATE OF INSURANCE
Insurance Company: Test Insurance Co
General Liability: $1,000,000
Expiration Date: 12/31/2025
"""

parser = COIParser()
result = parser.parse(missing_policy)

print(f"Policy found: '{result.data.policy_number}'")
print(f"Insurance Company: '{result.data.insurance_company}'")
print(f"General Liability: {result.data.general_liability_amount}")
print(f"Expiration Date: {result.data.expiration_date}")
print(f"Verified: {result.insurance_verified}")
print(f"Extraction details: {result.extraction_details}")

# Test each pattern individually
print("\nTesting patterns individually:")
for i, pattern in enumerate(parser.policy_patterns):
    match = pattern.search(missing_policy)
    if match:
        print(f"Pattern {i} matched: '{match.group(0)}' -> '{match.group(1)}'")
        is_valid = parser._is_valid_policy_number(match.group(1))
        print(f"Valid: {is_valid}") 
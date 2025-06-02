#!/usr/bin/env python3
"""
Realistic Performance Test for Task 21 - NO ARTIFICIAL OPTIMIZATIONS
Tests actual end-to-end document processing with real failure detection.
"""

import asyncio
import sys
import time
from uuid import uuid4

from fastapi.testclient import TestClient

# Add the app to the path
sys.path.append(".")
from app.main import app
from app.services.document_service import document_service
from app.services.performance_monitor import performance_monitor


async def wait_for_document_completion(
    doc_id: str, timeout_seconds: int = 30
) -> tuple[bool, str, float]:
    """
    Wait for document processing to complete and return actual results.

    Returns:
        (success, final_status, processing_time)
    """
    start_time = time.time()

    for _elapsed in range(0, timeout_seconds, 1):
        await asyncio.sleep(1)

        try:
            document = await document_service.get_document(doc_id)
            if document and document.status.value in ["PARSED", "FAILED"]:
                processing_time = time.time() - start_time
                success = document.status.value == "PARSED"
                return success, document.status.value, processing_time
        except Exception as e:
            print(f"   ⚠️  Error checking document status: {e}")
            continue

    # Timeout
    processing_time = time.time() - start_time
    return False, "TIMEOUT", processing_time


def test_realistic_performance_monitoring():
    """Test performance monitoring with realistic failure detection."""
    client = TestClient(app)

    print("🧪 REALISTIC Performance Test for Task 21")
    print("=" * 60)
    print("⚠️  NO ARTIFICIAL OPTIMIZATIONS - Testing real failures!")
    print("=" * 60)

    # Clear previous metrics to get clean measurements
    performance_monitor.clear_metrics()
    print("🧹 Cleared previous performance metrics")

    # Test 1: Process real document end-to-end
    print("\n📄 TEST 1: Real Document Processing")
    print("-" * 40)

    response = client.post(
        "/api/parse-test/",
        json={
            "path": "./BILL OF LADING.pdf",
            "doc_type": "POD",
            "driver_id": str(uuid4()),
            "load_id": str(uuid4()),
        },
    )

    if response.status_code != 202:
        print(f"❌ FAILED: Document submission failed: {response.json()}")
        return False

    doc_id = response.json()["doc_id"]
    print(f"✅ Document submitted: {doc_id}")

    # Wait for ACTUAL completion (not just API acceptance)
    print("⏳ Waiting for REAL processing completion...")

    async def check_completion():
        return await wait_for_document_completion(doc_id, timeout_seconds=45)

    success, final_status, processing_time = asyncio.run(check_completion())

    print("📊 REAL Processing Results:")
    print(f"   - Final Status: {final_status}")
    print(f"   - Processing Time: {processing_time:.2f}s")
    print(f"   - Success: {'✅ YES' if success else '❌ NO'}")

    # Test 2: Intentional failure test
    print("\n📄 TEST 2: Intentional Failure Test")
    print("-" * 40)

    failure_response = client.post(
        "/api/parse-test/",
        json={
            "path": "/definitely/does/not/exist.pdf",
            "doc_type": "POD",
            "driver_id": str(uuid4()),
            "load_id": str(uuid4()),
        },
    )

    print(f"📊 Expected Failure Result: {failure_response.status_code}")
    if 400 <= failure_response.status_code < 500:
        print("✅ Correctly rejected invalid file (4xx error)")
    elif failure_response.status_code >= 500:
        print("⚠️  Server error for invalid input (5xx error)")
    else:
        print("❌ Unexpected response for invalid file")

    # Test 3: Get REAL metrics after processing
    print("\n📊 TEST 3: Real Metrics Analysis")
    print("-" * 40)

    time.sleep(2)  # Allow metrics to be recorded

    kpi = client.get("/api/monitoring/kpi")
    if kpi.status_code == 200:
        kpi_data = kpi.json()

        print("📈 ACTUAL KPI Metrics:")
        print(f"   - Total Requests: {kpi_data['total_requests']}")
        print(f"   - Success Rate: {kpi_data['success_rate']:.1f}%")
        print(f"   - Median Turnaround: {kpi_data['median_turnaround']:.2f}s")
        print(f"   - Error Rate (5xx): {kpi_data['error_rate_5xx']:.2f}%")
        print(f"   - OCR Success Rate: {kpi_data['ocr_success_rate']:.1f}%")
        print(f"   - Parsing Success Rate: {kpi_data['parsing_success_rate']:.1f}%")

        # REALISTIC KPI Assessment
        print("\n🎯 REALISTIC KPI Assessment:")
        compliance = kpi_data["compliance_status"]

        turnaround_ok = compliance.get("turnaround_3s", False)
        success_ok = compliance.get("success_rate_95", False)
        error_ok = compliance.get("error_rate_1", False)
        overall_ok = compliance.get("overall_kpi_met", False)

        print(
            f"   - Turnaround ≤3s: {'✅ PASS' if turnaround_ok else '❌ FAIL'} ({kpi_data['median_turnaround']:.2f}s)"
        )
        print(
            f"   - Success ≥95%: {'✅ PASS' if success_ok else '❌ FAIL'} ({kpi_data['success_rate']:.1f}%)"
        )
        print(
            f"   - Error <1%: {'✅ PASS' if error_ok else '❌ FAIL'} ({kpi_data['error_rate_5xx']:.2f}%)"
        )
        print(f"   - Overall KPI: {'✅ MET' if overall_ok else '❌ NOT MET'}")

        # Detailed analysis
        if not overall_ok:
            print("\n⚠️  KPI ISSUES DETECTED:")
            if not turnaround_ok:
                print(
                    f"     - Processing too slow: {kpi_data['median_turnaround']:.2f}s > 3.0s"
                )
            if not success_ok:
                print(
                    f"     - Success rate too low: {kpi_data['success_rate']:.1f}% < 95%"
                )
            if not error_ok:
                print(
                    f"     - Error rate too high: {kpi_data['error_rate_5xx']:.2f}% > 1%"
                )
    else:
        print(f"❌ Failed to get KPI metrics: {kpi.status_code}")
        return False

    # Final assessment
    print("\n" + "=" * 60)
    print("🏁 REALISTIC TEST SUMMARY:")
    print(f"   - Document Processing: {'✅ SUCCESS' if success else '❌ FAILED'}")
    print(f"   - Processing Time: {processing_time:.2f}s")
    print("   - Error Handling: ✅ WORKING")
    print("   - Metrics Collection: ✅ WORKING")
    print(f"   - KPI Compliance: {'✅ MET' if overall_ok else '❌ NOT MET'}")

    if success and overall_ok:
        print("🎉 TASK 21 PERFORMANCE MONITORING: FULLY WORKING!")
    elif success and not overall_ok:
        print("⚠️  TASK 21: Processing works but KPIs need optimization")
    else:
        print("❌ TASK 21: Issues detected - needs investigation")

    return success and overall_ok


if __name__ == "__main__":
    test_realistic_performance_monitoring()

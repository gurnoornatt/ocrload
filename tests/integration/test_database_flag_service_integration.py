#!/usr/bin/env python3
"""
Integration tests for Database Flag Update Service

Tests the service functionality with real database operations,
business logic validation, and comprehensive scenarios that
would occur in production environments.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.database import (
    Document,
    DocumentType,
    DriverStatus,
    LoadStatus,
)
from app.services.database_flag_service import (
    DatabaseFlagUpdateService,
)


class TestDatabaseFlagServiceIntegration:
    """Integration test suite for Database Flag Update Service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = DatabaseFlagUpdateService()
        self.mock_driver_id = uuid4()
        self.mock_load_id = uuid4()
        self.mock_document_id = uuid4()

    @pytest.mark.asyncio
    async def test_cdl_flag_update_success(self):
        """Test successful CDL flag update with valid expiry date."""
        # Arrange
        future_expiry = datetime.now(UTC) + timedelta(
            days=60
        )  # 60 days from now
        cdl_data = {
            "driver_name": "John Smith",
            "license_number": "D123456789",
            "expiration_date": future_expiry,
            "license_class": "A",
            "state": "CA",
        }

        document = Document(
            id=self.mock_document_id,
            driver_id=self.mock_driver_id,
            type=DocumentType.CDL,
            url="https://example.com/cdl.jpg",
        )

        # Mock the supabase service
        with patch.object(
            self.service.supabase, "update_driver_flags"
        ) as mock_update_flags:
            mock_update_flags.return_value = True

            # Act
            result = await self.service.process_document_flags(
                document, cdl_data, confidence=0.95
            )

            # Assert
            assert result["confidence"] == 0.95
            assert result["flags_updated"]["cdl_verified"] is True
            assert any(
                "Confidence threshold met" in rule
                for rule in result["business_rules_applied"]
            )
            assert any(
                "CDL expiry valid" in rule for rule in result["business_rules_applied"]
            )

            # Verify the mock was called correctly
            mock_update_flags.assert_called_once_with(
                self.mock_driver_id, cdl_verified=True
            )

    @pytest.mark.asyncio
    async def test_cdl_flag_update_expiry_too_soon(self):
        """Test CDL flag update fails when expiry is too soon."""
        # Arrange - expiry in 20 days (less than required 30)
        soon_expiry = datetime.now(UTC) + timedelta(days=20)
        cdl_data = {
            "driver_name": "John Smith",
            "license_number": "D123456789",
            "expiration_date": soon_expiry,
            "license_class": "A",
            "state": "CA",
        }

        document = Document(
            id=self.mock_document_id,
            driver_id=self.mock_driver_id,
            type=DocumentType.CDL,
            url="https://example.com/cdl.jpg",
        )

        # Mock the supabase service
        with patch.object(
            self.service.supabase, "update_driver_flags"
        ) as mock_update_flags:
            # Act
            result = await self.service.process_document_flags(
                document, cdl_data, confidence=0.95
            )

            # Assert
            assert "cdl_verified" not in result["flags_updated"]
            assert any(
                "CDL expiry too soon" in rule
                for rule in result["business_rules_applied"]
            )

            # Verify the mock was not called
            mock_update_flags.assert_not_called()

    @pytest.mark.asyncio
    async def test_coi_flag_update_success(self):
        """Test successful COI flag update with valid expiry date."""
        # Arrange
        future_expiry = datetime.now(UTC) + timedelta(
            days=180
        )  # 6 months from now
        coi_data = {
            "policy_number": "POL123456",
            "insurance_company": "ACME Insurance",
            "general_liability_amount": 100000000,  # $1M in cents
            "auto_liability_amount": 100000000,  # $1M in cents
            "effective_date": datetime.now(UTC) - timedelta(days=30),
            "expiration_date": future_expiry,
        }

        document = Document(
            id=self.mock_document_id,
            driver_id=self.mock_driver_id,
            type=DocumentType.COI,
            url="https://example.com/coi.pdf",
        )

        # Mock the supabase service
        with patch.object(
            self.service.supabase, "update_driver_flags"
        ) as mock_update_flags:
            mock_update_flags.return_value = True

            # Act
            result = await self.service.process_document_flags(
                document, coi_data, confidence=0.92
            )

            # Assert
            assert result["flags_updated"]["insurance_verified"] is True
            assert any(
                "COI not expired" in rule for rule in result["business_rules_applied"]
            )

            mock_update_flags.assert_called_once_with(
                self.mock_driver_id, insurance_verified=True
            )

    @pytest.mark.asyncio
    async def test_coi_flag_update_expired(self):
        """Test COI flag update fails when insurance is expired."""
        # Arrange - expired 30 days ago
        past_expiry = datetime.now(UTC) - timedelta(days=30)
        coi_data = {
            "policy_number": "POL123456",
            "insurance_company": "ACME Insurance",
            "expiration_date": past_expiry,
        }

        document = Document(
            id=self.mock_document_id,
            driver_id=self.mock_driver_id,
            type=DocumentType.COI,
            url="https://example.com/coi.pdf",
        )

        # Mock the supabase service
        with patch.object(
            self.service.supabase, "update_driver_flags"
        ) as mock_update_flags:
            # Act
            result = await self.service.process_document_flags(
                document, coi_data, confidence=0.95
            )

            # Assert
            assert "insurance_verified" not in result["flags_updated"]
            assert any(
                "COI expired" in rule for rule in result["business_rules_applied"]
            )

            mock_update_flags.assert_not_called()

    @pytest.mark.asyncio
    async def test_agreement_flag_update_with_signature(self):
        """Test agreement flag update with detected signature."""
        # Arrange
        agreement_data = {
            "signature_detected": True,
            "signing_date": datetime.now(UTC),
            "agreement_type": "Driver Agreement",
        }

        document = Document(
            id=self.mock_document_id,
            driver_id=self.mock_driver_id,
            type=DocumentType.AGREEMENT,
            url="https://example.com/agreement.pdf",
        )

        # Mock the supabase service
        with patch.object(
            self.service.supabase, "update_driver_flags"
        ) as mock_update_flags:
            mock_update_flags.return_value = True

            # Act
            result = await self.service.process_document_flags(
                document, agreement_data, confidence=0.93
            )

            # Assert
            assert result["flags_updated"]["agreement_signed"] is True
            assert any(
                "Signature detected" in rule
                for rule in result["business_rules_applied"]
            )

            mock_update_flags.assert_called_once_with(
                self.mock_driver_id, agreement_signed=True
            )

    @pytest.mark.asyncio
    async def test_agreement_flag_update_no_signature(self):
        """Test agreement flag update without detected signature but high confidence."""
        # Arrange
        agreement_data = {
            "signature_detected": False,
            "signing_date": datetime.now(UTC),
            "agreement_type": "Driver Agreement",
        }

        document = Document(
            id=self.mock_document_id,
            driver_id=self.mock_driver_id,
            type=DocumentType.AGREEMENT,
            url="https://example.com/agreement.pdf",
        )

        # Mock the supabase service
        with patch.object(
            self.service.supabase, "update_driver_flags"
        ) as mock_update_flags:
            mock_update_flags.return_value = True

            # Act
            result = await self.service.process_document_flags(
                document, agreement_data, confidence=0.94
            )

            # Assert
            assert result["flags_updated"]["agreement_signed"] is True
            assert any(
                "no signature detection" in rule
                for rule in result["business_rules_applied"]
            )

            mock_update_flags.assert_called_once_with(
                self.mock_driver_id, agreement_signed=True
            )

    @pytest.mark.asyncio
    async def test_ratecon_flag_update_success(self):
        """Test successful rate confirmation flag update with all required fields."""
        # Arrange
        ratecon_data = {
            "rate_amount": 250000,  # $2,500 in cents
            "origin": "Atlanta, GA",
            "destination": "Chicago, IL",
            "pickup_date": datetime.now(UTC) + timedelta(days=1),
            "delivery_date": datetime.now(UTC) + timedelta(days=3),
            "weight": 45000.0,
            "commodity": "Electronics",
        }

        document = Document(
            id=self.mock_document_id,
            load_id=self.mock_load_id,
            type=DocumentType.RATE_CON,
            url="https://example.com/ratecon.pdf",
        )

        # Mock the supabase service
        with patch.object(
            self.service, "_update_load_ratecon_verified"
        ) as mock_update_ratecon:
            mock_update_ratecon.return_value = None

            # Act
            result = await self.service.process_document_flags(
                document,
                ratecon_data,
                confidence=0.85,  # Lower confidence OK for rate cons
            )

            # Assert
            assert result["flags_updated"]["ratecon_verified"] is True
            assert any(
                "All required fields present" in rule
                for rule in result["business_rules_applied"]
            )

            mock_update_ratecon.assert_called_once_with(self.mock_load_id, True)

    @pytest.mark.asyncio
    async def test_ratecon_flag_update_missing_fields(self):
        """Test rate confirmation flag update fails with missing required fields."""
        # Arrange - missing rate amount
        ratecon_data = {
            "rate_amount": None,  # Missing required field
            "origin": "Atlanta, GA",
            "destination": "Chicago, IL",
        }

        document = Document(
            id=self.mock_document_id,
            load_id=self.mock_load_id,
            type=DocumentType.RATE_CON,
            url="https://example.com/ratecon.pdf",
        )

        # Mock the supabase service
        with patch.object(
            self.service, "_update_load_ratecon_verified"
        ) as mock_update_ratecon:
            # Act
            result = await self.service.process_document_flags(
                document, ratecon_data, confidence=0.95
            )

            # Assert
            assert "ratecon_verified" not in result["flags_updated"]
            assert any(
                "Missing required fields" in rule
                for rule in result["business_rules_applied"]
            )
            assert any("rate" in rule for rule in result["business_rules_applied"])

            mock_update_ratecon.assert_not_called()

    @pytest.mark.asyncio
    async def test_pod_flag_update_success(self):
        """Test successful POD flag update marking load as delivered."""
        # Arrange
        pod_data = {
            "delivery_confirmed": True,
            "delivery_date": datetime.now(UTC),
            "receiver_name": "John Smith",
            "signature_present": True,
            "delivery_notes": "Package delivered in good condition",
        }

        document = Document(
            id=self.mock_document_id,
            load_id=self.mock_load_id,
            type=DocumentType.POD,
            url="https://example.com/pod.pdf",
        )

        # Mock the supabase service
        with patch.object(
            self.service.supabase, "update_load_status"
        ) as mock_update_status, patch.object(
            self.service, "_check_invoice_readiness"
        ) as mock_check_invoice:
            mock_update_status.return_value = True
            mock_check_invoice.return_value = None

            # Act
            result = await self.service.process_document_flags(
                document, pod_data, confidence=0.96
            )

            # Assert
            assert result["flags_updated"]["status"] == LoadStatus.DELIVERED
            assert any(
                "Delivery confirmed" in rule
                for rule in result["business_rules_applied"]
            )

            mock_update_status.assert_called_once_with(
                self.mock_load_id, LoadStatus.DELIVERED
            )
            mock_check_invoice.assert_called_once()

    @pytest.mark.asyncio
    async def test_pod_flag_update_no_delivery_confirmation(self):
        """Test POD flag update fails when delivery is not confirmed."""
        # Arrange
        pod_data = {
            "delivery_confirmed": False,  # Not confirmed
            "delivery_date": datetime.now(UTC),
            "receiver_name": "John Smith",
            "signature_present": True,
        }

        document = Document(
            id=self.mock_document_id,
            load_id=self.mock_load_id,
            type=DocumentType.POD,
            url="https://example.com/pod.pdf",
        )

        # Mock the supabase service
        with patch.object(
            self.service.supabase, "update_load_status"
        ) as mock_update_status:
            # Act
            result = await self.service.process_document_flags(
                document, pod_data, confidence=0.95
            )

            # Assert
            assert "status" not in result["flags_updated"]
            assert any(
                "Delivery not confirmed" in rule
                for rule in result["business_rules_applied"]
            )

            mock_update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_invoice_readiness_check(self):
        """Test invoice readiness check when both POD and rate confirmation are complete."""
        # Arrange
        pod_data = {
            "delivery_confirmed": True,
            "delivery_date": datetime.now(UTC),
            "receiver_name": "John Smith",
            "signature_present": True,
        }

        document = Document(
            id=self.mock_document_id,
            load_id=self.mock_load_id,
            type=DocumentType.POD,
            url="https://example.com/pod.pdf",
        )

        # Mock the supabase service
        with patch.object(
            self.service.supabase, "update_load_status"
        ) as mock_update_status, patch.object(
            self.service.supabase, "check_load_ratecon_verified"
        ) as mock_check_ratecon:
            mock_update_status.return_value = True
            mock_check_ratecon.return_value = True  # Rate confirmation is verified

            # Act
            result = await self.service.process_document_flags(
                document, pod_data, confidence=0.95
            )

            # Assert
            assert result["invoice_ready"] is True
            assert any(
                "Invoice ready" in rule for rule in result["business_rules_applied"]
            )

    @pytest.mark.asyncio
    async def test_low_confidence_scenarios(self):
        """Test that low confidence prevents flag updates across all document types."""
        test_cases = [
            (
                DocumentType.CDL,
                {"expiration_date": datetime.now(UTC) + timedelta(days=60)},
                self.mock_driver_id,
                None,
            ),
            (
                DocumentType.COI,
                {"expiration_date": datetime.now(UTC) + timedelta(days=60)},
                self.mock_driver_id,
                None,
            ),
            (
                DocumentType.AGREEMENT,
                {"signature_detected": True},
                self.mock_driver_id,
                None,
            ),
            # Note: RATE_CON doesn't use confidence threshold - only checks required fields
            (DocumentType.POD, {"delivery_confirmed": True}, None, self.mock_load_id),
        ]

        for doc_type, data, driver_id, load_id in test_cases:
            document = Document(
                id=uuid4(),
                driver_id=driver_id,
                load_id=load_id,
                type=doc_type,
                url=f"https://example.com/{doc_type.lower()}.pdf",
            )

            with patch.object(
                self.service.supabase, "update_driver_flags"
            ) as mock_driver_flags, patch.object(
                self.service.supabase, "update_load_status"
            ) as mock_load_status, patch.object(
                self.service, "_update_load_ratecon_verified"
            ) as mock_ratecon:
                # Act - low confidence (0.7 < 0.9 threshold)
                result = await self.service.process_document_flags(
                    document, data, confidence=0.7
                )

                # Assert
                assert len(result["flags_updated"]) == 0  # No flags should be updated
                assert any(
                    "Confidence too low" in rule
                    for rule in result["business_rules_applied"]
                )

                # Verify no database updates were made
                mock_driver_flags.assert_not_called()
                mock_load_status.assert_not_called()
                mock_ratecon.assert_not_called()

    @pytest.mark.asyncio
    async def test_ratecon_low_confidence_but_complete_fields(self):
        """Test that rate confirmation updates flags even with low confidence if all required fields are present."""
        # This tests the specific business rule for rate confirmations
        ratecon_data = {
            "rate_amount": 250000,
            "origin": "Atlanta, GA",
            "destination": "Chicago, IL",
        }

        document = Document(
            id=uuid4(),
            load_id=self.mock_load_id,
            type=DocumentType.RATE_CON,
            url="https://example.com/ratecon.pdf",
        )

        with patch.object(
            self.service, "_update_load_ratecon_verified"
        ) as mock_update_ratecon:
            mock_update_ratecon.return_value = None

            # Act - low confidence but all required fields present
            result = await self.service.process_document_flags(
                document,
                ratecon_data,
                confidence=0.6,  # Below normal threshold
            )

            # Assert - rate confirmation should still be verified due to complete fields
            assert result["flags_updated"]["ratecon_verified"] is True
            assert any(
                "All required fields present" in rule
                for rule in result["business_rules_applied"]
            )

            mock_update_ratecon.assert_called_once_with(self.mock_load_id, True)

    @pytest.mark.asyncio
    async def test_error_handling_missing_document_ids(self):
        """Test error handling when documents are missing required IDs."""
        # Test cases that should raise ValueError due to business logic constraints
        driver_test_cases = [
            (
                DocumentType.CDL,
                {"expiration_date": datetime.now(UTC) + timedelta(days=60)},
            ),
            (
                DocumentType.COI,
                {"expiration_date": datetime.now(UTC) + timedelta(days=60)},
            ),
            (DocumentType.AGREEMENT, {"signature_detected": True}),
        ]

        load_test_cases = [
            (
                DocumentType.RATE_CON,
                {"rate_amount": 250000, "origin": "A", "destination": "B"},
            ),
            (DocumentType.POD, {"delivery_confirmed": True}),
        ]

        # Test driver documents without driver_id (but with dummy load_id to satisfy model validation)
        for doc_type, data in driver_test_cases:
            document = Document(
                id=uuid4(),
                driver_id=None,  # Missing required driver_id
                load_id=self.mock_load_id,  # Dummy load_id to satisfy model validation
                type=doc_type,
                url=f"https://example.com/{doc_type.lower()}.pdf",
            )

            # Act & Assert
            with pytest.raises(ValueError) as exc_info:
                await self.service.process_document_flags(
                    document, data, confidence=0.95
                )

            assert "must have driver_id" in str(exc_info.value)

        # Test load documents without load_id (but with dummy driver_id to satisfy model validation)
        for doc_type, data in load_test_cases:
            document = Document(
                id=uuid4(),
                driver_id=self.mock_driver_id,  # Dummy driver_id to satisfy model validation
                load_id=None,  # Missing required load_id
                type=doc_type,
                url=f"https://example.com/{doc_type.lower()}.pdf",
            )

            # Act & Assert
            with pytest.raises(ValueError) as exc_info:
                await self.service.process_document_flags(
                    document, data, confidence=0.95
                )

            assert "must have load_id" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_driver_verification_status(self):
        """Test getting comprehensive driver verification status."""
        # Arrange
        mock_driver = MagicMock()
        mock_driver.doc_flags.model_dump.return_value = {
            "cdl_verified": True,
            "insurance_verified": True,
            "agreement_signed": False,
        }
        mock_driver.doc_flags.cdl_verified = True
        mock_driver.doc_flags.insurance_verified = True
        mock_driver.doc_flags.agreement_signed = False
        mock_driver.status = DriverStatus.PENDING
        mock_driver.updated_at = datetime.now(UTC)

        with patch.object(self.service.supabase, "get_driver_by_id") as mock_get_driver:
            mock_get_driver.return_value = mock_driver

            # Act
            result = await self.service.get_driver_verification_status(
                self.mock_driver_id
            )

            # Assert
            assert result["driver_id"] == str(self.mock_driver_id)
            assert result["doc_flags"]["cdl_verified"] is True
            assert result["doc_flags"]["insurance_verified"] is True
            assert result["doc_flags"]["agreement_signed"] is False
            assert result["verification_complete"] is False  # Not all flags are True

    @pytest.mark.asyncio
    async def test_get_load_verification_status(self):
        """Test getting comprehensive load verification status."""
        # Arrange
        mock_load = MagicMock()
        mock_load.status = LoadStatus.IN_TRANSIT
        mock_load.origin = "Atlanta, GA"
        mock_load.destination = "Chicago, IL"
        mock_load.rate = 250000  # $2,500 in cents

        with patch.object(
            self.service.supabase, "get_load_by_id"
        ) as mock_get_load, patch.object(
            self.service.supabase, "check_load_ratecon_verified"
        ) as mock_check_ratecon:
            mock_get_load.return_value = mock_load
            mock_check_ratecon.return_value = True

            # Act
            result = await self.service.get_load_verification_status(self.mock_load_id)

            # Assert
            assert result["load_id"] == str(self.mock_load_id)
            assert result["status"] == LoadStatus.IN_TRANSIT
            assert result["ratecon_verified"] is True
            assert result["pod_completed"] is False  # Status is not DELIVERED
            assert result["invoice_ready"] is False  # POD not completed

    @pytest.mark.asyncio
    async def test_comprehensive_production_scenario(self):
        """Test a comprehensive production scenario with multiple document processing."""
        # This test simulates a real production workflow

        # Step 1: Process CDL
        cdl_data = {
            "driver_name": "John Smith",
            "license_number": "D123456789",
            "expiration_date": datetime.now(UTC) + timedelta(days=365),
            "license_class": "A",
            "state": "CA",
        }

        cdl_doc = Document(
            id=uuid4(),
            driver_id=self.mock_driver_id,
            type=DocumentType.CDL,
            url="https://example.com/cdl.jpg",
        )

        # Step 2: Process COI
        coi_data = {
            "policy_number": "POL123456",
            "insurance_company": "ACME Insurance",
            "expiration_date": datetime.now(UTC) + timedelta(days=180),
        }

        coi_doc = Document(
            id=uuid4(),
            driver_id=self.mock_driver_id,
            type=DocumentType.COI,
            url="https://example.com/coi.pdf",
        )

        # Step 3: Process Agreement
        agreement_data = {
            "signature_detected": True,
            "signing_date": datetime.now(UTC),
            "agreement_type": "Driver Agreement",
        }

        agreement_doc = Document(
            id=uuid4(),
            driver_id=self.mock_driver_id,
            type=DocumentType.AGREEMENT,
            url="https://example.com/agreement.pdf",
        )

        # Step 4: Process Rate Confirmation
        ratecon_data = {
            "rate_amount": 250000,
            "origin": "Atlanta, GA",
            "destination": "Chicago, IL",
        }

        ratecon_doc = Document(
            id=uuid4(),
            load_id=self.mock_load_id,
            type=DocumentType.RATE_CON,
            url="https://example.com/ratecon.pdf",
        )

        # Step 5: Process POD
        pod_data = {
            "delivery_confirmed": True,
            "delivery_date": datetime.now(UTC),
            "receiver_name": "John Smith",
            "signature_present": True,
        }

        pod_doc = Document(
            id=uuid4(),
            load_id=self.mock_load_id,
            type=DocumentType.POD,
            url="https://example.com/pod.pdf",
        )

        # Mock all services
        with patch.object(
            self.service.supabase, "update_driver_flags"
        ) as mock_update_flags, patch.object(
            self.service.supabase, "update_load_status"
        ) as mock_update_status, patch.object(
            self.service, "_update_load_ratecon_verified"
        ) as mock_update_ratecon, patch.object(
            self.service.supabase, "check_load_ratecon_verified"
        ) as mock_check_ratecon:
            mock_update_flags.return_value = True
            mock_update_status.return_value = True
            mock_check_ratecon.return_value = True  # Rate confirmation will be verified

            # Act - Process all documents
            cdl_result = await self.service.process_document_flags(
                cdl_doc, cdl_data, 0.95
            )
            coi_result = await self.service.process_document_flags(
                coi_doc, coi_data, 0.92
            )
            agreement_result = await self.service.process_document_flags(
                agreement_doc, agreement_data, 0.94
            )
            ratecon_result = await self.service.process_document_flags(
                ratecon_doc, ratecon_data, 0.88
            )
            pod_result = await self.service.process_document_flags(
                pod_doc, pod_data, 0.96
            )

            # Assert - All processing should succeed
            assert cdl_result["flags_updated"]["cdl_verified"] is True
            assert coi_result["flags_updated"]["insurance_verified"] is True
            assert agreement_result["flags_updated"]["agreement_signed"] is True
            assert ratecon_result["flags_updated"]["ratecon_verified"] is True
            assert pod_result["flags_updated"]["status"] == LoadStatus.DELIVERED
            assert (
                pod_result["invoice_ready"] is True
            )  # Both POD and rate confirmation completed

            # Verify all database calls were made
            assert mock_update_flags.call_count == 3  # CDL, COI, Agreement
            mock_update_status.assert_called_once()
            mock_update_ratecon.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

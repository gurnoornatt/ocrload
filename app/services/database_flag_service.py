"""
Database Flag Update Service

Implements business logic to update driver and load flags based on document
processing results. Handles all document types with proper validation and
business rule enforcement.

Business Logic:
- CDL -> drivers.cdl_verified (if confidence>=0.9 && expiry>today+30)
- COI -> drivers.insurance_verified (if confidence>=0.9 && not expired)
- AGREEMENT -> drivers.agreement_signed (if confidence>=0.9)
- RATE_CON -> loads.ratecon_verified (if rate+origin+dest present)
- POD -> loads.status='delivered' (if confidence>=0.9)
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.models.database import (
    AgreementData,
    CDLData,
    COIData,
    Document,
    DocumentType,
    LoadStatus,
    PODData,
    RateConData,
)
from app.services.redis_event_service import redis_event_service
from app.services.supabase_client import supabase_service

logger = logging.getLogger(__name__)


class DatabaseFlagUpdateService:
    """
    Service for updating database flags based on document processing results.

    This service implements the business logic for determining when drivers
    and loads should have their verification flags updated based on parsed
    document data and confidence scores.
    """

    # Business rule thresholds
    MIN_CONFIDENCE_THRESHOLD = 0.9
    CDL_MIN_DAYS_BEFORE_EXPIRY = 30

    def __init__(self):
        """Initialize the flag update service."""
        self.supabase = supabase_service
        self.redis_event_service = redis_event_service

    async def process_document_flags(
        self, document: Document, parsed_data: dict[str, Any], confidence: float
    ) -> dict[str, Any]:
        """
        Process document and update appropriate flags based on document type.

        Args:
            document: Document model instance
            parsed_data: Parsed document data dictionary
            confidence: Parsing confidence score (0.0 to 1.0)

        Returns:
            Dict with processing results and any flag updates applied

        Raises:
            ValueError: If document type is unsupported or required data is missing
        """
        logger.info(
            f"Processing flags for document {document.id} "
            f"(type: {document.type}, confidence: {confidence:.2f})"
        )

        result = {
            "document_id": str(document.id),
            "document_type": document.type,
            "confidence": confidence,
            "flags_updated": {},
            "business_rules_applied": [],
            "errors": [],
        }

        try:
            # Route to appropriate handler based on document type
            if document.type == DocumentType.CDL:
                await self._process_cdl_flags(document, parsed_data, confidence, result)
            elif document.type == DocumentType.COI:
                await self._process_coi_flags(document, parsed_data, confidence, result)
            elif document.type == DocumentType.AGREEMENT:
                await self._process_agreement_flags(
                    document, parsed_data, confidence, result
                )
            elif document.type == DocumentType.RATE_CON:
                await self._process_ratecon_flags(
                    document, parsed_data, confidence, result
                )
            elif document.type == DocumentType.POD:
                await self._process_pod_flags(document, parsed_data, confidence, result)
            else:
                raise ValueError(f"Unsupported document type: {document.type}")

            logger.info(f"Flag processing completed for document {document.id}")

        except Exception as e:
            error_msg = f"Failed to process flags for document {document.id}: {str(e)}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            raise

        return result

    async def _process_cdl_flags(
        self,
        document: Document,
        parsed_data: dict[str, Any],
        confidence: float,
        result: dict[str, Any],
    ) -> None:
        """Process CDL document flags."""
        if not document.driver_id:
            raise ValueError("CDL document must have driver_id")

        cdl_data = CDLData(**parsed_data)

        # Business rule: CDL verified if confidence>=0.9 AND expiry>today+30
        if confidence >= self.MIN_CONFIDENCE_THRESHOLD:
            result["business_rules_applied"].append(
                f"Confidence threshold met: {confidence:.2f} >= {self.MIN_CONFIDENCE_THRESHOLD}"
            )

            # Check expiry date requirement
            if cdl_data.expiration_date:
                min_expiry_date = datetime.now(UTC) + timedelta(
                    days=self.CDL_MIN_DAYS_BEFORE_EXPIRY
                )

                if cdl_data.expiration_date > min_expiry_date:
                    # CDL meets all requirements - mark as verified
                    await self.supabase.update_driver_flags(
                        document.driver_id, cdl_verified=True
                    )
                    result["flags_updated"]["cdl_verified"] = True
                    result["business_rules_applied"].append(
                        f"CDL expiry valid: {cdl_data.expiration_date} > {min_expiry_date}"
                    )
                    logger.info(f"CDL verified for driver {document.driver_id}")
                else:
                    result["business_rules_applied"].append(
                        f"CDL expiry too soon: {cdl_data.expiration_date} <= {min_expiry_date}"
                    )
                    logger.warning(
                        f"CDL expiry too soon for driver {document.driver_id}"
                    )
            else:
                result["business_rules_applied"].append(
                    "CDL expiry date not found - cannot verify"
                )
                logger.warning(
                    f"CDL missing expiry date for driver {document.driver_id}"
                )
        else:
            result["business_rules_applied"].append(
                f"Confidence too low: {confidence:.2f} < {self.MIN_CONFIDENCE_THRESHOLD}"
            )

    async def _process_coi_flags(
        self,
        document: Document,
        parsed_data: dict[str, Any],
        confidence: float,
        result: dict[str, Any],
    ) -> None:
        """Process COI (Certificate of Insurance) document flags."""
        if not document.driver_id:
            raise ValueError("COI document must have driver_id")

        coi_data = COIData(**parsed_data)

        # Business rule: COI verified if confidence>=0.9 AND not expired
        if confidence >= self.MIN_CONFIDENCE_THRESHOLD:
            result["business_rules_applied"].append(
                f"Confidence threshold met: {confidence:.2f} >= {self.MIN_CONFIDENCE_THRESHOLD}"
            )

            # Check if insurance is not expired
            if coi_data.expiration_date:
                current_date = datetime.now(UTC)

                if coi_data.expiration_date > current_date:
                    # COI is not expired - mark as verified
                    await self.supabase.update_driver_flags(
                        document.driver_id, insurance_verified=True
                    )
                    result["flags_updated"]["insurance_verified"] = True
                    result["business_rules_applied"].append(
                        f"COI not expired: {coi_data.expiration_date} > {current_date}"
                    )
                    logger.info(f"COI verified for driver {document.driver_id}")
                else:
                    result["business_rules_applied"].append(
                        f"COI expired: {coi_data.expiration_date} <= {current_date}"
                    )
                    logger.warning(f"COI expired for driver {document.driver_id}")
            else:
                result["business_rules_applied"].append(
                    "COI expiry date not found - cannot verify"
                )
                logger.warning(
                    f"COI missing expiry date for driver {document.driver_id}"
                )
        else:
            result["business_rules_applied"].append(
                f"Confidence too low: {confidence:.2f} < {self.MIN_CONFIDENCE_THRESHOLD}"
            )

    async def _process_agreement_flags(
        self,
        document: Document,
        parsed_data: dict[str, Any],
        confidence: float,
        result: dict[str, Any],
    ) -> None:
        """Process Agreement document flags."""
        if not document.driver_id:
            raise ValueError("Agreement document must have driver_id")

        agreement_data = AgreementData(**parsed_data)

        # Business rule: Agreement signed if confidence>=0.9
        if confidence >= self.MIN_CONFIDENCE_THRESHOLD:
            result["business_rules_applied"].append(
                f"Confidence threshold met: {confidence:.2f} >= {self.MIN_CONFIDENCE_THRESHOLD}"
            )

            # Additional check: signature should be detected for higher confidence
            if agreement_data.signature_detected:
                await self.supabase.update_driver_flags(
                    document.driver_id, agreement_signed=True
                )
                result["flags_updated"]["agreement_signed"] = True
                result["business_rules_applied"].append(
                    "Signature detected in agreement"
                )
                logger.info(f"Agreement verified for driver {document.driver_id}")
            else:
                # Still mark as signed if confidence is high, even without detected signature
                await self.supabase.update_driver_flags(
                    document.driver_id, agreement_signed=True
                )
                result["flags_updated"]["agreement_signed"] = True
                result["business_rules_applied"].append(
                    "Agreement signed based on high confidence (no signature detection)"
                )
                logger.info(
                    f"Agreement verified for driver {document.driver_id} (no signature detected)"
                )
        else:
            result["business_rules_applied"].append(
                f"Confidence too low: {confidence:.2f} < {self.MIN_CONFIDENCE_THRESHOLD}"
            )

    async def _process_ratecon_flags(
        self,
        document: Document,
        parsed_data: dict[str, Any],
        confidence: float,
        result: dict[str, Any],
    ) -> None:
        """Process Rate Confirmation document flags."""
        if not document.load_id:
            raise ValueError("Rate confirmation document must have load_id")

        ratecon_data = RateConData(**parsed_data)

        # Business rule: Rate confirmation verified if rate+origin+dest present
        # Note: confidence threshold is less strict for rate confirmations
        required_fields = []
        has_rate = ratecon_data.rate_amount is not None and ratecon_data.rate_amount > 0
        has_origin = (
            ratecon_data.origin is not None and len(ratecon_data.origin.strip()) > 0
        )
        has_destination = (
            ratecon_data.destination is not None
            and len(ratecon_data.destination.strip()) > 0
        )

        if has_rate:
            required_fields.append("rate")
        if has_origin:
            required_fields.append("origin")
        if has_destination:
            required_fields.append("destination")

        result["business_rules_applied"].append(
            f"Required fields present: {required_fields}"
        )

        if has_rate and has_origin and has_destination:
            # All required fields present - mark rate confirmation as verified
            # Update load with ratecon_verified flag (this may need custom implementation)
            await self._update_load_ratecon_verified(document.load_id, True)
            result["flags_updated"]["ratecon_verified"] = True
            result["business_rules_applied"].append(
                "All required fields present: rate, origin, destination"
            )
            logger.info(f"Rate confirmation verified for load {document.load_id}")
        else:
            missing_fields = []
            if not has_rate:
                missing_fields.append("rate")
            if not has_origin:
                missing_fields.append("origin")
            if not has_destination:
                missing_fields.append("destination")

            result["business_rules_applied"].append(
                f"Missing required fields: {missing_fields}"
            )
            logger.warning(
                f"Rate confirmation incomplete for load {document.load_id}: missing {missing_fields}"
            )

    async def _process_pod_flags(
        self,
        document: Document,
        parsed_data: dict[str, Any],
        confidence: float,
        result: dict[str, Any],
    ) -> None:
        """Process POD (Proof of Delivery) document flags."""
        if not document.load_id:
            raise ValueError("POD document must have load_id")

        pod_data = PODData(**parsed_data)

        # Business rule: Load status='delivered' if confidence>=0.9
        if confidence >= self.MIN_CONFIDENCE_THRESHOLD:
            result["business_rules_applied"].append(
                f"Confidence threshold met: {confidence:.2f} >= {self.MIN_CONFIDENCE_THRESHOLD}"
            )

            # Additional validation: delivery should be confirmed
            if pod_data.delivery_confirmed:
                await self.supabase.update_load_status(
                    document.load_id, LoadStatus.DELIVERED
                )
                result["flags_updated"]["status"] = LoadStatus.DELIVERED
                result["business_rules_applied"].append(
                    "Delivery confirmed - load marked as delivered"
                )
                logger.info(f"Load {document.load_id} marked as delivered")

                # Also trigger invoice readiness check if rate confirmation is also verified
                await self._check_invoice_readiness(document.load_id, result)
            else:
                result["business_rules_applied"].append("Delivery not confirmed in POD")
                logger.warning(
                    f"POD for load {document.load_id} has high confidence but delivery not confirmed"
                )
        else:
            result["business_rules_applied"].append(
                f"Confidence too low: {confidence:.2f} < {self.MIN_CONFIDENCE_THRESHOLD}"
            )

    async def _update_load_ratecon_verified(
        self, load_id: str | UUID, verified: bool
    ) -> None:
        """
        Update load rate confirmation verified status.

        This is a custom method since the Load model doesn't have a direct ratecon_verified field.
        We use the document verification system to track this.
        """
        try:
            # For now, we'll track this through the document verification
            # In a full implementation, you might add a flags field to loads table
            # or use a separate verification tracking system

            # Update any existing RATE_CON documents for this load to verified status
            (
                self.supabase.client.table("documents")
                .update({"verified": verified})
                .eq("load_id", str(load_id))
                .eq("type", "RATE_CON")
                .execute()
            )

            logger.info(
                f"Updated rate confirmation verification for load {load_id}: {verified}"
            )

        except Exception as e:
            logger.error(
                f"Failed to update rate confirmation status for load {load_id}: {e}"
            )
            raise

    async def _check_invoice_readiness(
        self, load_id: str | UUID, result: dict[str, Any]
    ) -> None:
        """
        Check if load is ready for invoicing (POD completed + rate confirmation verified).

        This implements additional business logic for invoice generation triggers.
        """
        try:
            # Check if rate confirmation is also verified for this load
            ratecon_verified = await self.supabase.check_load_ratecon_verified(load_id)

            if ratecon_verified:
                result["business_rules_applied"].append(
                    "Invoice ready: POD completed + rate confirmation verified"
                )
                result["invoice_ready"] = True
                logger.info(f"Load {load_id} is ready for invoicing")

                # Get load details to find driver_id for event emission
                load = await self.supabase.get_load_by_id(load_id)
                if load and load.assigned_driver_id:
                    # Emit invoice ready event
                    await self.redis_event_service.emit_invoice_ready(
                        load_id=load.id, driver_id=load.assigned_driver_id
                    )
                    result["event_emitted"] = True
                    result["business_rules_applied"].append(
                        "Invoice ready event emitted to Redis"
                    )
                else:
                    logger.warning(
                        f"Cannot emit invoice_ready event for load {load_id}: assigned_driver_id not found"
                    )
                    result["business_rules_applied"].append(
                        "Invoice ready event not emitted: assigned_driver_id missing"
                    )

            else:
                result["business_rules_applied"].append(
                    "Invoice not ready: rate confirmation not verified"
                )
                result["invoice_ready"] = False

        except Exception as e:
            logger.error(f"Failed to check invoice readiness for load {load_id}: {e}")
            # Don't raise - this is a secondary check that shouldn't fail the main operation

    async def get_driver_verification_status(
        self, driver_id: str | UUID
    ) -> dict[str, Any]:
        """
        Get comprehensive verification status for a driver.

        Args:
            driver_id: Driver UUID

        Returns:
            Dict with verification status and details
        """
        try:
            driver = await self.supabase.get_driver_by_id(driver_id)
            if not driver:
                raise ValueError(f"Driver {driver_id} not found")

            return {
                "driver_id": str(driver_id),
                "doc_flags": driver.doc_flags.model_dump(),
                "status": driver.status,
                "verification_complete": (
                    driver.doc_flags.cdl_verified
                    and driver.doc_flags.insurance_verified
                    and driver.doc_flags.agreement_signed
                ),
                "updated_at": driver.updated_at.isoformat(),
            }

        except Exception as e:
            logger.error(
                f"Failed to get driver verification status for {driver_id}: {e}"
            )
            raise

    async def get_load_verification_status(
        self, load_id: str | UUID
    ) -> dict[str, Any]:
        """
        Get comprehensive verification status for a load.

        Args:
            load_id: Load UUID

        Returns:
            Dict with verification status and details
        """
        try:
            load = await self.supabase.get_load_by_id(load_id)
            if not load:
                raise ValueError(f"Load {load_id} not found")

            ratecon_verified = await self.supabase.check_load_ratecon_verified(load_id)
            pod_completed = load.status == LoadStatus.DELIVERED

            return {
                "load_id": str(load_id),
                "status": load.status,
                "ratecon_verified": ratecon_verified,
                "pod_completed": pod_completed,
                "invoice_ready": ratecon_verified and pod_completed,
                "origin": load.origin,
                "destination": load.destination,
                "rate": load.rate,
            }

        except Exception as e:
            logger.error(f"Failed to get load verification status for {load_id}: {e}")
            raise


# Global service instance
database_flag_service = DatabaseFlagUpdateService()

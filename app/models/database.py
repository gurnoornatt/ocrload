"""Database models for OCR document processing service.

This module defines Pydantic models that map to the existing Supabase database schema.
The models work with the current tables without modification, adapting to existing
column names and data types.
"""

import re
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class DocumentType(str, Enum):
    """Document types supported by the OCR system."""

    CDL = "CDL"
    COI = "COI"
    AGREEMENT = "AGREEMENT"
    RATE_CON = "RATE_CON"
    POD = "POD"
    INVOICE = "INVOICE"
    LUMPER = "LUMPER"


class DocumentStatus(str, Enum):
    """Status of document processing."""

    PENDING = "pending"
    PARSED = "parsed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class DriverStatus(str, Enum):
    """Driver verification status."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    INCOMPLETE = "incomplete"


class LoadStatus(str, Enum):
    """Load processing status."""

    AVAILABLE = "available"
    ASSIGNED = "assigned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class AuditResultStatus(str, Enum):
    """Audit result status."""
    
    PASSED = "passed"
    FAILED = "failed"


class DiscrepancyResolutionStatus(str, Enum):
    """Discrepancy resolution status."""
    
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"


class RateType(str, Enum):
    """Contract rate types."""
    
    FLAT = "flat"
    VARIABLE = "variable"


class PeriodType(str, Enum):
    """Analytics period types."""
    
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class ApprovalStatus(str, Enum):
    """Approval status for charges."""
    
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


# Document Flags Schema (stored in drivers.doc_flags JSONB)
class DocumentFlags(BaseModel):
    """Document verification flags for drivers."""

    cdl_verified: bool = False
    insurance_verified: bool = False
    agreement_signed: bool = False

    model_config = {
        "json_schema_extra": {
            "example": {
                "cdl_verified": True,
                "insurance_verified": True,
                "agreement_signed": False,
            }
        }
    }


# Load Flags Schema (for rate confirmation verification)
class LoadFlags(BaseModel):
    """Flags for load document verification."""

    ratecon_verified: bool = False
    pod_completed: bool = False

    model_config = {
        "json_schema_extra": {
            "example": {"ratecon_verified": True, "pod_completed": False}
        }
    }


# Parsed Document Data Schemas
class CDLData(BaseModel):
    """Parsed data from CDL documents."""

    driver_name: str | None = None
    license_number: str | None = None
    expiration_date: datetime | None = None
    license_class: str | None = None
    address: str | None = None
    state: str | None = None

    @field_validator("expiration_date", mode="before")
    @classmethod
    def parse_expiration_date(cls, v):
        """Parse various date formats from OCR text."""
        if not v:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            # Handle common date formats from OCR
            date_patterns = [
                r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})",  # MM/DD/YYYY or MM-DD-YYYY
                r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})",  # YYYY/MM/DD or YYYY-MM-DD
                r"(\d{1,2})[/-](\d{1,2})[/-](\d{2})",  # MM/DD/YY or MM-DD-YY
            ]
            for pattern in date_patterns:
                match = re.search(pattern, v)
                if match:
                    try:
                        if len(match.group(3)) == 4:  # Full year
                            # Handle both YYYY/MM/DD and MM/DD/YYYY formats
                            g1, g2, g3 = (
                                int(match.group(1)),
                                int(match.group(2)),
                                int(match.group(3)),
                            )
                            if g1 > 12 and g1 > 1900:  # Looks like YYYY/MM/DD
                                return datetime(g1, g2, g3)
                            else:  # MM/DD/YYYY format
                                return datetime(g3, g1, g2)
                        else:  # Two-digit year
                            year = int(match.group(3))
                            year = 2000 + year if year < 50 else 1900 + year
                            return datetime(
                                year, int(match.group(1)), int(match.group(2))
                            )
                    except (ValueError, IndexError):
                        continue
        return v


class COIData(BaseModel):
    """Parsed data from Certificate of Insurance documents."""

    policy_number: str | None = None
    insurance_company: str | None = None
    general_liability_amount: int | None = None  # in cents
    auto_liability_amount: int | None = None  # in cents
    effective_date: datetime | None = None
    expiration_date: datetime | None = None

    @field_validator("general_liability_amount", "auto_liability_amount", mode="before")
    @classmethod
    def parse_currency_amount(cls, v):
        """Parse currency amounts to cents."""
        if not v:
            return None
        if isinstance(v, str):
            # Remove currency symbols and convert to cents
            amount_str = re.sub(r"[$,\s]", "", v)
            try:
                amount = float(amount_str)
                return int(amount * 100)  # Convert to cents
            except ValueError:
                return None
        return v


class AgreementData(BaseModel):
    """Parsed data from agreement documents."""

    signature_detected: bool = False
    signing_date: datetime | None = None
    agreement_type: str | None = None
    key_terms: list[str] | None = None


class RateConData(BaseModel):
    """Parsed data from rate confirmation documents."""

    rate_amount: int | None = None  # in cents
    origin: str | None = None
    destination: str | None = None
    pickup_date: datetime | None = None
    delivery_date: datetime | None = None
    weight: float | None = None
    commodity: str | None = None

    @field_validator("rate_amount", mode="before")
    @classmethod
    def parse_rate_amount(cls, v):
        """Parse rate amounts to cents."""
        if not v:
            return None
        if isinstance(v, str):
            # Handle formats like "$2,500", "2500.00", etc.
            rate_str = re.sub(r"[$,\s]", "", v)
            try:
                rate = float(rate_str)
                return int(rate * 100)  # Convert to cents
            except ValueError:
                return None
        return v


class PODData(BaseModel):
    """Parsed data from Proof of Delivery documents."""

    delivery_confirmed: bool = False
    delivery_date: datetime | None = None
    receiver_name: str | None = None
    signature_present: bool = False
    delivery_notes: str | None = None


# Union type for all parsed document data
ParsedDocumentData = Union[CDLData, COIData, AgreementData, RateConData, PODData]


class BaseDBModel(BaseModel):
    """Base model for database entities."""

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"from_attributes": True}


class Document(BaseDBModel):
    """Model for documents table in the database."""

    driver_id: UUID | None = None
    load_id: UUID | None = None
    type: DocumentType  # Maps to existing 'type' column
    url: str  # Maps to existing 'url' column (not raw_url as in PRD)
    status: DocumentStatus = Field(
        default=DocumentStatus.PENDING
    )  # Document processing status
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    parsed_data: dict[str, Any] | None = None  # JSONB column
    verified: bool | None = None  # Existing boolean column
    metadata: dict[str, Any] | None = None  # Additional metadata (file info, errors, etc.)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, v):
        """Ensure confidence is between 0 and 1."""
        if v is not None and (v < 0 or v > 1):
            raise ValueError("Confidence must be between 0 and 1")
        return v

    @model_validator(mode="after")
    def validate_required_associations(self):
        """Ensure either driver_id or load_id is provided for relevant document types."""
        if self.type in [DocumentType.CDL, DocumentType.COI, DocumentType.AGREEMENT]:
            if not self.driver_id:
                raise ValueError(f"{self.type} documents require a driver_id")
        return self

    def get_parsed_data_typed(self) -> ParsedDocumentData | None:
        """Get parsed data as the appropriate typed model."""
        if not self.parsed_data:
            return None
        try:
            if self.type == DocumentType.CDL:
                return CDLData(**self.parsed_data)
            elif self.type == DocumentType.COI:
                return COIData(**self.parsed_data)
            elif self.type == DocumentType.AGREEMENT:
                return AgreementData(**self.parsed_data)
            elif self.type == DocumentType.RATE_CON:
                return RateConData(**self.parsed_data)
            elif self.type == DocumentType.POD:
                return PODData(**self.parsed_data)
        except (ValueError, TypeError, KeyError):
            return None
        return None


# Driver Model (maps to drivers table)
class Driver(BaseDBModel):
    """Model for drivers table in the database."""

    phone_number: str = Field(..., min_length=10)
    language: str = Field(default="English")
    wallet_id: str | None = None
    doc_flags: DocumentFlags = Field(default_factory=DocumentFlags)
    status: DriverStatus = Field(default=DriverStatus.PENDING)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v):
        """Basic phone number validation."""
        # Remove non-digits
        digits = re.sub(r"\D", "", v)
        if len(digits) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return v

    def update_doc_flags(self, **flags) -> None:
        """Update document verification flags."""
        current_flags = self.doc_flags.model_dump()
        current_flags.update(flags)
        self.doc_flags = DocumentFlags(**current_flags)
        self.updated_at = datetime.now(UTC)


# Load Model (maps to loads table)
class Load(BaseDBModel):
    """Model for loads table in the database."""

    origin: str | None = None
    destination: str | None = None
    rate: int | None = None  # in cents
    negotiated_rate: int | None = None  # in cents
    assigned_driver_id: UUID | None = None
    status: LoadStatus = Field(default=LoadStatus.AVAILABLE)
    score: float | None = None
    lane_hash: str | None = None
    equipment: str | None = None

    @field_validator("rate", "negotiated_rate")
    @classmethod
    def validate_rate(cls, v):
        """Ensure rates are positive."""
        if v is not None and v < 0:
            raise ValueError("Rate must be positive")
        return v

    def get_rate_in_dollars(self) -> float | None:
        """Get rate converted from cents to dollars."""
        if self.rate is not None:
            return self.rate / 100.0
        return None

    def set_rate_from_dollars(self, dollars: float) -> None:
        """Set rate from dollar amount (converts to cents)."""
        self.rate = int(dollars * 100)


# Transaction Model (maps to transactions table if it exists)
class Transaction(BaseDBModel):
    """Model for transactions table in the database."""

    driver_id: UUID
    load_id: UUID | None = None
    amount: int  # in cents
    type: str
    status: str = "pending"
    reference: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        """Ensure amount is not negative."""
        if v < 0:
            raise ValueError("Transaction amount cannot be negative")
        return v


# Freight Audit Models
class AuditResult(BaseDBModel):
    """Model for audit_results table."""

    audit_id: UUID = Field(default_factory=uuid4)
    document_id: UUID | None = None
    result_status: AuditResultStatus
    audit_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditDiscrepancy(BaseDBModel):
    """Model for audit_discrepancies table."""

    discrepancy_id: UUID = Field(default_factory=uuid4)
    audit_id: UUID
    description: str
    resolution_status: DiscrepancyResolutionStatus = Field(default=DiscrepancyResolutionStatus.UNRESOLVED)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolved_by: str | None = None


class ContractRate(BaseDBModel):
    """Model for contract_rates table."""

    rate_id: UUID = Field(default_factory=uuid4)
    carrier_id: UUID | None = None
    rate_type: RateType
    rate_value: float = Field(..., ge=0)
    origin: str | None = None
    destination: str | None = None
    equipment_type: str | None = None
    effective_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expiration_date: datetime | None = None
    is_active: bool = Field(default=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SpendAnalytics(BaseDBModel):
    """Model for spend_analytics table."""

    analytics_id: UUID = Field(default_factory=uuid4)
    period: datetime
    period_type: PeriodType = Field(default=PeriodType.MONTHLY)
    total_spend: float = Field(default=0, ge=0)
    savings: float | None = Field(default=0)
    load_count: int | None = Field(default=0, ge=0)
    average_rate: float | None = None
    carrier_count: int | None = Field(default=0, ge=0)
    top_lanes: dict[str, Any] | None = None
    cost_breakdown: dict[str, Any] | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Document Parsing Models
class Invoice(BaseDBModel):
    """Model for invoices table."""

    document_id: UUID
    invoice_number: str | None = None
    invoice_date: datetime | None = None
    due_date: datetime | None = None
    vendor_name: str | None = None
    vendor_address: str | None = None
    customer_name: str | None = None
    customer_address: str | None = None
    subtotal: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    currency: str = Field(default="USD")
    payment_terms: str | None = None
    line_items: list[dict[str, Any]] | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BillOfLading(BaseDBModel):
    """Model for bills_of_lading table."""

    document_id: UUID
    bol_number: str | None = None
    pro_number: str | None = None
    pickup_date: datetime | None = None
    delivery_date: datetime | None = None
    shipper_name: str | None = None
    shipper_address: str | None = None
    consignee_name: str | None = None
    consignee_address: str | None = None
    carrier_name: str | None = None
    driver_name: str | None = None
    equipment_type: str | None = None
    equipment_number: str | None = None
    commodity_description: str | None = None
    weight: float | None = None
    pieces: int | None = None
    hazmat: bool = Field(default=False)
    freight_charges: float | None = None
    special_instructions: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LumperReceipt(BaseDBModel):
    """Model for lumper_receipts table."""

    document_id: UUID
    receipt_number: str | None = None
    receipt_date: datetime | None = None
    facility_name: str | None = None
    facility_address: str | None = None
    driver_name: str | None = None
    carrier_name: str | None = None
    bol_number: str | None = None
    service_type: str | None = None
    labor_hours: float | None = None
    hourly_rate: float | None = None
    total_amount: float | None = None
    equipment_used: str | None = None
    special_services: list[dict[str, Any]] | None = None
    notes: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AccessorialCharge(BaseDBModel):
    """Model for accessorial_charges table."""

    document_id: UUID
    charge_number: str | None = None
    charge_date: datetime | None = None
    carrier_name: str | None = None
    bol_number: str | None = None
    pro_number: str | None = None
    charge_type: str | None = None
    charge_description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    total_amount: float | None = None
    justification: str | None = None
    supporting_docs: list[dict[str, Any]] | None = None
    approval_status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    approved_by: str | None = None
    approved_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Request/Response Models for API endpoints
class DocumentCreateRequest(BaseModel):
    """Request model for creating a document."""

    driver_id: UUID | None = None
    load_id: UUID | None = None
    doc_type: DocumentType
    media_url: str

    @model_validator(mode="after")
    def validate_ids(self):
        """Ensure either driver_id or load_id is provided."""
        if not self.driver_id and not self.load_id:
            raise ValueError("Either driver_id or load_id must be provided")
        return self


class DocumentProcessingResponse(BaseModel):
    """Standard response model for document processing."""

    success: bool
    doc_id: UUID
    needs_retry: bool = False
    confidence: float
    flags: dict[str, bool]  # Current verification flags
    message: str | None = None
    processing_time_ms: int | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "doc_id": "123e4567-e89b-12d3-a456-426614174000",
                "needs_retry": False,
                "confidence": 0.95,
                "flags": {
                    "cdl_verified": True,
                    "insurance_verified": False,
                    "agreement_signed": False,
                    "ratecon_verified": False,
                    "pod_completed": False,
                },
                "message": "CDL processed successfully",
                "processing_time_ms": 2500,
            }
        }
    }


class ParseTestRequest(BaseModel):
    """Request model for parse-test endpoint."""

    path: str = Field(..., min_length=1)
    doc_type: DocumentType

    @field_validator("path")
    @classmethod
    def validate_path_security(cls, v):
        """Prevent directory traversal attacks."""
        if ".." in v or v.startswith("/"):
            if not v.startswith("/app/") and not v.startswith("./"):
                raise ValueError("Invalid file path")
        return v


# Health Check Models
class ServiceHealthStatus(BaseModel):
    """Health status for individual services."""

    status: str  # "healthy", "limited", "warning", "unhealthy"
    message: str
    details: dict[str, Any] | None = None


class HealthCheckResponse(BaseModel):
    """Comprehensive health check response."""

    ok: bool
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: datetime
    service: str
    version: str
    environment: str
    checks: dict[str, ServiceHealthStatus]
    response_time_ms: float

    model_config = {
        "json_schema_extra": {
            "example": {
                "ok": True,
                "status": "healthy",
                "timestamp": "2024-01-15T12:00:00Z",
                "service": "ocr-load-service",
                "version": "1.0.0",
                "environment": "production",
                "checks": {
                    "database": {
                        "status": "healthy",
                        "message": "Connected to Supabase",
                    },
                    "storage": {
                        "status": "healthy",
                        "message": "Storage bucket accessible",
                    },
                },
                "response_time_ms": 45.2,
            }
        }
    }

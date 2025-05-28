"""Database models for OCR document processing service.

This module defines Pydantic models that map to the existing Supabase database schema.
The models work with the current tables without modification, adapting to existing
column names and data types.
"""

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.types import Json


class DocumentType(str, Enum):
    """Document types supported by the OCR system."""
    CDL = "CDL"
    COI = "COI" 
    AGREEMENT = "AGREEMENT"
    RATE_CON = "RATE_CON"
    POD = "POD"


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
                "agreement_signed": False
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
            "example": {
                "ratecon_verified": True,
                "pod_completed": False
            }
        }
    }


# Parsed Document Data Schemas
class CDLData(BaseModel):
    """Parsed data from CDL documents."""
    driver_name: Optional[str] = None
    license_number: Optional[str] = None
    expiration_date: Optional[datetime] = None
    license_class: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    
    @field_validator('expiration_date', mode='before')
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
                r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # MM/DD/YYYY or MM-DD-YYYY
                r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # YYYY/MM/DD or YYYY-MM-DD
                r'(\d{1,2})[/-](\d{1,2})[/-](\d{2})',  # MM/DD/YY or MM-DD-YY
            ]
            for pattern in date_patterns:
                match = re.search(pattern, v)
                if match:
                    try:
                        if len(match.group(3)) == 4:  # Full year
                            # Handle both YYYY/MM/DD and MM/DD/YYYY formats
                            g1, g2, g3 = int(match.group(1)), int(match.group(2)), int(match.group(3))
                            if g1 > 12 and g1 > 1900:  # Looks like YYYY/MM/DD
                                return datetime(g1, g2, g3)
                            else:  # MM/DD/YYYY format
                                return datetime(g3, g1, g2)
                        else:  # Two-digit year
                            year = int(match.group(3))
                            year = 2000 + year if year < 50 else 1900 + year
                            return datetime(year, int(match.group(1)), int(match.group(2)))
                    except (ValueError, IndexError):
                        continue
        return v


class COIData(BaseModel):
    """Parsed data from Certificate of Insurance documents."""
    policy_number: Optional[str] = None
    insurance_company: Optional[str] = None
    general_liability_amount: Optional[int] = None  # in cents
    auto_liability_amount: Optional[int] = None  # in cents
    effective_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    
    @field_validator('general_liability_amount', 'auto_liability_amount', mode='before')
    @classmethod
    def parse_currency_amount(cls, v):
        """Parse currency amounts to cents."""
        if not v:
            return None
        if isinstance(v, str):
            # Remove currency symbols and convert to cents
            amount_str = re.sub(r'[$,\s]', '', v)
            try:
                amount = float(amount_str)
                return int(amount * 100)  # Convert to cents
            except ValueError:
                return None
        return v


class AgreementData(BaseModel):
    """Parsed data from agreement documents."""
    signature_detected: bool = False
    signing_date: Optional[datetime] = None
    agreement_type: Optional[str] = None
    key_terms: Optional[List[str]] = None


class RateConData(BaseModel):
    """Parsed data from rate confirmation documents."""
    rate_amount: Optional[int] = None  # in cents
    origin: Optional[str] = None
    destination: Optional[str] = None
    pickup_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    weight: Optional[float] = None
    commodity: Optional[str] = None
    
    @field_validator('rate_amount', mode='before')
    @classmethod
    def parse_rate_amount(cls, v):
        """Parse rate amounts to cents."""
        if not v:
            return None
        if isinstance(v, str):
            # Handle formats like "$2,500", "2500.00", etc.
            rate_str = re.sub(r'[$,\s]', '', v)
            try:
                rate = float(rate_str)
                return int(rate * 100)  # Convert to cents
            except ValueError:
                return None
        return v


class PODData(BaseModel):
    """Parsed data from Proof of Delivery documents."""
    delivery_confirmed: bool = False
    delivery_date: Optional[datetime] = None
    receiver_name: Optional[str] = None
    signature_present: bool = False
    delivery_notes: Optional[str] = None


# Union type for all parsed data types
ParsedDocumentData = Union[CDLData, COIData, AgreementData, RateConData, PODData]


# Base Database Models
class BaseDBModel(BaseModel):
    """Base model for database entities."""
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = {
        "from_attributes": True
    }


# Document Model (maps to documents table)
class Document(BaseDBModel):
    """Model for documents table in the database."""
    driver_id: Optional[UUID] = None
    load_id: Optional[UUID] = None
    type: DocumentType  # Maps to existing 'type' column
    url: str  # Maps to existing 'url' column (not raw_url as in PRD)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    parsed_data: Optional[Dict[str, Any]] = None  # JSONB column
    verified: Optional[bool] = None  # Existing boolean column
    
    @field_validator('confidence', mode='before')
    @classmethod  
    def validate_confidence(cls, v):
        """Ensure confidence is between 0 and 1."""
        if v is not None:
            return max(0.0, min(1.0, float(v)))
        return v
    
    @model_validator(mode='after')
    def validate_required_associations(self):
        """Ensure document has either driver_id or load_id."""
        if not self.driver_id and not self.load_id:
            raise ValueError("Document must have either driver_id or load_id")
        return self
    
    def get_parsed_data_typed(self) -> Optional[ParsedDocumentData]:
        """Get parsed_data as a typed model based on document type."""
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
    wallet_id: Optional[str] = None
    doc_flags: DocumentFlags = Field(default_factory=DocumentFlags)
    status: DriverStatus = Field(default=DriverStatus.PENDING)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @field_validator('phone_number')
    @classmethod
    def validate_phone_number(cls, v):
        """Basic phone number validation."""
        # Remove non-digits
        digits = re.sub(r'\D', '', v)
        if len(digits) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return v
    
    def update_doc_flags(self, **flags) -> None:
        """Update document verification flags."""
        current_flags = self.doc_flags.model_dump()
        current_flags.update(flags)
        self.doc_flags = DocumentFlags(**current_flags)
        self.updated_at = datetime.now(timezone.utc)


# Load Model (maps to loads table)
class Load(BaseDBModel):
    """Model for loads table in the database."""
    origin: Optional[str] = None
    destination: Optional[str] = None
    rate: Optional[int] = None  # in cents
    negotiated_rate: Optional[int] = None  # in cents
    assigned_driver_id: Optional[UUID] = None
    status: LoadStatus = Field(default=LoadStatus.AVAILABLE)
    score: Optional[float] = None
    lane_hash: Optional[str] = None
    equipment: Optional[str] = None
    
    @field_validator('rate', 'negotiated_rate')
    @classmethod
    def validate_rate(cls, v):
        """Ensure rates are positive."""
        if v is not None and v < 0:
            raise ValueError("Rate must be positive")
        return v
    
    def get_rate_in_dollars(self) -> Optional[float]:
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
    load_id: Optional[UUID] = None
    amount: int  # in cents
    type: str
    status: str = "pending"
    reference: Optional[str] = None
    
    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v):
        """Ensure amount is not negative."""
        if v < 0:
            raise ValueError("Transaction amount cannot be negative")
        return v


# Request/Response Models for API endpoints
class DocumentCreateRequest(BaseModel):
    """Request model for creating a document."""
    driver_id: Optional[UUID] = None
    load_id: Optional[UUID] = None
    doc_type: DocumentType
    media_url: str
    
    @model_validator(mode='after')
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
    flags: Dict[str, bool]  # Current verification flags
    message: Optional[str] = None
    processing_time_ms: Optional[int] = None
    
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
                    "pod_completed": False
                },
                "message": "CDL processed successfully",
                "processing_time_ms": 2500
            }
        }
    }


class ParseTestRequest(BaseModel):
    """Request model for parse-test endpoint."""
    path: str = Field(..., min_length=1)
    doc_type: DocumentType
    
    @field_validator('path')
    @classmethod
    def validate_path_security(cls, v):
        """Prevent directory traversal attacks."""
        if '..' in v or v.startswith('/'):
            if not v.startswith('/app/') and not v.startswith('./'):
                raise ValueError("Invalid file path")
        return v


# Health Check Models
class ServiceHealthStatus(BaseModel):
    """Health status for individual services."""
    status: str  # "healthy", "limited", "warning", "unhealthy"
    message: str
    details: Optional[Dict[str, Any]] = None


class HealthCheckResponse(BaseModel):
    """Comprehensive health check response."""
    ok: bool
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: datetime
    service: str
    version: str
    environment: str
    checks: Dict[str, ServiceHealthStatus]
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
                        "message": "Connected to Supabase"
                    },
                    "storage": {
                        "status": "healthy", 
                        "message": "Storage bucket accessible"
                    }
                },
                "response_time_ms": 45.2
            }
        }
    } 
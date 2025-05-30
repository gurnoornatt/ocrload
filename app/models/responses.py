"""Standardized response models for all API endpoints."""

import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentFlags(BaseModel):
    """Document verification flags."""
    cdl_verified: bool = Field(False, description="CDL document verified")
    insurance_verified: bool = Field(False, description="Insurance certificate verified")
    agreement_signed: bool = Field(False, description="Agreement document signed")
    ratecon_parsed: bool = Field(False, description="Rate confirmation parsed")
    pod_ok: bool = Field(False, description="Proof of delivery completed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cdl_verified": True,
                "insurance_verified": True,
                "agreement_signed": False,
                "ratecon_parsed": True,
                "pod_ok": False
            }
        }
    }


class StandardAPIResponse(BaseModel):
    """Standardized response model for all API endpoints."""
    success: bool = Field(..., description="Whether the operation was successful")
    doc_id: UUID = Field(..., description="Document ID for tracking")
    needs_retry: bool = Field(False, description="Whether the operation should be retried")
    confidence: float = Field(0.0, description="Processing confidence score (0.0-1.0)")
    flags: DocumentFlags = Field(default_factory=DocumentFlags, description="Document verification flags")
    message: Optional[str] = Field(None, description="Human-readable message")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Response timestamp")
    request_id: Optional[str] = Field(None, description="Request ID for tracing")
    processing_time_ms: Optional[int] = Field(None, description="Processing time in milliseconds")

    model_config = {
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat()
        },
        "json_schema_extra": {
            "example": {
                "success": True,
                "doc_id": "123e4567-e89b-12d3-a456-426614174000",
                "needs_retry": False,
                "confidence": 0.95,
                "flags": {
                    "cdl_verified": True,
                    "insurance_verified": True,
                    "agreement_signed": False,
                    "ratecon_parsed": True,
                    "pod_ok": False
                },
                "message": "Document processed successfully",
                "timestamp": "2024-01-15T12:00:00Z",
                "request_id": "req_12345",
                "processing_time_ms": 2500
            }
        }
    }


class MediaUploadResponse(StandardAPIResponse):
    """Response model for media upload endpoint."""
    processing_url: str = Field(..., description="URL to check processing status")
    
    model_config = {
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat()
        },
        "json_schema_extra": {
            "example": {
                "success": True,
                "doc_id": "123e4567-e89b-12d3-a456-426614174000",
                "needs_retry": False,
                "confidence": 0.0,
                "flags": {
                    "cdl_verified": False,
                    "insurance_verified": False,
                    "agreement_signed": False,
                    "ratecon_parsed": False,
                    "pod_ok": False
                },
                "message": "Document upload accepted and processing started",
                "timestamp": "2024-01-15T12:00:00Z",
                "request_id": "req_12345",
                "processing_url": "/api/media/123e4567-e89b-12d3-a456-426614174000/status"
            }
        }
    }


class ParseTestResponse(StandardAPIResponse):
    """Response model for parse-test endpoint."""
    processing_url: str = Field(..., description="URL to check processing status")
    
    model_config = {
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat()
        },
        "json_schema_extra": {
            "example": {
                "success": True,
                "doc_id": "123e4567-e89b-12d3-a456-426614174000", 
                "needs_retry": False,
                "confidence": 0.0,
                "flags": {
                    "cdl_verified": False,
                    "insurance_verified": False,
                    "agreement_signed": False,
                    "ratecon_parsed": False,
                    "pod_ok": False
                },
                "message": "Local file parsing accepted and processing started",
                "timestamp": "2024-01-15T12:00:00Z",
                "request_id": "req_12345",
                "processing_url": "/api/media/123e4567-e89b-12d3-a456-426614174000/status"
            }
        }
    }


class ProcessingStatusResponse(StandardAPIResponse):
    """Response model for processing status endpoint."""
    status: str = Field(..., description="Current processing status")
    progress: Dict[str, Any] = Field(..., description="Detailed progress information")
    result: Optional[Dict[str, Any]] = Field(None, description="Processing results if complete")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    model_config = {
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat()
        },
        "json_schema_extra": {
            "example": {
                "success": True,
                "doc_id": "123e4567-e89b-12d3-a456-426614174000",
                "needs_retry": False,
                "confidence": 0.95,
                "flags": {
                    "cdl_verified": True,
                    "insurance_verified": True,
                    "agreement_signed": False,
                    "ratecon_parsed": True,
                    "pod_ok": False
                },
                "message": "Document processing completed",
                "timestamp": "2024-01-15T12:00:00Z",
                "request_id": "req_12345",
                "status": "parsed",
                "progress": {
                    "step": "completed",
                    "completion": 100,
                    "message": "Document processing completed successfully"
                },
                "result": {
                    "extracted_text": "Document content...",
                    "parsed_data": {}
                }
            }
        }
    }


class ErrorResponse(BaseModel):
    """Standardized error response model."""
    success: bool = Field(False, description="Always false for error responses")
    error: str = Field(..., description="Error message")
    error_code: str = Field(..., description="Machine-readable error code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Error timestamp")
    request_id: Optional[str] = Field(None, description="Request ID for tracing")
    status_code: int = Field(..., description="HTTP status code")

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        },
        "json_schema_extra": {
            "example": {
                "success": False,
                "error": "Document not found",
                "error_code": "DOCUMENT_NOT_FOUND",
                "details": {
                    "doc_id": "123e4567-e89b-12d3-a456-426614174000",
                    "attempted_at": "2024-01-15T12:00:00Z"
                },
                "timestamp": "2024-01-15T12:00:00Z",
                "request_id": "req_12345",
                "status_code": 404
            }
        }
    }


class HealthCheckResponse(BaseModel):
    """Health check response model."""
    ok: bool = Field(..., description="Overall health status")
    status: str = Field(..., description="Health status (healthy/degraded/unhealthy)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Check timestamp")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    environment: str = Field(..., description="Environment (development/production)")
    checks: Dict[str, Dict[str, Any]] = Field(..., description="Individual service checks")
    response_time_ms: float = Field(..., description="Response time in milliseconds")

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        },
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
                        "status": "ok",
                        "message": "Connected to Supabase"
                    },
                    "storage": {
                        "status": "ok",
                        "message": "Storage bucket accessible"
                    }
                },
                "response_time_ms": 45.2
            }
        }
    } 
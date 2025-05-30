"""Custom exception classes for the OCR Load service."""

from typing import Optional, Dict, Any
from fastapi import HTTPException
from datetime import datetime, timezone


class OCRLoadException(Exception):
    """Base exception for OCR Load service."""
    
    def __init__(
        self, 
        message: str, 
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class ValidationError(OCRLoadException):
    """Raised when request validation fails."""
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR", 
            details=details
        )


class DocumentNotFoundError(OCRLoadException):
    """Raised when a document cannot be found."""
    
    def __init__(
        self, 
        document_id: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=f"Document {document_id} not found",
            error_code="DOCUMENT_NOT_FOUND",
            details={"document_id": document_id, **(details or {})}
        )


class FileNotFoundError(OCRLoadException):
    """Raised when a file cannot be found."""
    
    def __init__(
        self, 
        file_path: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=f"File not found: {file_path}",
            error_code="FILE_NOT_FOUND",
            details={"file_path": file_path, **(details or {})}
        )


class FileValidationError(OCRLoadException):
    """Raised when file validation fails."""
    
    def __init__(
        self, 
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code="FILE_VALIDATION_ERROR",
            details=details
        )


class DownloadError(OCRLoadException):
    """Raised when file download fails."""
    
    def __init__(
        self, 
        message: str,
        url: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if url:
            details["url"] = url
        
        super().__init__(
            message=message,
            error_code="DOWNLOAD_ERROR",
            details=details
        )


class StorageError(OCRLoadException):
    """Raised when storage operations fail."""
    
    def __init__(
        self, 
        message: str,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if operation:
            details["operation"] = operation
        
        super().__init__(
            message=message,
            error_code="STORAGE_ERROR",
            details=details
        )


class DatabaseError(OCRLoadException):
    """Raised when database operations fail."""
    
    def __init__(
        self, 
        message: str,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if operation:
            details["operation"] = operation
        
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            details=details
        )


class OCRError(OCRLoadException):
    """Raised when OCR processing fails."""
    
    def __init__(
        self, 
        message: str,
        provider: Optional[str] = None,
        retry_recommended: bool = False,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if provider:
            details["provider"] = provider
        details["retry_recommended"] = retry_recommended
        
        super().__init__(
            message=message,
            error_code="OCR_ERROR",
            details=details
        )


class OCRTimeoutError(OCRError):
    """Raised when OCR processing times out."""
    
    def __init__(
        self, 
        message: str,
        provider: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds
        
        super().__init__(
            message=message,
            provider=provider,
            retry_recommended=True,
            details=details
        )
        self.error_code = "OCR_TIMEOUT_ERROR"


class OCRRateLimitError(OCRError):
    """Raised when OCR rate limit is exceeded."""
    
    def __init__(
        self, 
        message: str,
        provider: Optional[str] = None,
        retry_after_seconds: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if retry_after_seconds:
            details["retry_after_seconds"] = retry_after_seconds
        
        super().__init__(
            message=message,
            provider=provider,
            retry_recommended=True,
            details=details
        )
        self.error_code = "OCR_RATE_LIMIT_ERROR"


class OCRAuthenticationError(OCRError):
    """Raised when OCR authentication fails."""
    
    def __init__(
        self, 
        message: str,
        provider: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            provider=provider,
            retry_recommended=False,
            details=details
        )
        self.error_code = "OCR_AUTHENTICATION_ERROR"


class DocumentParsingError(OCRLoadException):
    """Raised when document parsing fails."""
    
    def __init__(
        self, 
        message: str,
        doc_type: Optional[str] = None,
        confidence: Optional[float] = None,
        retry_recommended: bool = False,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if doc_type:
            details["doc_type"] = doc_type
        if confidence is not None:
            details["confidence"] = confidence
        details["retry_recommended"] = retry_recommended
        
        super().__init__(
            message=message,
            error_code="DOCUMENT_PARSING_ERROR",
            details=details
        )


class NetworkError(OCRLoadException):
    """Raised when network operations fail."""
    
    def __init__(
        self, 
        message: str,
        service: Optional[str] = None,
        retry_recommended: bool = True,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if service:
            details["service"] = service
        details["retry_recommended"] = retry_recommended
        
        super().__init__(
            message=message,
            error_code="NETWORK_ERROR",
            details=details
        )


class SecurityError(OCRLoadException):
    """Raised when security violations occur."""
    
    def __init__(
        self, 
        message: str,
        violation_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if violation_type:
            details["violation_type"] = violation_type
        
        super().__init__(
            message=message,
            error_code="SECURITY_ERROR",
            details=details
        )


class ConfigurationError(OCRLoadException):
    """Raised when configuration is invalid or missing."""
    
    def __init__(
        self, 
        message: str,
        config_key: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if config_key:
            details["config_key"] = config_key
        
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details=details
        )


# HTTP Exception Mappings
def to_http_exception(exc: OCRLoadException, request_id: Optional[str] = None) -> HTTPException:
    """Convert OCRLoadException to HTTPException with appropriate status code."""
    
    # Define status code mappings
    status_mappings = {
        "VALIDATION_ERROR": 422,
        "DOCUMENT_NOT_FOUND": 404,
        "FILE_NOT_FOUND": 404,
        "FILE_VALIDATION_ERROR": 400,
        "DOWNLOAD_ERROR": 400,
        "STORAGE_ERROR": 503,
        "DATABASE_ERROR": 503,
        "OCR_ERROR": 502,
        "OCR_TIMEOUT_ERROR": 504,
        "OCR_RATE_LIMIT_ERROR": 429,
        "OCR_AUTHENTICATION_ERROR": 502,
        "DOCUMENT_PARSING_ERROR": 422,
        "NETWORK_ERROR": 502,
        "SECURITY_ERROR": 403,
        "CONFIGURATION_ERROR": 500,
        "INTERNAL_ERROR": 500
    }
    
    status_code = status_mappings.get(exc.error_code, 500)
    
    # Build error detail
    error_detail = {
        "success": False,
        "error": exc.message,
        "error_code": exc.error_code,
        "details": exc.details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status_code": status_code
    }
    
    if request_id:
        error_detail["request_id"] = request_id
    
    return HTTPException(
        status_code=status_code,
        detail=error_detail
    ) 
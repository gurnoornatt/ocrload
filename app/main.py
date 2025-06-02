"""Main FastAPI application for OCR & Docs Micro-Service."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.settings import settings
from app.exceptions import OCRLoadException, to_http_exception
from app.models.responses import ErrorResponse
from app.services.performance_monitor import (
    PipelineStage,
    ProcessingStatus,
    log_performance_summary,
    performance_monitor,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class TimingMiddleware(BaseHTTPMiddleware):
    """Middleware to track request timing for performance monitoring."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and add timing headers."""
        start_time = time.time()

        # Add request ID for tracing
        request_id = f"{int(start_time * 1000)}-{hash(request.url.path)}"

        # Store request ID in request state for access in handlers
        request.state.request_id = request_id

        # Process request with performance tracking
        status = ProcessingStatus.SUCCESS
        error_type = None

        try:
            response = await call_next(request)

            # Determine status based on response code
            if response.status_code >= 500:
                status = ProcessingStatus.FAILURE
                error_type = f"HTTP_{response.status_code}"
            elif response.status_code >= 400:
                status = ProcessingStatus.FAILURE
                error_type = f"HTTP_{response.status_code}"

        except Exception as e:
            status = ProcessingStatus.FAILURE
            error_type = type(e).__name__
            raise

        finally:
            # Calculate timing
            process_time = time.time() - start_time

            # Record performance metric for non-monitoring endpoints
            if not request.url.path.startswith("/api/monitoring"):
                performance_monitor.record_metric(
                    stage=PipelineStage.TOTAL_PIPELINE,
                    status=status,
                    duration=process_time,
                    request_id=request_id,
                    error_type=error_type,
                    status_code=response.status_code if "response" in locals() else 500,
                    endpoint=request.url.path,
                    method=request.method,
                )

            # Add timing headers
            if "response" in locals():
                response.headers["X-Process-Time"] = str(process_time)
                response.headers["X-Request-ID"] = request_id

                # Log request info
                logger.info(
                    f"Request: {request.method} {request.url.path} "
                    f"Status: {response.status_code} "
                    f"Time: {process_time:.3f}s "
                    f"ID: {request_id}"
                )

        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Environment: {'development' if settings.debug else 'production'}")

    # Validate configuration
    try:
        is_valid = settings.validate_production_config()
        if is_valid:
            logger.info("✅ All configuration values properly set")
        else:
            logger.warning(
                "⚠️  Using placeholder configuration values - service may not function properly"
            )
    except ValueError as e:
        logger.error(f"❌ Configuration validation failed: {e}")
        raise

    # Start performance monitoring background task
    performance_task = asyncio.create_task(log_performance_summary())
    logger.info("Performance monitoring started")

    # TODO: Initialize connections (Supabase, Redis, etc.)
    # TODO: Validate API keys and external service connectivity

    yield

    # Shutdown
    logger.info("Shutting down application")

    # Cancel performance monitoring task
    performance_task.cancel()
    try:
        await performance_task
    except asyncio.CancelledError:
        logger.info("Performance monitoring stopped")

    # TODO: Close connections and cleanup resources


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title=settings.app_name,
        description="FastAPI micro-service for OCR processing of transportation documents with Supabase integration",
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else ["https://*.railway.app"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # Add trusted host middleware for production
    if not settings.debug:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*.railway.app", "localhost", "testserver"],
        )

    # Add timing middleware
    app.add_middleware(TimingMiddleware)

    # Exception handlers
    @app.exception_handler(OCRLoadException)
    async def ocr_load_exception_handler(
        request: Request, exc: OCRLoadException
    ) -> JSONResponse:
        """Handle custom OCRLoadException instances."""
        request_id = getattr(request.state, "request_id", None)

        logger.error(
            f"OCRLoadException: {exc.error_code} - {exc.message} "
            f"- {request.url} - Request ID: {request_id}",
            extra={"error_code": exc.error_code, "details": exc.details},
        )

        http_exc = to_http_exception(exc, request_id)
        return JSONResponse(status_code=http_exc.status_code, content=http_exc.detail)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """Handle HTTP exceptions with proper logging and standardized response."""
        request_id = getattr(request.state, "request_id", None)

        logger.warning(
            f"HTTP {exc.status_code}: {exc.detail} - {request.url} - Request ID: {request_id}"
        )

        # Check if detail is already in our standard format
        if isinstance(exc.detail, dict) and "error_code" in exc.detail:
            # Already formatted
            response_content = exc.detail
            if request_id and "request_id" not in response_content:
                response_content["request_id"] = request_id
        else:
            # Format as standard error response
            response_content = ErrorResponse(
                error=str(exc.detail),
                error_code="HTTP_ERROR",
                request_id=request_id,
                status_code=exc.status_code,
            ).model_dump(mode="json")

        return JSONResponse(status_code=exc.status_code, content=response_content)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request validation errors with detailed messages."""
        request_id = getattr(request.state, "request_id", None)

        logger.warning(
            f"Validation error: {exc.errors()} - {request.url} - Request ID: {request_id}"
        )

        # Serialize the error details properly to handle ValueError objects
        serialized_errors = []
        for error in exc.errors():
            serialized_error = error.copy()
            # Convert any exception objects to strings
            if "ctx" in serialized_error and "error" in serialized_error["ctx"]:
                if isinstance(serialized_error["ctx"]["error"], Exception):
                    serialized_error["ctx"]["error"] = str(
                        serialized_error["ctx"]["error"]
                    )
            serialized_errors.append(serialized_error)

        response_content = ErrorResponse(
            error="Validation error",
            error_code="VALIDATION_ERROR",
            details={"validation_errors": serialized_errors},
            request_id=request_id,
            status_code=422,
        ).model_dump(mode="json")

        return JSONResponse(status_code=422, content=response_content)

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unexpected exceptions with proper logging."""
        request_id = getattr(request.state, "request_id", None)

        logger.error(
            f"Unexpected error: {str(exc)} - {request.url} - Request ID: {request_id}",
            exc_info=True,
        )

        response_content = ErrorResponse(
            error="Internal server error",
            error_code="INTERNAL_ERROR",
            details={"exception_type": type(exc).__name__},
            request_id=request_id,
            status_code=500,
        ).model_dump(mode="json")

        return JSONResponse(status_code=500, content=response_content)

    # Include routers
    from app.routers import health, media, monitoring, parse_test

    app.include_router(health.router)
    app.include_router(media.router, prefix="/api")
    app.include_router(parse_test.router, prefix="/api")
    app.include_router(monitoring.router)  # Already has /api/monitoring prefix

    # TODO: Add remaining routers when they're created

    return app


# Create the application instance
app = create_application()


@app.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint with basic service information."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "environment": "development" if settings.debug else "production",
        "docs_url": "/docs" if settings.debug else "disabled",
    }

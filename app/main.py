"""Main FastAPI application for OCR & Docs Micro-Service."""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.settings import settings

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
        
        # Process request
        response = await call_next(request)
        
        # Calculate timing
        process_time = time.time() - start_time
        
        # Add timing headers
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
    
    # TODO: Initialize connections (Supabase, Redis, etc.)
    # TODO: Validate API keys and external service connectivity
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
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
            allowed_hosts=["*.railway.app", "localhost"]
        )

    # Add timing middleware
    app.add_middleware(TimingMiddleware)

    # Exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle HTTP exceptions with proper logging."""
        logger.warning(f"HTTP {exc.status_code}: {exc.detail} - {request.url}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.detail,
                "status_code": exc.status_code
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Handle request validation errors with detailed messages."""
        logger.warning(f"Validation error: {exc.errors()} - {request.url}")
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": "Validation error",
                "details": exc.errors(),
                "status_code": 422
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected exceptions with proper logging."""
        logger.error(f"Unexpected error: {str(exc)} - {request.url}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
                "status_code": 500
            }
        )

    # Include routers
    from app.routers import health
    app.include_router(health.router)
    
    # TODO: Add remaining routers when they're created
    # from app.routers import media, parse_test
    # app.include_router(media.router, prefix="/api")
    # app.include_router(parse_test.router, prefix="/api")

    return app


# Create the application instance
app = create_application()


@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint with basic service information."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "environment": "development" if settings.debug else "production",
        "docs_url": "/docs" if settings.debug else "disabled"
    }

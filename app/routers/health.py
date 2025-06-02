"""Health check router for liveness and readiness probes."""

import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.models.responses import HealthCheckResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(http_request: Request) -> JSONResponse:
    """
    Health check endpoint for Railway and Kubernetes liveness probes.

    Returns system health status including:
    - Basic service status
    - Database connectivity (when implemented)
    - Storage accessibility (when implemented)
    - System timestamp and info

    Should respond in <100ms for optimal probe performance.
    """
    request_id = getattr(http_request.state, "request_id", None)
    start_time = time.time()

    health_status = HealthCheckResponse(
        ok=True,
        status="healthy",
        service=settings.app_name,
        version=settings.app_version,
        environment="development" if settings.debug else "production",
        checks={},
        response_time_ms=0.0,  # Will be updated below
    )

    # Database and storage connectivity checks
    try:
        # Check if we're using placeholder values (development mode)
        using_placeholders = (
            "placeholder" in settings.supabase_url.lower()
            or "placeholder" in settings.supabase_anon_key.lower()
            or "placeholder" in settings.DATALAB_API_KEY.lower()
        )

        if using_placeholders and settings.debug:
            # Development mode with placeholders - skip actual connectivity tests
            health_status.checks["database"] = {
                "status": "info",
                "message": "Development mode with placeholder credentials - skipping connectivity test",
            }
            health_status.checks["storage"] = {
                "status": "info",
                "message": "Development mode with placeholder credentials - skipping connectivity test",
            }
            health_status.checks["redis"] = {
                "status": "info",
                "message": "Development mode - Redis connectivity not tested",
            }
            health_status.status = (
                "healthy"  # Allow health check to pass in development
            )
        else:
            # Production mode or real credentials - perform actual checks
            from app.services.supabase_client import supabase_service

            supabase_health = await supabase_service.health_check()

            # Add database check results
            db_status = supabase_health["database"]["status"]
            if db_status == "healthy":
                health_status.checks["database"] = {
                    "status": "ok",
                    "message": supabase_health["database"]["message"],
                }
            elif db_status == "limited":
                health_status.checks["database"] = {
                    "status": "warning",
                    "message": supabase_health["database"]["message"],
                }
                health_status.status = "degraded"
            else:
                health_status.ok = False
                health_status.status = "unhealthy"
                health_status.checks["database"] = {
                    "status": "error",
                    "message": supabase_health["database"]["message"],
                }

            # Add storage check results
            storage_status = supabase_health["storage"]["status"]
            if storage_status == "healthy":
                health_status.checks["storage"] = {
                    "status": "ok",
                    "message": supabase_health["storage"]["message"],
                    "bucket": supabase_health["storage"].get("bucket_name"),
                }
            elif storage_status == "warning":
                health_status.checks["storage"] = {
                    "status": "warning",
                    "message": supabase_health["storage"]["message"],
                }
                if health_status.status == "healthy":
                    health_status.status = "degraded"
            else:
                health_status.ok = False
                health_status.status = "unhealthy"
                health_status.checks["storage"] = {
                    "status": "error",
                    "message": supabase_health["storage"]["message"],
                }

            # Add Redis check results
            from app.services.redis_event_service import redis_event_service

            redis_health = await redis_event_service.health_check()

            redis_status = redis_health["status"]
            if redis_status == "healthy":
                health_status.checks["redis"] = {
                    "status": "ok",
                    "message": redis_health["message"],
                    "configured": redis_health["configured"],
                }
            elif redis_status == "disabled":
                health_status.checks["redis"] = {
                    "status": "info",
                    "message": redis_health["message"],
                    "configured": redis_health["configured"],
                }
                # Redis being disabled is not a health issue
            else:
                # Redis failure is not critical - service can continue without events
                health_status.checks["redis"] = {
                    "status": "warning",
                    "message": redis_health["message"],
                    "configured": redis_health["configured"],
                }
                if health_status.status == "healthy":
                    health_status.status = "degraded"

    except Exception as e:
        # Check if this is a development environment with placeholders
        using_placeholders = (
            "placeholder" in settings.supabase_url.lower()
            or "placeholder" in settings.supabase_anon_key.lower()
            or "placeholder" in settings.DATALAB_API_KEY.lower()
        )

        if using_placeholders and settings.debug:
            # Development mode - don't fail health check for placeholder credential errors
            health_status.checks["database"] = {
                "status": "info",
                "message": "Development mode - database connectivity not tested",
            }
            health_status.checks["storage"] = {
                "status": "info",
                "message": "Development mode - storage connectivity not tested",
            }
            health_status.checks["redis"] = {
                "status": "info",
                "message": "Development mode - Redis connectivity not tested",
            }
        else:
            # Production mode - fail health check on errors
            health_status.ok = False
            health_status.status = "unhealthy"
            health_status.checks["database"] = {
                "status": "error",
                "message": f"Health check failed: {str(e)}",
            }
            health_status.checks["storage"] = {
                "status": "error",
                "message": f"Health check failed: {str(e)}",
            }
            health_status.checks["redis"] = {
                "status": "error",
                "message": f"Health check failed: {str(e)}",
            }

    # Basic environment checks
    health_status.checks["environment"] = {
        "status": "ok",
        "mode": "development" if settings.debug else "production",
        "using_placeholders": "placeholder" in settings.supabase_url.lower(),
        "supabase_url_configured": bool(settings.supabase_url),
        "supabase_service_key_configured": bool(settings.supabase_service_key),
        "datalab_api_key_configured": bool(settings.DATALAB_API_KEY),
    }

    # Calculate response time
    response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
    health_status.response_time_ms = round(response_time, 2)

    # Return appropriate status code
    status_code = 200 if health_status.ok else 503

    # Convert to dict for JSON response with proper serialization
    response_data = health_status.model_dump(mode="json")
    if request_id:
        response_data["request_id"] = request_id

    return JSONResponse(status_code=status_code, content=response_data)


@router.get("/health/ready", response_model=dict[str, Any])
async def readiness_check(http_request: Request) -> JSONResponse:
    """
    Readiness check endpoint for determining if service is ready to accept traffic.

    This performs more thorough checks than the basic health endpoint,
    including external service connectivity.
    """
    request_id = getattr(http_request.state, "request_id", None)
    start_time = time.time()

    readiness_status = {
        "ready": True,
        "timestamp": datetime.now(UTC).isoformat(),
        "service": settings.app_name,
        "version": settings.app_version,
        "checks": {},
    }

    # TODO: Add comprehensive readiness checks
    # - Database connection and query capability
    # - Storage bucket read/write access
    # - External API reachability (Datalab, Marker)
    # - Redis connectivity (if configured)

    # Basic configuration checks
    config_ready = all(
        [
            settings.supabase_url,
            settings.supabase_service_key,
            settings.DATALAB_API_KEY,
        ]
    )

    readiness_status["checks"]["configuration"] = {
        "status": "ok" if config_ready else "error",
        "message": "All required environment variables configured"
        if config_ready
        else "Missing required configuration",
    }

    if not config_ready:
        readiness_status["ready"] = False

    # Calculate response time
    response_time = (time.time() - start_time) * 1000
    readiness_status["response_time_ms"] = round(response_time, 2)

    # Add request ID if available
    if request_id:
        readiness_status["request_id"] = request_id

    # Return appropriate status code
    status_code = 200 if readiness_status["ready"] else 503

    return JSONResponse(status_code=status_code, content=readiness_status)

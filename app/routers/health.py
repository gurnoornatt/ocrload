"""Health check router for liveness and readiness probes."""

import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.config.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Dict[str, Any])
async def health_check() -> JSONResponse:
    """
    Health check endpoint for Railway and Kubernetes liveness probes.
    
    Returns system health status including:
    - Basic service status
    - Database connectivity (when implemented)
    - Storage accessibility (when implemented)
    - System timestamp and info
    
    Should respond in <100ms for optimal probe performance.
    """
    start_time = time.time()
    
    health_status = {
        "ok": True,
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": "development" if settings.debug else "production",
        "checks": {}
    }
    
    # Database and storage connectivity checks
    try:
        from app.services.supabase_client import supabase_service
        supabase_health = await supabase_service.health_check()
        
        # Add database check results
        db_status = supabase_health["database"]["status"]
        if db_status == "healthy":
            health_status["checks"]["database"] = {
                "status": "ok", 
                "message": supabase_health["database"]["message"]
            }
        elif db_status == "limited":
            health_status["checks"]["database"] = {
                "status": "warning", 
                "message": supabase_health["database"]["message"]
            }
            health_status["status"] = "degraded"
        else:
            health_status["ok"] = False
            health_status["status"] = "unhealthy"
            health_status["checks"]["database"] = {
                "status": "error", 
                "message": supabase_health["database"]["message"]
            }
        
        # Add storage check results
        storage_status = supabase_health["storage"]["status"]
        if storage_status == "healthy":
            health_status["checks"]["storage"] = {
                "status": "ok", 
                "message": supabase_health["storage"]["message"],
                "bucket": supabase_health["storage"].get("bucket_name")
            }
        elif storage_status == "warning":
            health_status["checks"]["storage"] = {
                "status": "warning", 
                "message": supabase_health["storage"]["message"]
            }
            if health_status["status"] == "healthy":
                health_status["status"] = "degraded"
        else:
            health_status["ok"] = False
            health_status["status"] = "unhealthy"
            health_status["checks"]["storage"] = {
                "status": "error", 
                "message": supabase_health["storage"]["message"]
            }
            
    except Exception as e:
        health_status["ok"] = False
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {"status": "error", "message": f"Health check failed: {str(e)}"}
        health_status["checks"]["storage"] = {"status": "error", "message": f"Health check failed: {str(e)}"}
    
    # Basic environment checks
    health_status["checks"]["environment"] = {
        "status": "ok",
        "supabase_url_configured": bool(settings.supabase_url),
        "supabase_service_key_configured": bool(settings.supabase_service_key),
        "datalab_api_key_configured": bool(settings.datalab_api_key),
    }
    
    # Calculate response time
    response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
    health_status["response_time_ms"] = round(response_time, 2)
    
    # Return appropriate status code
    status_code = 200 if health_status["ok"] else 503
    
    return JSONResponse(
        status_code=status_code,
        content=health_status
    )


@router.get("/health/ready", response_model=Dict[str, Any])
async def readiness_check() -> JSONResponse:
    """
    Readiness check endpoint for determining if service is ready to accept traffic.
    
    This performs more thorough checks than the basic health endpoint,
    including external service connectivity.
    """
    start_time = time.time()
    
    readiness_status = {
        "ready": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": settings.app_name,
        "version": settings.app_version,
        "checks": {}
    }
    
    # TODO: Add comprehensive readiness checks
    # - Database connection and query capability
    # - Storage bucket read/write access
    # - External API reachability (Datalab, Marker)
    # - Redis connectivity (if configured)
    
    # Basic configuration checks
    config_ready = all([
        settings.supabase_url,
        settings.supabase_service_key,
        settings.datalab_api_key,
    ])
    
    readiness_status["checks"]["configuration"] = {
        "status": "ok" if config_ready else "error",
        "message": "All required environment variables configured" if config_ready else "Missing required configuration"
    }
    
    if not config_ready:
        readiness_status["ready"] = False
    
    # Calculate response time
    response_time = (time.time() - start_time) * 1000
    readiness_status["response_time_ms"] = round(response_time, 2)
    
    # Return appropriate status code
    status_code = 200 if readiness_status["ready"] else 503
    
    return JSONResponse(
        status_code=status_code,
        content=readiness_status
    ) 
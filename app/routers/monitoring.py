"""
Performance monitoring and metrics endpoints.

Provides endpoints for:
- Real-time KPI reporting
- Performance metrics
- Health checks with detailed status
- Prometheus-style metrics export
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.performance_monitor import performance_monitor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


class HealthStatus(BaseModel):
    """Health check response model."""

    status: str = Field(..., description="Overall service status")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    kpi_compliance: bool = Field(..., description="Whether KPIs are being met")
    last_hour_requests: int = Field(..., description="Number of requests in last hour")
    median_response_time: float = Field(..., description="Median response time")
    success_rate: float = Field(..., description="Success rate percentage")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional status details"
    )


class KPIReportResponse(BaseModel):
    """KPI report response model."""

    timeframe_minutes: int
    total_requests: int
    success_rate: float
    median_turnaround: float
    p95_turnaround: float
    p99_turnaround: float
    error_rate_5xx: float
    ocr_success_rate: float
    parsing_success_rate: float
    stage_averages: dict[str, float]
    compliance_status: dict[str, bool]
    summary: str


class MetricsSummaryResponse(BaseModel):
    """Metrics summary response model."""

    total_metrics: int
    uptime_seconds: float
    stage_counts: dict[str, int]
    status_counts: dict[str, int]
    oldest_metric: float | None
    newest_metric: float | None


@router.get("/health", response_model=HealthStatus)
async def get_health_status() -> HealthStatus:
    """
    Get comprehensive health status including KPI compliance.

    Returns detailed health information including:
    - Service uptime
    - KPI compliance status
    - Recent performance metrics
    - Error rates and response times
    """
    try:
        # Get recent KPI report
        kpi_report = performance_monitor.get_kpi_report(60)  # Last hour
        summary = performance_monitor.get_metrics_summary()

        # Determine overall status
        if kpi_report.total_requests == 0:
            status = "starting"  # No requests yet
            kpi_compliance = True  # No failures yet
        elif kpi_report.compliance_status.get("overall_kpi_met", False):
            status = "healthy"
            kpi_compliance = True
        else:
            status = "degraded"
            kpi_compliance = False

        # Build detailed status
        details = {
            "kpi_targets": {
                "median_turnaround_target": "≤ 3.0s",
                "success_rate_target": "≥ 95%",
                "error_rate_target": "≤ 1%",
            },
            "current_performance": {
                "median_turnaround": f"{kpi_report.median_turnaround:.2f}s",
                "success_rate": f"{kpi_report.success_rate:.1f}%",
                "error_rate_5xx": f"{kpi_report.error_rate_5xx:.1f}%",
            },
            "compliance": kpi_report.compliance_status,
        }

        return HealthStatus(
            status=status,
            uptime_seconds=summary["uptime_seconds"],
            kpi_compliance=kpi_compliance,
            last_hour_requests=kpi_report.total_requests,
            median_response_time=kpi_report.median_turnaround,
            success_rate=kpi_report.success_rate,
            details=details,
        )

    except Exception as e:
        logger.error(f"Error getting health status: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")


@router.get("/kpi", response_model=KPIReportResponse)
async def get_kpi_report(
    timeframe_minutes: int = Query(
        60, ge=1, le=1440, description="Timeframe in minutes (1-1440)"
    ),
) -> KPIReportResponse:
    """
    Get KPI compliance report for specified timeframe.

    Returns detailed KPI metrics including:
    - Success rates and turnaround times
    - Error rates and compliance status
    - Stage-by-stage performance breakdown
    """
    try:
        report = performance_monitor.get_kpi_report(timeframe_minutes)

        # Generate summary
        if report.total_requests == 0:
            summary = f"No requests in last {timeframe_minutes} minutes"
        else:
            compliance_text = (
                "KPIs MET"
                if report.compliance_status.get("overall_kpi_met", False)
                else "KPIs NOT MET"
            )
            summary = (
                f"{report.total_requests} requests, {report.success_rate:.1f}% success, "
                f"{report.median_turnaround:.2f}s median - {compliance_text}"
            )

        return KPIReportResponse(
            timeframe_minutes=report.timeframe_minutes,
            total_requests=report.total_requests,
            success_rate=report.success_rate,
            median_turnaround=report.median_turnaround,
            p95_turnaround=report.p95_turnaround,
            p99_turnaround=report.p99_turnaround,
            error_rate_5xx=report.error_rate_5xx,
            ocr_success_rate=report.ocr_success_rate,
            parsing_success_rate=report.parsing_success_rate,
            stage_averages=report.stage_averages,
            compliance_status=report.compliance_status,
            summary=summary,
        )

    except Exception as e:
        logger.error(f"Error getting KPI report: {e}")
        raise HTTPException(status_code=500, detail="KPI report generation failed")


@router.get("/metrics", response_model=MetricsSummaryResponse)
async def get_metrics_summary() -> MetricsSummaryResponse:
    """
    Get summary of collected performance metrics.

    Returns:
    - Total number of metrics collected
    - Service uptime
    - Breakdown by stage and status
    - Metric collection timeframe
    """
    try:
        summary = performance_monitor.get_metrics_summary()

        return MetricsSummaryResponse(
            total_metrics=summary["total_metrics"],
            uptime_seconds=summary["uptime_seconds"],
            stage_counts=summary.get("stage_counts", {}),
            status_counts=summary.get("status_counts", {}),
            oldest_metric=summary.get("oldest_metric"),
            newest_metric=summary.get("newest_metric"),
        )

    except Exception as e:
        logger.error(f"Error getting metrics summary: {e}")
        raise HTTPException(status_code=500, detail="Metrics summary failed")


@router.get("/prometheus")
async def get_prometheus_metrics() -> str:
    """
    Get metrics in Prometheus format for external monitoring.

    Returns metrics in Prometheus exposition format for integration
    with monitoring systems like Grafana, DataDog, etc.
    """
    try:
        kpi_report = performance_monitor.get_kpi_report(60)
        summary = performance_monitor.get_metrics_summary()

        # Build Prometheus metrics
        metrics = []

        # Service info
        metrics.append("# HELP ocrload_uptime_seconds Service uptime in seconds")
        metrics.append("# TYPE ocrload_uptime_seconds gauge")
        metrics.append(f"ocrload_uptime_seconds {summary['uptime_seconds']}")

        # Request metrics
        metrics.append("# HELP ocrload_requests_total Total number of requests")
        metrics.append("# TYPE ocrload_requests_total counter")
        metrics.append(f"ocrload_requests_total {kpi_report.total_requests}")

        # Success rate
        metrics.append("# HELP ocrload_success_rate Success rate percentage")
        metrics.append("# TYPE ocrload_success_rate gauge")
        metrics.append(f"ocrload_success_rate {kpi_report.success_rate}")

        # Response times
        metrics.append("# HELP ocrload_response_time_seconds Response time quantiles")
        metrics.append("# TYPE ocrload_response_time_seconds gauge")
        metrics.append(
            f'ocrload_response_time_seconds{{quantile="0.5"}} {kpi_report.median_turnaround}'
        )
        metrics.append(
            f'ocrload_response_time_seconds{{quantile="0.95"}} {kpi_report.p95_turnaround}'
        )
        metrics.append(
            f'ocrload_response_time_seconds{{quantile="0.99"}} {kpi_report.p99_turnaround}'
        )

        # Error rate
        metrics.append("# HELP ocrload_error_rate_5xx 5xx error rate percentage")
        metrics.append("# TYPE ocrload_error_rate_5xx gauge")
        metrics.append(f"ocrload_error_rate_5xx {kpi_report.error_rate_5xx}")

        # KPI compliance
        metrics.append(
            "# HELP ocrload_kpi_compliance KPI compliance status (1=compliant, 0=non-compliant)"
        )
        metrics.append("# TYPE ocrload_kpi_compliance gauge")
        metrics.append(
            f"ocrload_kpi_compliance {1 if kpi_report.compliance_status.get('overall_kpi_met', False) else 0}"
        )

        # Stage-specific metrics
        for stage, avg_time in kpi_report.stage_averages.items():
            metrics.append(
                f'ocrload_stage_duration_seconds{{stage="{stage}"}} {avg_time}'
            )

        return "\n".join(metrics)

    except Exception as e:
        logger.error(f"Error generating Prometheus metrics: {e}")
        raise HTTPException(
            status_code=500, detail="Prometheus metrics generation failed"
        )


@router.get("/status/simple")
async def get_simple_status() -> dict[str, Any]:
    """
    Simple status endpoint for basic health checks.

    Returns minimal status information suitable for load balancer
    health checks and basic monitoring.
    """
    try:
        kpi_report = performance_monitor.get_kpi_report(5)  # Last 5 minutes

        # Simple status determination
        if kpi_report.total_requests == 0:
            status = "ok"  # No recent activity, but service is running
        elif kpi_report.compliance_status.get("overall_kpi_met", False):
            status = "ok"
        else:
            status = "degraded"

        return {
            "status": status,
            "timestamp": performance_monitor._start_time,
            "requests_5min": kpi_report.total_requests,
        }

    except Exception as e:
        logger.error(f"Error in simple status check: {e}")
        return {"status": "error", "error": str(e)}

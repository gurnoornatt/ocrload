"""
Performance monitoring service for tracking KPIs and metrics.

This service tracks:
- OCR turnaround time (target: 3s median)
- Success rates (target: ≥95% parse success)
- Error tracking (target: <1% 5xx errors)
- Pipeline stage timing
- Resource utilization
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Pipeline stages for performance tracking."""

    DOWNLOAD = "download"
    STORAGE_UPLOAD = "storage_upload"
    OCR_PROCESSING = "ocr_processing"
    DOCUMENT_PARSING = "document_parsing"
    DATABASE_UPDATE = "database_update"
    EVENT_EMISSION = "event_emission"
    TOTAL_PIPELINE = "total_pipeline"


class ProcessingStatus(Enum):
    """Processing result status."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    RETRY = "retry"


@dataclass
class PerformanceMetric:
    """Individual performance metric."""

    stage: PipelineStage
    status: ProcessingStatus
    duration: float
    timestamp: float
    request_id: str
    error_type: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class KPIReport:
    """KPI compliance report."""

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


class PerformanceMonitor:
    """Performance monitoring service with KPI tracking."""

    def __init__(self, max_metrics: int = 10000):
        self.max_metrics = max_metrics
        self.metrics: list[PerformanceMetric] = []
        self.lock = Lock()
        self._start_time = time.time()

    def clear_metrics(self) -> None:
        """Clear all metrics (useful for testing)."""
        with self.lock:
            self.metrics.clear()
            self._start_time = time.time()
        logger.info("Performance metrics cleared")

    def record_metric(
        self,
        stage: PipelineStage,
        status: ProcessingStatus,
        duration: float,
        request_id: str,
        error_type: str | None = None,
        **details,
    ) -> None:
        """Record a performance metric."""
        metric = PerformanceMetric(
            stage=stage,
            status=status,
            duration=duration,
            timestamp=time.time(),
            request_id=request_id,
            error_type=error_type,
            details=details,
        )

        with self.lock:
            self.metrics.append(metric)

            # Keep only recent metrics to prevent memory growth
            if len(self.metrics) > self.max_metrics:
                self.metrics = self.metrics[-self.max_metrics :]

        # Log performance metric
        level = logging.WARNING if status == ProcessingStatus.FAILURE else logging.INFO
        logger.log(
            level,
            f"Performance: {stage.value} {status.value} {duration:.3f}s "
            f"ID: {request_id} {f'Error: {error_type}' if error_type else ''}",
        )

    def get_kpi_report(self, timeframe_minutes: int = 60) -> KPIReport:
        """Generate KPI compliance report for the specified timeframe."""
        cutoff_time = time.time() - (timeframe_minutes * 60)

        with self.lock:
            # Filter metrics to timeframe
            recent_metrics = [m for m in self.metrics if m.timestamp >= cutoff_time]

        if not recent_metrics:
            return KPIReport(
                timeframe_minutes=timeframe_minutes,
                total_requests=0,
                success_rate=0.0,
                median_turnaround=0.0,
                p95_turnaround=0.0,
                p99_turnaround=0.0,
                error_rate_5xx=0.0,
                ocr_success_rate=0.0,
                parsing_success_rate=0.0,
                stage_averages={},
                compliance_status={},
            )

        # Get total pipeline metrics
        pipeline_metrics = [
            m for m in recent_metrics if m.stage == PipelineStage.TOTAL_PIPELINE
        ]

        # Calculate success rate
        total_requests = len(pipeline_metrics)
        successful_requests = len(
            [m for m in pipeline_metrics if m.status == ProcessingStatus.SUCCESS]
        )
        success_rate = (
            (successful_requests / total_requests * 100) if total_requests > 0 else 0.0
        )

        # Calculate turnaround times
        successful_durations = [
            m.duration for m in pipeline_metrics if m.status == ProcessingStatus.SUCCESS
        ]

        if successful_durations:
            successful_durations.sort()
            n = len(successful_durations)
            median_turnaround = successful_durations[n // 2] if n > 0 else 0.0
            p95_index = int(n * 0.95) if n > 0 else 0
            p99_index = int(n * 0.99) if n > 0 else 0
            p95_turnaround = (
                successful_durations[min(p95_index, n - 1)] if n > 0 else 0.0
            )
            p99_turnaround = (
                successful_durations[min(p99_index, n - 1)] if n > 0 else 0.0
            )
        else:
            median_turnaround = p95_turnaround = p99_turnaround = 0.0

        # Calculate error rates
        error_5xx_count = len(
            [
                m
                for m in pipeline_metrics
                if m.status == ProcessingStatus.FAILURE
                and m.details.get("status_code", 0) >= 500
            ]
        )
        error_rate_5xx = (
            (error_5xx_count / total_requests * 100) if total_requests > 0 else 0.0
        )

        # Calculate stage-specific success rates
        ocr_metrics = [
            m for m in recent_metrics if m.stage == PipelineStage.OCR_PROCESSING
        ]
        ocr_success_count = len(
            [m for m in ocr_metrics if m.status == ProcessingStatus.SUCCESS]
        )
        ocr_success_rate = (
            (ocr_success_count / len(ocr_metrics) * 100) if ocr_metrics else 0.0
        )

        parsing_metrics = [
            m for m in recent_metrics if m.stage == PipelineStage.DOCUMENT_PARSING
        ]
        parsing_success_count = len(
            [m for m in parsing_metrics if m.status == ProcessingStatus.SUCCESS]
        )
        parsing_success_rate = (
            (parsing_success_count / len(parsing_metrics) * 100)
            if parsing_metrics
            else 0.0
        )

        # Calculate stage averages
        stage_averages = {}
        for stage in PipelineStage:
            stage_metrics = [
                m.duration
                for m in recent_metrics
                if m.stage == stage and m.status == ProcessingStatus.SUCCESS
            ]
            if stage_metrics:
                stage_averages[stage.value] = sum(stage_metrics) / len(stage_metrics)

        # Check KPI compliance
        compliance_status = {
            "turnaround_3s": median_turnaround <= 3.0,
            "success_rate_95": success_rate >= 95.0,
            "error_rate_1": error_rate_5xx <= 1.0,
            "overall_kpi_met": (
                median_turnaround <= 3.0
                and success_rate >= 95.0
                and error_rate_5xx <= 1.0
            ),
        }

        return KPIReport(
            timeframe_minutes=timeframe_minutes,
            total_requests=total_requests,
            success_rate=success_rate,
            median_turnaround=median_turnaround,
            p95_turnaround=p95_turnaround,
            p99_turnaround=p99_turnaround,
            error_rate_5xx=error_rate_5xx,
            ocr_success_rate=ocr_success_rate,
            parsing_success_rate=parsing_success_rate,
            stage_averages=stage_averages,
            compliance_status=compliance_status,
        )

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get summary of all collected metrics."""
        with self.lock:
            total_metrics = len(self.metrics)
            if total_metrics == 0:
                return {
                    "total_metrics": 0,
                    "uptime_seconds": time.time() - self._start_time,
                }

            stage_counts = {}
            status_counts = {}

            for metric in self.metrics:
                stage_counts[metric.stage.value] = (
                    stage_counts.get(metric.stage.value, 0) + 1
                )
                status_counts[metric.status.value] = (
                    status_counts.get(metric.status.value, 0) + 1
                )

            return {
                "total_metrics": total_metrics,
                "uptime_seconds": time.time() - self._start_time,
                "stage_counts": stage_counts,
                "status_counts": status_counts,
                "oldest_metric": self.metrics[0].timestamp if self.metrics else None,
                "newest_metric": self.metrics[-1].timestamp if self.metrics else None,
            }

    @asynccontextmanager
    async def track_stage(self, stage: PipelineStage, request_id: str, **context):
        """Context manager for tracking a pipeline stage."""
        start_time = time.time()
        error_type = None
        status = ProcessingStatus.SUCCESS

        try:
            yield
        except Exception as e:
            error_type = type(e).__name__
            status = ProcessingStatus.FAILURE
            raise
        finally:
            duration = time.time() - start_time
            self.record_metric(
                stage=stage,
                status=status,
                duration=duration,
                request_id=request_id,
                error_type=error_type,
                **context,
            )


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


async def log_performance_summary():
    """Log performance summary periodically."""
    while True:
        try:
            await asyncio.sleep(300)  # Every 5 minutes

            # Get KPI report for last hour
            report = performance_monitor.get_kpi_report(60)

            if report.total_requests > 0:
                logger.info(
                    f"Performance Summary (1h): "
                    f"Requests: {report.total_requests} "
                    f"Success: {report.success_rate:.1f}% "
                    f"Median: {report.median_turnaround:.2f}s "
                    f"P95: {report.p95_turnaround:.2f}s "
                    f"Errors: {report.error_rate_5xx:.1f}% "
                    f"KPI Met: {report.compliance_status['overall_kpi_met']}"
                )

                # Warn if KPIs not met
                if not report.compliance_status["overall_kpi_met"]:
                    issues = []
                    if not report.compliance_status["turnaround_3s"]:
                        issues.append(
                            f"Turnaround {report.median_turnaround:.2f}s > 3s"
                        )
                    if not report.compliance_status["success_rate_95"]:
                        issues.append(f"Success {report.success_rate:.1f}% < 95%")
                    if not report.compliance_status["error_rate_1"]:
                        issues.append(f"Errors {report.error_rate_5xx:.1f}% > 1%")

                    logger.warning(f"KPI Issues: {'; '.join(issues)}")

        except Exception as e:
            logger.error(f"Error in performance summary logging: {e}")

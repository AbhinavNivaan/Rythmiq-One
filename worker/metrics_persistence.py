"""
Metrics persistence for Rythmiq One worker.

Persists job processing metrics to Supabase for:
- Capacity planning and CPU budget monitoring
- Performance regression detection
- Processing path optimization
- Postmortem analysis

Usage:
    from metrics_persistence import persist_metrics
    
    # After job completion:
    metrics = collector.finalize()
    persist_metrics(metrics)
"""

from __future__ import annotations

import os
from typing import Optional

from shared.logging import get_worker_logger
from metrics import ProcessingMetrics

logger = get_worker_logger(__name__)


def _get_stage_cpu(stages: dict, stage_name: str) -> float:
    """Safely extract CPU seconds from stage dict."""
    stage = stages.get(stage_name, {})
    if isinstance(stage, dict):
        return stage.get("cpu_seconds", 0.0)
    return 0.0


def persist_metrics(metrics: ProcessingMetrics, correlation_id: Optional[str] = None) -> bool:
    """
    Write job metrics to Supabase cpu_metrics table.
    
    Called after successful job completion.
    Failures are logged but don't fail the job.
    
    Args:
        metrics: ProcessingMetrics from MetricsCollector.finalize()
        correlation_id: Optional correlation ID for logging
    
    Returns:
        True if persistence succeeded, False otherwise
    """
    # Check if persistence is enabled
    if os.environ.get("ENABLE_METRICS_PERSISTENCE", "true").lower() == "false":
        logger.debug(
            "Metrics persistence disabled",
            extra={"job_id": metrics.job_id, "correlation_id": correlation_id}
        )
        return False
    
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.debug(
            "Supabase credentials not configured, skipping metrics persistence",
            extra={"job_id": metrics.job_id, "correlation_id": correlation_id}
        )
        return False
    
    try:
        # Import here to avoid dependency issues in dev
        from supabase import create_client
        
        client = create_client(supabase_url, supabase_key)
        
        # Convert metrics to dict for extraction
        metrics_dict = metrics.to_dict()
        stages = metrics_dict.get("stages", {})
        chars = metrics_dict.get("characteristics", {})
        
        # Build insert payload
        row = {
            "job_id": metrics.job_id,
            "execution_temperature": metrics.execution_temperature,
            "processing_path": metrics.processing_path,
            "total_cpu_seconds": metrics.total_cpu_seconds,
            "total_wall_seconds": metrics.total_wall_seconds,
            "fetch_cpu_seconds": _get_stage_cpu(stages, "fetch"),
            "quality_cpu_seconds": _get_stage_cpu(stages, "quality_scoring"),
            "pre_ocr_cpu_seconds": _get_stage_cpu(stages, "pre_ocr"),
            "enhancement_cpu_seconds": _get_stage_cpu(stages, "enhancement"),
            "ocr_cpu_seconds": _get_stage_cpu(stages, "ocr"),
            "schema_cpu_seconds": _get_stage_cpu(stages, "schema_adaptation"),
            "upload_cpu_seconds": _get_stage_cpu(stages, "upload"),
            "input_file_size_bytes": chars.get("input_file_size_bytes"),
            "output_file_size_bytes": chars.get("output_file_size_bytes"),
            "quality_score": chars.get("quality_score"),
            "ocr_confidence": chars.get("ocr_confidence"),
            "enhancement_skipped": chars.get("enhancement_skipped", False),
            "page_count": chars.get("page_count", 1),
        }
        
        client.table("cpu_metrics").insert(row).execute()
        
        logger.info(
            "Metrics persisted to cpu_metrics",
            extra={
                "job_id": metrics.job_id,
                "correlation_id": correlation_id,
                "cpu_seconds": metrics.total_cpu_seconds,
                "extra": {
                    "processing_path": metrics.processing_path,
                    "execution_temperature": metrics.execution_temperature,
                }
            }
        )
        
        return True
        
    except ImportError:
        logger.warning(
            "supabase package not installed, cannot persist metrics",
            extra={"job_id": metrics.job_id, "correlation_id": correlation_id}
        )
        return False
        
    except Exception as e:
        # Log but don't fail job - metrics are best-effort
        logger.warning(
            f"Failed to persist metrics: {type(e).__name__}",
            extra={
                "job_id": metrics.job_id,
                "correlation_id": correlation_id,
                "extra": {"error": str(e)}
            }
        )
        return False


def persist_error_event(
    job_id: str,
    error_code: str,
    error_stage: str,
    processing_path: Optional[str] = None,
    quality_score: Optional[float] = None,
    correlation_id: Optional[str] = None,
) -> bool:
    """
    Record an error event to Supabase error_events table.
    
    Used for error pattern analysis and alerting.
    
    Args:
        job_id: Job UUID
        error_code: Error code from ErrorCode enum
        error_stage: Processing stage where error occurred
        processing_path: Optional processing path (fast/standard)
        quality_score: Optional quality score at time of error
        correlation_id: Optional correlation ID for logging
    
    Returns:
        True if persistence succeeded, False otherwise
    """
    if os.environ.get("ENABLE_METRICS_PERSISTENCE", "true").lower() == "false":
        return False
    
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        return False
    
    try:
        from supabase import create_client
        
        client = create_client(supabase_url, supabase_key)
        
        row = {
            "job_id": job_id,
            "error_code": error_code,
            "error_stage": error_stage,
            "processing_path": processing_path,
            "quality_score": quality_score,
        }
        
        client.table("error_events").insert(row).execute()
        
        logger.info(
            "Error event persisted",
            extra={
                "job_id": job_id,
                "correlation_id": correlation_id,
                "error_code": error_code,
                "error_stage": error_stage,
            }
        )
        
        return True
        
    except Exception as e:
        logger.warning(
            f"Failed to persist error event: {type(e).__name__}",
            extra={
                "job_id": job_id,
                "correlation_id": correlation_id,
                "extra": {"error": str(e)}
            }
        )
        return False

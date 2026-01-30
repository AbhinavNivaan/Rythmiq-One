"""
Instrumented worker for CPU metrics collection.

This module wraps the standard worker processing pipeline with
comprehensive CPU and timing instrumentation for capacity planning.

The instrumented version:
1. Measures CPU time per stage using resource.getrusage()
2. Tracks cold vs warm execution
3. Classifies processing path (fast vs standard)
4. Outputs extended metrics in STDOUT JSON

Usage:
    # Run instrumented worker instead of standard worker
    echo '{"job_id": "...", ...}' | python worker_instrumented.py
    
    # Or import and use process_job_instrumented directly
    from worker_instrumented import process_job_instrumented
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Dict, List, Optional

# Ensure parent directory is in path for imports
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import (
    JobPayload,
    Artifacts,
    Metrics,
    SuccessResult,
    FailureResult,
    ErrorDetail,
)
from errors import (
    WorkerError,
    ErrorCode,
    ProcessingStage,
    payload_missing,
    payload_invalid,
    artifact_source_invalid,
    internal_error,
)
from storage.spaces_client import (
    validate_artifact_source,
    ArtifactSourceError,
    create_client_from_spec,
)
from processors.quality import assess_quality, check_quality_warning, QUALITY_WARNING_THRESHOLD
from processors.ocr import extract_text_safe
from processors.enhancement import enhance_image, EnhancementOptions
from processors.schema import adapt_to_schema
from metrics import MetricsCollector, ProcessingMetrics


logger = logging.getLogger(__name__)

# GUARD-002: OCR rollback threshold
OCR_ROLLBACK_THRESHOLD = 0.10

# Quality threshold for fast path classification
FAST_PATH_QUALITY_THRESHOLD = 0.75


def read_stdin() -> str:
    """Read raw input from STDIN."""
    return sys.stdin.read()


def parse_payload(raw: str) -> Dict[str, Any]:
    """Parse raw STDIN input as JSON."""
    raw = raw.strip() if raw else ""
    
    if not raw:
        raise payload_missing()
    
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise payload_invalid(f"Invalid JSON: {str(e)}")
    
    if not isinstance(payload, dict):
        raise payload_invalid("Payload must be a JSON object")
    
    return payload


def validate_payload(data: Dict[str, Any]) -> JobPayload:
    """Validate and parse job payload."""
    try:
        return JobPayload.from_dict(data)
    except ArtifactSourceError as e:
        raise artifact_source_invalid(str(e))
    except ValueError as e:
        raise payload_invalid(str(e))


def process_job_instrumented(payload: JobPayload) -> tuple[SuccessResult, ProcessingMetrics]:
    """
    Execute the processing pipeline with full CPU instrumentation.
    
    Pipeline: FETCH → DECODE → QUALITY → ENHANCE → OCR → SCHEMA → UPLOAD
    
    Each stage is individually timed for CPU consumption.
    
    Args:
        payload: Validated job payload
        
    Returns:
        Tuple of (SuccessResult, ProcessingMetrics)
        
    Raises:
        WorkerError: On any processing failure
    """
    # Initialize metrics collector
    collector = MetricsCollector(payload.job_id)
    
    warnings: List[str] = []
    
    # Create storage client (not timed - configuration only)
    storage = create_client_from_spec(
        endpoint=payload.storage.endpoint,
        region=payload.storage.region,
        bucket=payload.storage.bucket,
    )
    
    # =========================================================================
    # Stage 1: FETCH - Download artifact
    # =========================================================================
    with collector.stage(MetricsCollector.STAGE_FETCH):
        raw_data = storage.download(
            source=payload.input.artifact_source,
            artifact_url=payload.input.artifact_url,
            raw_path=payload.input.raw_path,
        )
    
    # Record input size
    collector.set_characteristics(input_file_size_bytes=len(raw_data))
    
    # =========================================================================
    # Stage 2: QUALITY - Assess input quality
    # =========================================================================
    with collector.stage(MetricsCollector.STAGE_QUALITY):
        quality_result = assess_quality(raw_data)
    
    collector.set_characteristics(quality_score=quality_result.score)
    
    if check_quality_warning(quality_result.score):
        warnings.append(
            f"Low quality score: {quality_result.score:.2f} (threshold: {QUALITY_WARNING_THRESHOLD})"
        )
    
    # =========================================================================
    # Stage 3: PRE-OCR - Baseline OCR for rollback comparison (GUARD-002)
    # =========================================================================
    with collector.stage(MetricsCollector.STAGE_PRE_OCR):
        pre_ocr_result, pre_ocr_warning = extract_text_safe(raw_data)
    
    pre_ocr_confidence = pre_ocr_result.confidence if pre_ocr_result else 0.0
    is_readable = pre_ocr_confidence > 0.5
    
    # =========================================================================
    # Determine processing path (for metrics classification)
    # =========================================================================
    # Fast path: High quality + readable (GUARD-001 will skip enhancement)
    if quality_result.score >= FAST_PATH_QUALITY_THRESHOLD and is_readable:
        collector.set_processing_path("fast")
    else:
        collector.set_processing_path("standard")
    
    # =========================================================================
    # Stage 4: ENHANCE - Apply enhancements with GUARD-001
    # =========================================================================
    with collector.stage(MetricsCollector.STAGE_ENHANCEMENT):
        enhancement_options = EnhancementOptions(
            quality_score=quality_result.score,
            is_readable=is_readable,
        )
        enhanced = enhance_image(raw_data, enhancement_options)
    
    # Track if enhancement was skipped (GUARD-001)
    enhancement_skipped = enhanced.skipped if hasattr(enhanced, 'skipped') else False
    collector.set_characteristics(enhancement_skipped=enhancement_skipped)
    
    # =========================================================================
    # Stage 5: OCR - Extract text from enhanced image
    # =========================================================================
    with collector.stage(MetricsCollector.STAGE_OCR):
        ocr_result, ocr_warning = extract_text_safe(enhanced.image_data)
    
    post_ocr_confidence = ocr_result.confidence if ocr_result else 0.0
    
    # GUARD-002: OCR rollback check
    use_original = False
    if pre_ocr_confidence > 0 and post_ocr_confidence < pre_ocr_confidence - OCR_ROLLBACK_THRESHOLD:
        logger.warning(
            f"[ENHANCEMENT] rollback triggered (OCR regression): "
            f"{pre_ocr_confidence:.3f} -> {post_ocr_confidence:.3f}"
        )
        warnings.append(
            f"Enhancement rollback: OCR confidence dropped from {pre_ocr_confidence:.2f} to {post_ocr_confidence:.2f}"
        )
        use_original = True
        ocr_result = pre_ocr_result
        ocr_warning = pre_ocr_warning
    
    final_image_data = raw_data if use_original else enhanced.image_data
    final_ocr_confidence = pre_ocr_confidence if use_original else post_ocr_confidence
    
    collector.set_characteristics(ocr_confidence=final_ocr_confidence)
    
    if ocr_warning:
        warnings.append(ocr_warning)
    
    # =========================================================================
    # Stage 6: SCHEMA - Adapt to target format
    # =========================================================================
    with collector.stage(MetricsCollector.STAGE_SCHEMA):
        schema_result = adapt_to_schema(
            data=final_image_data,
            schema=payload.portal_schema.schema_definition,
            job_id=payload.job_id,
            user_id=payload.user_id,
            original_filename=payload.input.original_filename,
        )
    
    collector.set_characteristics(output_file_size_bytes=len(schema_result.image_data))
    
    # =========================================================================
    # Stage 7: UPLOAD - Upload results
    # =========================================================================
    with collector.stage(MetricsCollector.STAGE_UPLOAD):
        master_path = storage.upload_master(
            data=schema_result.image_data,
            user_id=payload.user_id,
            job_id=payload.job_id,
        )
        
        preview_path = storage.upload_preview(
            data=schema_result.image_data,
            user_id=payload.user_id,
            job_id=payload.job_id,
        )
    
    # =========================================================================
    # Finalize metrics
    # =========================================================================
    processing_metrics = collector.finalize()
    
    # Build result
    result = SuccessResult(
        job_id=payload.job_id,
        quality_score=quality_result.score,
        warnings=warnings,
        artifacts=Artifacts(
            master_path=master_path,
            preview_path=preview_path,
        ),
        metrics=Metrics(
            ocr_confidence=final_ocr_confidence,
            processing_ms=int(processing_metrics.total_wall_seconds * 1000),
        ),
    )
    
    return result, processing_metrics


def build_failure_result(
    job_id: Optional[str],
    error: WorkerError,
) -> FailureResult:
    """Build a failure result from a WorkerError."""
    return FailureResult(
        job_id=job_id,
        error=ErrorDetail(
            code=error.code.value,
            stage=error.stage.value,
            message=error.message,
            retryable=error.retryable,
        ),
    )


def write_output(result: Dict[str, Any]) -> None:
    """Write JSON result to STDOUT."""
    output = json.dumps(result, separators=(",", ":"), ensure_ascii=False)
    print(output)


def main() -> int:
    """
    Main entry point for instrumented worker.
    
    Same contract as standard worker, but with extended metrics output.
    """
    job_id: Optional[str] = None
    
    try:
        # Read and parse payload
        raw = read_stdin()
        data = parse_payload(raw)
        
        # Extract job_id early for error reporting
        job_id = data.get("job_id")
        
        # Validate payload
        payload = validate_payload(data)
        job_id = payload.job_id
        
        # Process job with instrumentation
        result, metrics = process_job_instrumented(payload)
        
        # Build output with extended metrics
        output = result.to_dict()
        output["cpu_metrics"] = metrics.to_dict()
        
        # Log metrics summary for observability
        logger.info(
            f"Job {job_id} completed: "
            f"cpu={metrics.total_cpu_seconds:.3f}s, "
            f"wall={metrics.total_wall_seconds:.3f}s, "
            f"path={metrics.processing_path}, "
            f"temp={metrics.execution_temperature}"
        )
        
        write_output(output)
        
    except WorkerError as e:
        failure = build_failure_result(job_id, e)
        write_output(failure.to_dict())
        
    except Exception as e:
        error = internal_error(f"{type(e).__name__}: {str(e)}")
        failure = build_failure_result(job_id, error)
        write_output(failure.to_dict())
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

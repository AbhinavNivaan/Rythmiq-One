#!/usr/bin/env python3
"""
Camber CPU Worker - Single-shot document processing.

Execution contract (HARD REQUIREMENTS):
- Read exactly one JSON payload from STDIN
- Produce exactly one JSON payload to STDOUT
- Exit with code 0 on success OR handled failure
- NEVER crash the process
- NEVER throw unhandled exceptions
- No global state, no threads, no retries, no daemons

Usage:
    echo '{"job_id": "...", ...}' | python worker.py
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


logger = logging.getLogger(__name__)

# GUARD-002: OCR rollback threshold
OCR_ROLLBACK_THRESHOLD = 0.10  # Rollback if confidence drops by more than 10%


def read_stdin() -> str:
    """
    Read raw input from STDIN.
    
    Returns:
        Raw string from STDIN
    """
    return sys.stdin.read()


def parse_payload(raw: str) -> Dict[str, Any]:
    """
    Parse raw STDIN input as JSON.
    
    Args:
        raw: Raw string from STDIN
        
    Returns:
        Parsed JSON as dict
        
    Raises:
        WorkerError: If input is empty or invalid JSON
    """
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
    """
    Validate and parse job payload.
    
    Args:
        data: Raw JSON dict
        
    Returns:
        Validated JobPayload
        
    Raises:
        WorkerError: If validation fails
    """
    try:
        return JobPayload.from_dict(data)
    except ArtifactSourceError as e:
        raise artifact_source_invalid(str(e))
    except ValueError as e:
        raise payload_invalid(str(e))


def process_job(payload: JobPayload) -> SuccessResult:
    """
    Execute the full processing pipeline.
    
    Pipeline: FETCH → DECODE → QUALITY → ENHANCE → OCR → SCHEMA → UPLOAD
    
    Includes guardrails:
    - GUARD-001: Skip enhancement for readable images
    - GUARD-002: OCR confidence rollback
    
    Args:
        payload: Validated job payload
        
    Returns:
        SuccessResult on success
        
    Raises:
        WorkerError: On any processing failure
    """
    start_time = time.time()
    warnings: List[str] = []
    
    # Create storage client
    storage = create_client_from_spec(
        endpoint=payload.storage.endpoint,
        region=payload.storage.region,
        bucket=payload.storage.bucket,
    )
    
    # Stage 1: FETCH - Download artifact
    raw_data = storage.download(
        source=payload.input.artifact_source,
        artifact_url=payload.input.artifact_url,
        raw_path=payload.input.raw_path,
    )
    
    # Stage 2: QUALITY - Assess input quality
    quality_result = assess_quality(raw_data)
    
    if check_quality_warning(quality_result.score):
        warnings.append(
            f"Low quality score: {quality_result.score:.2f} (threshold: {QUALITY_WARNING_THRESHOLD})"
        )
    
    # GUARD-002: Pre-enhancement OCR for rollback comparison
    pre_ocr_result, pre_ocr_warning = extract_text_safe(raw_data)
    pre_ocr_confidence = pre_ocr_result.confidence if pre_ocr_result else 0.0
    is_readable = pre_ocr_confidence > 0.5  # Consider readable if OCR confidence > 50%
    
    # Stage 3: ENHANCE - Apply enhancements with GUARD-001
    enhancement_options = EnhancementOptions(
        quality_score=quality_result.score,
        is_readable=is_readable,
    )
    enhanced = enhance_image(raw_data, enhancement_options)
    
    # Stage 4: OCR - Extract text from enhanced image
    ocr_result, ocr_warning = extract_text_safe(enhanced.image_data)
    post_ocr_confidence = ocr_result.confidence if ocr_result else 0.0
    
    # GUARD-002: OCR rollback check
    use_original = False
    if pre_ocr_confidence > 0 and post_ocr_confidence < pre_ocr_confidence - OCR_ROLLBACK_THRESHOLD:
        # OCR confidence dropped by more than threshold - rollback
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
    
    # Use original or enhanced image based on rollback
    final_image_data = raw_data if use_original else enhanced.image_data
    final_ocr_confidence = pre_ocr_confidence if use_original else post_ocr_confidence
    
    if ocr_warning:
        warnings.append(ocr_warning)
    
    # Stage 5: SCHEMA - Adapt to target format
    schema_result = adapt_to_schema(
        data=final_image_data,
        schema=payload.portal_schema.schema_definition,
        job_id=payload.job_id,
        user_id=payload.user_id,
        original_filename=payload.input.original_filename,
    )
    
    # Stage 6: UPLOAD - Upload results
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
    
    # Calculate processing time
    processing_ms = int((time.time() - start_time) * 1000)
    
    return SuccessResult(
        job_id=payload.job_id,
        quality_score=quality_result.score,
        warnings=warnings,
        artifacts=Artifacts(
            master_path=master_path,
            preview_path=preview_path,
        ),
        metrics=Metrics(
            ocr_confidence=final_ocr_confidence,
            processing_ms=processing_ms,
        ),
    )


def build_failure_result(
    job_id: Optional[str],
    error: WorkerError,
) -> FailureResult:
    """
    Build a failure result from a WorkerError.
    
    Args:
        job_id: Job ID (may be None if payload parsing failed)
        error: The WorkerError that occurred
        
    Returns:
        FailureResult ready for JSON serialization
    """
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
    """
    Write JSON result to STDOUT.
    
    Uses compact formatting (no extra whitespace) and ensures
    ASCII-safe output for maximum compatibility.
    
    Args:
        result: Result dict to serialize
    """
    output = json.dumps(result, separators=(",", ":"), ensure_ascii=False)
    print(output)


def main() -> int:
    """
    Main entry point for the worker.
    
    Orchestrates the full execution flow:
    1. Read STDIN
    2. Parse JSON
    3. Validate payload
    4. Process job
    5. Write result to STDOUT
    6. Exit with code 0
    
    CRITICAL: This function NEVER raises exceptions.
    All failures are converted to structured JSON responses.
    
    Returns:
        Exit code (always 0)
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
        job_id = payload.job_id  # Now we have the validated job_id
        
        # Process job
        result = process_job(payload)
        
        # Write success result
        write_output(result.to_dict())
        
    except WorkerError as e:
        # Known error - return structured failure
        failure = build_failure_result(job_id, e)
        write_output(failure.to_dict())
        
    except Exception as e:
        # Unknown error - wrap as internal error
        # This should NEVER happen, but we catch everything
        # to guarantee JSON output
        error = internal_error(f"{type(e).__name__}: {str(e)}")
        failure = build_failure_result(job_id, error)
        write_output(failure.to_dict())
    
    # Always exit with code 0
    # Success/failure is communicated via JSON body
    return 0


if __name__ == "__main__":
    sys.exit(main())

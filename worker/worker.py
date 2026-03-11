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
from processors.document_ai import extract_text_safe as docai_extract_text
from processors.enhancement import enhance_image, EnhancementOptions, READABLE_QUALITY_THRESHOLD
from processors.schema import adapt_to_schema, adapt_master_document
from crypto import encrypt_file as crypto_encrypt, decrypt_file as crypto_decrypt, sek_from_base64, nonce_to_base64, NONCE_SIZE


logger = logging.getLogger(__name__)


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
    
    Pipeline: FETCH → QUALITY → ENHANCE → DOCUMENT AI OCR → SCHEMA → UPLOAD
    
    Includes guardrails:
    - GUARD-001: Skip enhancement for high-quality images
    
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

    # Stage 1b: DECRYPT — adapt-from-master: decrypt encrypted master blob in-memory.
    # Blob format stored in Spaces: nonce (12 bytes) || AES-256-GCM ciphertext.
    # No plaintext ever written to disk or storage during this step.
    if payload.encrypted_input:
        if not payload.sek_b64:
            raise WorkerError(
                code=ErrorCode.PAYLOAD_INVALID,
                stage=ProcessingStage.FETCH,
                message="encrypted_input=true requires sek_b64 to be provided",
            )
        try:
            sek = sek_from_base64(payload.sek_b64)
            if len(raw_data) <= NONCE_SIZE:
                raise ValueError(f"Encrypted blob too short: {len(raw_data)} bytes")
            nonce = raw_data[:NONCE_SIZE]
            ciphertext = raw_data[NONCE_SIZE:]
            raw_data = crypto_decrypt(ciphertext, nonce, sek)
            del sek, nonce, ciphertext
            logger.info("Encrypted master input decrypted in-memory")
        except WorkerError:
            raise
        except Exception as e:
            raise WorkerError(
                code=ErrorCode.DECRYPT_FAILED,
                stage=ProcessingStage.FETCH,
                message=f"Failed to decrypt encrypted input: {str(e)}",
                details={"exception_type": type(e).__name__},
            )
    
    # Stage 2: QUALITY - Assess input quality (type-aware weights/metrics)
    quality_result = assess_quality(raw_data, payload.document_type)

    if check_quality_warning(quality_result.score):
        warnings.append(
            f"Low quality score: {quality_result.score:.2f} (threshold: {QUALITY_WARNING_THRESHOLD})"
        )

    # Determine whether this document type benefits from OCR.
    # Identity cards, photographs, and signatures are skipped.
    _OCR_SKIP_CATEGORIES: frozenset[str] = frozenset({
        "identity", "photograph", "signature", "address",
    })
    _category_lower = (payload.document_category or "").lower()
    is_text_document = (
        payload.document_type == "document"
        and _category_lower not in _OCR_SKIP_CATEGORIES
    )

    # Stage 3: ENHANCE - Route to type-specific pipeline
    # GUARD-001: treat high-quality images as readable so NLM denoising and CLAHE
    # are skipped.  Applying heavy denoising to a sharp 80 %+ image degrades it.
    enhancement_options = EnhancementOptions(
        quality_score=quality_result.score,
        is_readable=quality_result.score >= READABLE_QUALITY_THRESHOLD,
        document_type=payload.document_type,
        document_category=payload.document_category,
        document_subtype=payload.document_subtype,
        quality_breakdown=quality_result.breakdown,
    )
    enhanced = enhance_image(raw_data, enhancement_options)

    # Stage 4: DOCUMENT AI OCR (replaces PaddleOCR — runs on enhanced image)
    # Single call after enhancement.  No rollback needed — Document AI
    # confidence is reliable and not degraded by our enhancement pipeline.
    final_ocr_confidence = 0.0

    if is_text_document:
        ocr_result, ocr_warning = docai_extract_text(enhanced.image_data)
        final_ocr_confidence = ocr_result.confidence if ocr_result else 0.0

        if ocr_warning:
            warnings.append(ocr_warning)

    # Final image is always the enhanced image
    final_image_data = enhanced.image_data

    # Stage 5: OUTPUT TRANSFORM
    # - master mode: optimize best possible output under size cap
    # - adapt mode: enforce portal schema constraints
    if payload.mode == "master":
        schema_result = adapt_master_document(
            data=final_image_data,
            constraints=payload.master_constraints,
            job_id=payload.job_id,
            user_id=payload.user_id,
            original_filename=payload.input.original_filename,
            ocr_result=ocr_result if is_text_document else None,
        )
    else:
        if payload.portal_schema is None:
            raise payload_invalid("portal_schema is required for adapt mode")

        schema_result = adapt_to_schema(
            data=final_image_data,
            schema=payload.portal_schema.schema_definition,
            job_id=payload.job_id,
            user_id=payload.user_id,
            original_filename=payload.input.original_filename,
        )
    
    # Stage 6: ENCRYPT - Encrypt output before storage (if SEK provided)
    upload_data = schema_result.image_data
    is_encrypted = False
    encryption_nonce_b64: str | None = None
    
    if payload.sek_b64:
        try:
            sek = sek_from_base64(payload.sek_b64)
            ciphertext, nonce = crypto_encrypt(upload_data, sek)
            # Prepend nonce to ciphertext so blob is self-contained.
            # Decrypt path: nonce = blob[:NONCE_SIZE], ciphertext = blob[NONCE_SIZE:]
            upload_data = nonce + ciphertext
            encryption_nonce_b64 = nonce_to_base64(nonce)
            is_encrypted = True
            logger.info("Output encrypted with AES-256-GCM (nonce prepended to blob)")
            # Zero sensitive key material
            del sek, nonce, ciphertext
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise WorkerError(
                code=ErrorCode.UPLOAD_FAILED,
                stage=ProcessingStage.UPLOAD,
                message=f"Encryption failed: {str(e)}",
            )
    else:
        logger.warning("No SEK provided — uploading unencrypted (legacy mode)")
    
    # Stage 7: UPLOAD - Upload results
    master_path = storage.upload_master(
        data=upload_data,
        user_id=payload.user_id,
        job_id=payload.job_id,
        content_type=schema_result.content_type,
    )
    
    preview_path = storage.upload_preview(
        data=schema_result.image_data,
        user_id=payload.user_id,
        job_id=payload.job_id,
    )
    
    # ============================================
    # CRITICAL SECURITY FIX: Delete raw upload
    # ============================================
    # After successful encryption and upload, delete the raw plaintext upload
    # to prevent plaintext files from persisting in storage indefinitely
    raw_upload_deleted = False
    if payload.input.raw_path:
        try:
            logger.info(f"Deleting raw upload: {payload.input.raw_path}")
            storage.delete(payload.input.raw_path)
            logger.info(f"Successfully deleted raw upload: {payload.input.raw_path}")
            raw_upload_deleted = True
        except Exception as cleanup_error:
            # Log but don't fail the job if deletion fails
            # The encrypted master was already created successfully
            logger.error(
                "SECURITY WARNING: Failed to delete raw upload",
                extra={
                    "error": str(cleanup_error),
                    "job_id": payload.job_id,
                    "user_id": payload.user_id,
                    "raw_path": payload.input.raw_path,
                }
            )
            # TODO: Trigger alert for manual cleanup
    # ============================================
    
    # Stage 8: POST-QUALITY — assess the final (enhanced or rolled-back) image
    # Done before the del so we still have final_image_data in memory.
    output_quality_result = assess_quality(final_image_data, payload.document_type)

    # Clean up sensitive data from memory
    del upload_data, final_image_data
    
    # Calculate processing time
    processing_ms = int((time.time() - start_time) * 1000)
    
    return SuccessResult(
        job_id=payload.job_id,
        input_quality_score=quality_result.score,
        output_quality_score=output_quality_result.score,
        warnings=warnings,
        artifacts=Artifacts(
            master_path=master_path,
            preview_path=preview_path,
            encrypted=is_encrypted,
            encryption_nonce=encryption_nonce_b64,
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

"""
Error handling for Camber CPU worker.

All errors are mapped to structured error responses with:
- code: Deterministic error code
- stage: Pipeline stage where error occurred
- message: Human-readable description
- retryable: Whether the error is transient

No raw exceptions escape. Every failure produces valid JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(str, Enum):
    """
    Deterministic error codes.
    
    Each code maps to a specific failure mode.
    No ambiguity, no generic fallbacks.
    """
    # INIT stage errors
    PAYLOAD_MISSING = "PAYLOAD_MISSING"
    PAYLOAD_INVALID = "PAYLOAD_INVALID"
    ARTIFACT_SOURCE_INVALID = "ARTIFACT_SOURCE_INVALID"
    
    # FETCH stage errors
    FETCH_FAILED = "FETCH_FAILED"
    FETCH_TIMEOUT = "FETCH_TIMEOUT"
    ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND"
    ARTIFACT_ACCESS_DENIED = "ARTIFACT_ACCESS_DENIED"
    
    # DECODE stage errors
    DECODE_FAILED = "DECODE_FAILED"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    CORRUPT_IMAGE = "CORRUPT_IMAGE"
    
    # OCR stage errors
    OCR_FAILED = "OCR_FAILED"
    OCR_TIMEOUT = "OCR_TIMEOUT"
    OCR_NO_TEXT = "OCR_NO_TEXT"
    
    # QUALITY stage errors
    QUALITY_FAILED = "QUALITY_FAILED"
    
    # ENHANCE stage errors
    ENHANCE_FAILED = "ENHANCE_FAILED"
    
    # SCHEMA stage errors
    SCHEMA_FAILED = "SCHEMA_FAILED"
    RESIZE_FAILED = "RESIZE_FAILED"
    COMPRESSION_FAILED = "COMPRESSION_FAILED"
    SIZE_EXCEEDED = "SIZE_EXCEEDED"
    
    # UPLOAD stage errors
    UPLOAD_FAILED = "UPLOAD_FAILED"
    UPLOAD_TIMEOUT = "UPLOAD_TIMEOUT"
    
    # Catch-all (should never happen)
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ProcessingStage(str, Enum):
    """Pipeline processing stages."""
    INIT = "init"
    FETCH = "fetch"
    DECODE = "decode"
    QUALITY = "quality"
    ENHANCE = "enhance"
    OCR = "ocr"
    SCHEMA = "schema"
    UPLOAD = "upload"


# Retryable error codes (transient failures)
RETRYABLE_CODES = frozenset({
    ErrorCode.FETCH_TIMEOUT,
    ErrorCode.OCR_TIMEOUT,
    ErrorCode.UPLOAD_TIMEOUT,
    ErrorCode.UPLOAD_FAILED,
})


@dataclass(frozen=True)
class WorkerError(Exception):
    """
    Structured worker error.
    
    Immutable (frozen=True) for deterministic behavior.
    Always produces valid JSON output.
    """
    code: ErrorCode
    stage: ProcessingStage
    message: str
    details: Optional[Dict[str, Any]] = field(default=None)
    
    def __str__(self) -> str:
        return f"{self.code.value} at {self.stage.value}: {self.message}"
    
    @property
    def retryable(self) -> bool:
        """Whether this error is potentially transient."""
        return self.code in RETRYABLE_CODES
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        result = {
            "code": self.code.value,
            "stage": self.stage.value,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            result["details"] = self.details
        return result


def wrap_exception(
    exc: Exception,
    code: ErrorCode,
    stage: ProcessingStage,
    message: Optional[str] = None,
) -> WorkerError:
    """
    Wrap a raw exception in a WorkerError.
    
    Use this to convert any exception to a structured error.
    Never let raw exceptions escape.
    """
    return WorkerError(
        code=code,
        stage=stage,
        message=message or str(exc),
        details={"exception_type": type(exc).__name__},
    )


def create_error(
    code: ErrorCode,
    stage: ProcessingStage,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> WorkerError:
    """Create a WorkerError with explicit parameters."""
    return WorkerError(
        code=code,
        stage=stage,
        message=message,
        details=details,
    )


# Convenience constructors for common errors

def payload_missing() -> WorkerError:
    return WorkerError(
        code=ErrorCode.PAYLOAD_MISSING,
        stage=ProcessingStage.INIT,
        message="No payload received from STDIN",
    )


def payload_invalid(reason: str) -> WorkerError:
    return WorkerError(
        code=ErrorCode.PAYLOAD_INVALID,
        stage=ProcessingStage.INIT,
        message=f"Invalid payload: {reason}",
    )


def artifact_source_invalid(reason: str) -> WorkerError:
    return WorkerError(
        code=ErrorCode.ARTIFACT_SOURCE_INVALID,
        stage=ProcessingStage.INIT,
        message=f"Invalid artifact source: {reason}",
    )


def fetch_failed(reason: str) -> WorkerError:
    return WorkerError(
        code=ErrorCode.FETCH_FAILED,
        stage=ProcessingStage.FETCH,
        message=f"Failed to fetch artifact: {reason}",
    )


def decode_failed(reason: str) -> WorkerError:
    return WorkerError(
        code=ErrorCode.DECODE_FAILED,
        stage=ProcessingStage.DECODE,
        message=f"Failed to decode image: {reason}",
    )


def ocr_failed(reason: str) -> WorkerError:
    return WorkerError(
        code=ErrorCode.OCR_FAILED,
        stage=ProcessingStage.OCR,
        message=f"OCR failed: {reason}",
    )


def schema_failed(reason: str) -> WorkerError:
    return WorkerError(
        code=ErrorCode.SCHEMA_FAILED,
        stage=ProcessingStage.SCHEMA,
        message=f"Schema adaptation failed: {reason}",
    )


def upload_failed(reason: str) -> WorkerError:
    return WorkerError(
        code=ErrorCode.UPLOAD_FAILED,
        stage=ProcessingStage.UPLOAD,
        message=f"Upload failed: {reason}",
    )


def internal_error(reason: str) -> WorkerError:
    return WorkerError(
        code=ErrorCode.INTERNAL_ERROR,
        stage=ProcessingStage.INIT,
        message=f"Internal error: {reason}",
    )

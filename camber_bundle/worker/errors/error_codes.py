"""
Deterministic error codes for the Python execution worker.

All errors are terminal (no retries). Each error maps to a specific
processing stage for traceability.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


class ProcessingStage(str, Enum):
    """Processing pipeline stages."""
    INIT = "INIT"
    FETCH = "FETCH"
    OCR = "OCR"
    NORMALIZE = "NORMALIZE"
    TRANSFORM = "TRANSFORM"


class ErrorCode(str, Enum):
    """
    Deterministic error codes.
    
    Every failure in the worker maps to exactly one of these codes.
    No ambiguity, no fallback to generic errors.
    """
    # INIT stage
    PAYLOAD_MISSING = "PAYLOAD_MISSING"
    PAYLOAD_INVALID = "PAYLOAD_INVALID"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # FETCH stage
    ARTIFACT_FETCH_FAILED = "ARTIFACT_FETCH_FAILED"
    
    # OCR stage
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    CORRUPT_DATA = "CORRUPT_DATA"
    SIZE_EXCEEDED = "SIZE_EXCEEDED"
    OCR_FAILURE = "OCR_FAILURE"
    
    # NORMALIZE stage
    NORMALIZE_FAILED = "NORMALIZE_FAILED"
    
    # TRANSFORM stage
    SCHEMA_INVALID = "SCHEMA_INVALID"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    AMBIGUOUS_FIELD = "AMBIGUOUS_FIELD"
    TRANSFORM_ERROR = "TRANSFORM_ERROR"
    VALIDATION_FAILED = "VALIDATION_FAILED"


@dataclass(frozen=True)
class ProcessingError(Exception):
    """
    Immutable error with code, stage, and optional details.
    
    frozen=True ensures deterministic behavior - errors cannot be mutated
    after creation.
    """
    code: ErrorCode
    stage: ProcessingStage
    details: Optional[Dict[str, Any]] = field(default=None)
    
    def __str__(self) -> str:
        return f"{self.code.value} at {self.stage.value}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        result = {
            "code": self.code.value,
            "stage": self.stage.value,
        }
        if self.details:
            result["details"] = self.details
        return result

"""
Unified structured logging for Rythmiq One.

All services MUST use this logger factory to ensure consistent
JSON log format across API, worker, and webhook handlers.

Usage:
    from shared.logging import get_api_logger, get_worker_logger
    
    logger = get_api_logger(__name__)
    logger.info("Job created", extra={
        "job_id": str(job_id),
        "correlation_id": correlation_id,
        "user_id_hash": hash_user_id(user_id),
    })

PII BLOCKLIST - NEVER LOG:
- OCR extracted text
- Original filenames
- User email addresses
- User IP addresses (hash if fraud detection needed)
- Raw user_id (use hash_user_id())
- File contents
- Schema field values from documents
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def hash_user_id(user_id: str) -> str:
    """
    Create anonymized user identifier.
    
    Returns first 16 characters of SHA-256 hash.
    Sufficient for correlation without exposing raw ID.
    """
    if not user_id:
        return "unknown"
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]


def hash_ip(ip_address: str) -> str:
    """
    Hash IP address for fraud detection correlation.
    
    Use sparingly - only when fraud detection requires IP patterns.
    """
    if not ip_address:
        return "unknown"
    return hashlib.sha256(ip_address.encode()).hexdigest()[:16]


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter compliant with Rythmiq log schema.
    
    Produces logs in format:
    {
        "timestamp": "2026-01-30T14:23:45.123Z",
        "level": "INFO",
        "service": "api",
        "message": "Request completed",
        ...optional fields...
    }
    """
    
    # Fields that are allowed in log output
    ALLOWED_EXTRA_FIELDS = frozenset([
        "stage",
        "job_id", 
        "correlation_id",
        "user_id_hash",
        "latency_ms",
        "cpu_seconds",
        "error_code",
        "error_stage",
        "http_method",
        "http_path",
        "http_status",
        "extra",
    ])
    
    # Fields that must NEVER appear (safety check)
    BLOCKED_FIELDS = frozenset([
        "user_id",  # Use user_id_hash instead
        "email",
        "ip_address",
        "filename",
        "original_filename",
        "ocr_text",
        "extracted_text",
        "file_content",
        "password",
        "secret",
        "token",
        "api_key",
    ])
    
    def __init__(self, service: str):
        super().__init__()
        self.service = service
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self.service,
            "message": record.getMessage(),
        }
        
        # Add allowed extra fields
        for field in self.ALLOWED_EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                log_entry[field] = value
        
        # Safety check: warn if blocked fields are present
        for field in self.BLOCKED_FIELDS:
            if hasattr(record, field):
                # Replace with warning, don't expose the value
                log_entry["_pii_warning"] = f"Blocked field '{field}' was stripped"
        
        return json.dumps(log_entry, separators=(",", ":"), ensure_ascii=False, default=str)


class StructuredLogger(logging.Logger):
    """
    Logger subclass with structured logging helpers.
    
    Provides convenience methods for common log patterns.
    """
    
    def log_stage_complete(
        self,
        stage: str,
        job_id: str,
        correlation_id: str,
        cpu_seconds: float,
        latency_ms: float,
        **extra: Any,
    ) -> None:
        """Log stage completion with timing metrics."""
        self.info(
            f"{stage} stage completed",
            extra={
                "stage": stage,
                "job_id": job_id,
                "correlation_id": correlation_id,
                "cpu_seconds": round(cpu_seconds, 6),
                "latency_ms": round(latency_ms, 2),
                "extra": extra if extra else None,
            }
        )
    
    def log_job_complete(
        self,
        job_id: str,
        correlation_id: str,
        user_id_hash: str,
        cpu_seconds: float,
        latency_ms: float,
        success: bool = True,
        **extra: Any,
    ) -> None:
        """Log job completion."""
        level = logging.INFO if success else logging.ERROR
        status = "completed successfully" if success else "failed"
        
        self.log(
            level,
            f"Job {status}",
            extra={
                "job_id": job_id,
                "correlation_id": correlation_id,
                "user_id_hash": user_id_hash,
                "cpu_seconds": round(cpu_seconds, 6),
                "latency_ms": round(latency_ms, 2),
                "extra": extra if extra else None,
            }
        )
    
    def log_error(
        self,
        message: str,
        error_code: str,
        error_stage: str,
        job_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """Log an error with structured error fields."""
        self.error(
            message,
            extra={
                "error_code": error_code,
                "error_stage": error_stage,
                "job_id": job_id,
                "correlation_id": correlation_id,
                "extra": extra if extra else None,
            }
        )


def _create_logger(name: str, service: str, level: int = logging.INFO) -> StructuredLogger:
    """
    Internal factory for creating structured loggers.
    
    Args:
        name: Logger name (usually __name__)
        service: Service identifier (api, worker, webhook)
        level: Logging level
    
    Returns:
        Configured StructuredLogger instance
    """
    # Register our custom logger class
    logging.setLoggerClass(StructuredLogger)
    
    logger = logging.getLogger(name)
    
    # Only configure if no handlers exist
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter(service))
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    
    # Reset to default class for other loggers
    logging.setLoggerClass(logging.Logger)
    
    return logger  # type: ignore


def get_api_logger(name: str) -> StructuredLogger:
    """Create a structured logger for API service."""
    return _create_logger(name, "api")


def get_worker_logger(name: str) -> StructuredLogger:
    """Create a structured logger for worker service."""
    return _create_logger(name, "worker")


def get_webhook_logger(name: str) -> StructuredLogger:
    """Create a structured logger for webhook handler."""
    return _create_logger(name, "webhook")


# Convenience alias
def get_logger(name: str, service: str) -> StructuredLogger:
    """
    Create a structured logger for any service.
    
    Args:
        name: Logger name (usually __name__)
        service: Service identifier (api, worker, webhook)
    
    Returns:
        Configured StructuredLogger instance
    """
    return _create_logger(name, service)


def configure_root_logger(service: str, level: str = "INFO") -> None:
    """
    Configure the root logger with structured formatting.
    
    Call this once at application startup.
    
    Args:
        service: Service identifier
        level: Log level string (DEBUG, INFO, WARN, ERROR)
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter(service))
    
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(numeric_level)
    
    # Suppress noisy libraries
    for lib in ["httpx", "httpcore", "boto3", "botocore", "urllib3", "asyncio"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

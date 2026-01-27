"""
Exception definitions.
Owns: Application-specific exception classes.
"""

from typing import Any


class AppException(Exception):
    error_code: str = "INTERNAL_ERROR"
    status_code: int = 500
    retryable: bool = False

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
            **self.details,
        }


class UnauthorizedException(AppException):
    error_code = "UNAUTHORIZED"
    status_code = 401
    retryable = False


class ForbiddenException(AppException):
    error_code = "FORBIDDEN"
    status_code = 403
    retryable = False


class NotFoundException(AppException):
    error_code = "NOT_FOUND"
    status_code = 404
    retryable = False


class InvalidInputException(AppException):
    error_code = "INVALID_INPUT"
    status_code = 400
    retryable = False


class SchemaNotFoundException(AppException):
    error_code = "SCHEMA_NOT_FOUND"
    status_code = 400
    retryable = False


class QuotaExceededException(AppException):
    error_code = "QUOTA_EXCEEDED"
    status_code = 402
    retryable = False


class JobNotCompleteException(AppException):
    error_code = "JOB_NOT_COMPLETE"
    status_code = 409
    retryable = True


class StorageException(AppException):
    error_code = "STORAGE_ERROR"
    status_code = 500
    retryable = True


class InternalException(AppException):
    error_code = "INTERNAL_ERROR"
    status_code = 500
    retryable = True


class CamberException(AppException):
    """Raised when Camber API calls fail."""
    error_code = "CAMBER_ERROR"
    status_code = 502
    retryable = True


class CamberTimeoutException(CamberException):
    """Raised when Camber API times out."""
    error_code = "CAMBER_TIMEOUT"
    status_code = 504
    retryable = True


class StateTransitionException(AppException):
    """Raised when an invalid state transition is attempted."""
    error_code = "INVALID_STATE_TRANSITION"
    status_code = 409
    retryable = False


class PackagingException(AppException):
    """Raised when output packaging fails."""
    error_code = "PACKAGING_ERROR"
    status_code = 500
    retryable = True


class IdempotencyConflictException(AppException):
    """Raised when a duplicate operation is detected but already processed."""
    error_code = "IDEMPOTENCY_CONFLICT"
    status_code = 409
    retryable = False


class WebhookAuthException(AppException):
    """Raised when webhook authentication fails."""
    error_code = "WEBHOOK_AUTH_FAILED"
    status_code = 401
    retryable = False

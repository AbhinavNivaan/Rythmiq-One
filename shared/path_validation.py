"""
Shared path validation for DigitalOcean Spaces storage.

This module is the SINGLE SOURCE OF TRUTH for path validation logic.
Both API and worker code MUST import from here.

Do not duplicate this logic elsewhere.
"""

import re
from typing import Tuple


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

# UUIDv4 regex pattern (lowercase, with hyphens)
# Format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
UUIDV4_PATTERN = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')

# Unix millisecond timestamp (13 digits)
TIMESTAMP_PATTERN = re.compile(r'^[0-9]{13}$')

# Safe filename characters
FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9._-]{1,128}$')

# Valid category prefixes
VALID_CATEGORIES = frozenset({'raw', 'master', 'output'})


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------

class PathValidationError(ValueError):
    """
    Raised when a storage path fails validation.
    
    This is a security-critical error - do not catch and ignore.
    """
    pass


# -----------------------------------------------------------------------------
# Component Validation
# -----------------------------------------------------------------------------

def validate_uuid(value: str, field_name: str = "uuid") -> None:
    """
    Validate a UUIDv4 string.
    
    Args:
        value: String to validate
        field_name: Name for error messages (e.g., "user_id", "job_id")
        
    Raises:
        PathValidationError: If validation fails
    """
    if not value:
        raise PathValidationError(f"Empty {field_name} not allowed")
    
    if '\0' in value:
        raise PathValidationError(f"Null byte in {field_name}")
    
    if '/' in value or '\\' in value:
        raise PathValidationError(f"Path separator in {field_name}")
    
    if '..' in value:
        raise PathValidationError(f"Path traversal in {field_name}")
    
    if not UUIDV4_PATTERN.match(value):
        raise PathValidationError(
            f"Invalid {field_name}: must be UUIDv4 format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
        )


def validate_timestamp(value: str) -> None:
    """
    Validate a Unix millisecond timestamp string.
    
    Args:
        value: String to validate (13 digits)
        
    Raises:
        PathValidationError: If validation fails
    """
    if not value:
        raise PathValidationError("Empty timestamp not allowed")
    
    if not TIMESTAMP_PATTERN.match(value):
        raise PathValidationError("Invalid timestamp: must be 13 digits (Unix ms)")


def validate_filename(value: str) -> None:
    """
    Validate a sanitized filename.
    
    Args:
        value: Filename to validate
        
    Raises:
        PathValidationError: If validation fails
    """
    if not value:
        raise PathValidationError("Empty filename not allowed")
    
    if '\0' in value:
        raise PathValidationError("Null byte in filename")
    
    if '/' in value or '\\' in value:
        raise PathValidationError("Path separator in filename")
    
    if '..' in value:
        raise PathValidationError("Path traversal in filename")
    
    if not FILENAME_PATTERN.match(value):
        raise PathValidationError(
            "Invalid filename: only a-z, A-Z, 0-9, '.', '-', '_' allowed (max 128 chars)"
        )
    
    if value[0] in '.-':
        raise PathValidationError("Filename cannot start with '.' or '-'")


# -----------------------------------------------------------------------------
# Filename Sanitization
# -----------------------------------------------------------------------------

def sanitize_filename(raw_filename: str) -> str:
    """
    Sanitize a user-provided filename for safe storage.
    
    Transformations:
    - Replace unsafe characters with underscore
    - Collapse multiple consecutive dots
    - Remove leading dot/dash
    - Truncate to 128 characters
    
    Args:
        raw_filename: Original filename from user
        
    Returns:
        Sanitized filename safe for storage paths
    """
    if not raw_filename:
        return "unnamed"
    
    # Replace unsafe characters with underscore
    safe = re.sub(r'[^a-zA-Z0-9._-]', '_', raw_filename)
    
    # Collapse multiple consecutive dots
    safe = re.sub(r'\.{2,}', '.', safe)
    
    # Remove leading dot or dash
    safe = safe.lstrip('.-')
    
    # Truncate to max length
    safe = safe[:128]
    
    # If nothing left, use default
    if not safe:
        return "unnamed"
    
    return safe


# -----------------------------------------------------------------------------
# Full Path Validation
# -----------------------------------------------------------------------------

def validate_storage_path(path: str) -> Tuple[str, str, str]:
    """
    Validate a complete storage path.
    
    Valid path structures:
        raw/{user_id}/{job_id}/{filename...}
        master/{user_id}/{document_id}/{filename...}
        output/{user_id}/{job_id}/{filename...}
    
    Validation rules:
    - No absolute paths (leading /)
    - No path traversal (..)
    - No null bytes
    - Must have valid category prefix
    - Must have valid user_id (UUIDv4)
    - Must have valid object_id (UUIDv4) - job_id or document_id
    - Must have at least one filename component
    
    Args:
        path: Full storage path (without bucket)
        
    Returns:
        Tuple of (category, user_id, object_id)
        
    Raises:
        PathValidationError: If path is invalid or unsafe
    """
    if not path:
        raise PathValidationError("Empty path not allowed")
    
    # Security: reject absolute paths
    if path.startswith('/'):
        raise PathValidationError("Absolute paths not allowed")
    
    # Security: reject traversal
    if '..' in path:
        raise PathValidationError("Path traversal not allowed")
    
    # Security: reject null bytes
    if '\0' in path:
        raise PathValidationError("Null bytes not allowed")
    
    parts = path.split('/')
    
    # Minimum: category/user_id/object_id/filename (4 components)
    if len(parts) < 4:
        raise PathValidationError(
            "Path too short: must have at least category/user_id/object_id/filename"
        )
    
    category = parts[0]
    user_id = parts[1]
    object_id = parts[2]
    filename_parts = parts[3:]  # May have multiple components
    
    # Validate category
    if category not in VALID_CATEGORIES:
        raise PathValidationError(f"Invalid category '{category}': must be one of {VALID_CATEGORIES}")
    
    # Validate user_id
    validate_uuid(user_id, "user_id")
    
    # Validate object_id (job_id or document_id)
    validate_uuid(object_id, "object_id")
    
    # Validate filename exists (at least one non-empty component)
    if not filename_parts or not filename_parts[0]:
        raise PathValidationError("Filename required after object_id")
    
    return (category, user_id, object_id)


# -----------------------------------------------------------------------------
# Path Builders
# -----------------------------------------------------------------------------

def build_raw_path(user_id: str, job_id: str, timestamp_ms: int, filename: str) -> str:
    """
    Build a validated path for raw artifact storage.
    
    Args:
        user_id: User UUID (UUIDv4 format)
        job_id: Job UUID (UUIDv4 format)
        timestamp_ms: Upload timestamp in milliseconds
        filename: Original filename (will be sanitized)
        
    Returns:
        Validated storage path: raw/{user_id}/{job_id}/{timestamp}_{filename}
    """
    validate_uuid(user_id, "user_id")
    validate_uuid(job_id, "job_id")
    validate_timestamp(str(timestamp_ms))
    safe_filename = sanitize_filename(filename)
    
    path = f"raw/{user_id}/{job_id}/{timestamp_ms}_{safe_filename}"
    validate_storage_path(path)
    return path


def build_master_path(user_id: str, document_id: str) -> str:
    """
    Build a validated path for master document storage.
    
    Args:
        user_id: User UUID (UUIDv4 format)
        document_id: Document UUID (UUIDv4 format)
        
    Returns:
        Validated storage path: master/{user_id}/{document_id}/{document_id}.enc
    """
    validate_uuid(user_id, "user_id")
    validate_uuid(document_id, "document_id")
    
    # Use document_id as filename for explicit identification
    path = f"master/{user_id}/{document_id}/{document_id}.enc"
    validate_storage_path(path)
    return path


def build_output_path(user_id: str, job_id: str, timestamp_ms: int) -> str:
    """
    Build a validated path for output ZIP storage.
    
    Args:
        user_id: User UUID (UUIDv4 format)
        job_id: Job UUID (UUIDv4 format)
        timestamp_ms: Output generation timestamp in milliseconds
        
    Returns:
        Validated storage path: output/{user_id}/{job_id}/{timestamp}_output.zip.enc
    """
    validate_uuid(user_id, "user_id")
    validate_uuid(job_id, "job_id")
    validate_timestamp(str(timestamp_ms))
    
    path = f"output/{user_id}/{job_id}/{timestamp_ms}_output.zip.enc"
    validate_storage_path(path)
    return path

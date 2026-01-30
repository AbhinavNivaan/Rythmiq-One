"""
Error handling package.

Re-exports the main error classes from the legacy errors.py module
to maintain backward compatibility while allowing the errors/ directory
to exist for additional error utilities.
"""

# Import from the parent-level errors.py module by reading it directly
# This is a workaround for the shadowing issue
import sys
import importlib.util
from pathlib import Path

# Load errors.py directly since this package shadows it
_errors_py = Path(__file__).parent.parent / "errors.py"
_spec = importlib.util.spec_from_file_location("_errors_module", _errors_py)
_errors_module = importlib.util.module_from_spec(_spec)
sys.modules["_errors_module"] = _errors_module
_spec.loader.exec_module(_errors_module)

# Re-export all public names
WorkerError = _errors_module.WorkerError
ErrorCode = _errors_module.ErrorCode
ProcessingStage = _errors_module.ProcessingStage
RETRYABLE_CODES = _errors_module.RETRYABLE_CODES

# Re-export helper functions
wrap_exception = _errors_module.wrap_exception
create_error = _errors_module.create_error
payload_missing = _errors_module.payload_missing
payload_invalid = _errors_module.payload_invalid
artifact_source_invalid = _errors_module.artifact_source_invalid
fetch_failed = _errors_module.fetch_failed
decode_failed = _errors_module.decode_failed
ocr_failed = _errors_module.ocr_failed
schema_failed = _errors_module.schema_failed
upload_failed = _errors_module.upload_failed
internal_error = _errors_module.internal_error

# Also export from error_codes.py for new code
from errors.error_codes import ProcessingError

__all__ = [
    'WorkerError',
    'ErrorCode', 
    'ProcessingStage',
    'RETRYABLE_CODES',
    'ProcessingError',
    'wrap_exception',
    'create_error',
    'payload_missing',
    'payload_invalid',
    'artifact_source_invalid',
    'fetch_failed',
    'decode_failed',
    'ocr_failed',
    'schema_failed',
    'upload_failed',
    'internal_error',
]

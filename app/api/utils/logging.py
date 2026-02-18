"""
Log redaction utilities to prevent sensitive data leakage.

SECURITY: Never log encryption keys, tokens, or passwords.
This module automatically redacts sensitive fields from all log output.
"""

import re
import logging
from typing import Any, Dict


# Patterns to redact from logs - matches various formats
REDACT_PATTERNS = [
    # SEK in various formats (base64, 40+ chars)
    (r'sek_b64:\s+"([A-Za-z0-9+/]{30,})"', 'sek_b64: "[REDACTED_SEK]"'),
    (r"sek_b64:\s+'([A-Za-z0-9+/]{30,})'", "sek_b64: '[REDACTED_SEK]'"),
    (r'sek_b64:\s+([A-Za-z0-9+/]{30,})[\s,}]', 'sek_b64: [REDACTED_SEK] '),
    (r'"sek_b64"\s*:\s*"([A-Za-z0-9+/=]{40,})"', '"sek_b64": "[REDACTED_SEK]"'),
    (r"'sek_b64'\s*:\s*'([A-Za-z0-9+/=]{40,})'", "'sek_b64': '[REDACTED_SEK]'"),
    (r'sek_b64":\s*"([A-Za-z0-9+/=]{40,})"', 'sek_b64": "[REDACTED_SEK]"'),
    (r"sek_b64':\s*'([A-Za-z0-9+/=]{40,})'", "sek_b64': '[REDACTED_SEK]'"),
    (r"sek_b64=([A-Za-z0-9+/=]{40,})", "sek_b64=[REDACTED_SEK]"),
    
    # Storage encryption key
    (r'storage_encryption_key:\s+"([^"]{8,})"', 'storage_encryption_key: "[REDACTED]"'),
    (r"storage_encryption_key:\s+'([^']{8,})'", "storage_encryption_key: '[REDACTED]'"),
    (r'storage_encryption_key:\s+([A-Za-z0-9+/=]{8,})[\s,}]', 'storage_encryption_key: [REDACTED] '),
    (r'"storage_encryption_key"\s*:\s*"([^"]{10,})"', '"storage_encryption_key": "[REDACTED]"'),
    (r"'storage_encryption_key'\s*:\s*'([^']{10,})'", "'storage_encryption_key': '[REDACTED]'"),
    (r"storage_encryption_key=([A-Za-z0-9+/=]{10,})", "storage_encryption_key=[REDACTED]"),
    
    # JWT tokens (Bearer tokens)
    (r'Bearer\s+([A-Za-z0-9\-_.]+\.[A-Za-z0-9\-_.]+\.[A-Za-z0-9\-_.]+)', 'Bearer [REDACTED_TOKEN]'),
    (r'"access_token"\s*:\s*"([^"]{20,})"', '"access_token": "[REDACTED_TOKEN]"'),
    (r'"refresh_token"\s*:\s*"([^"]{20,})"', '"refresh_token": "[REDACTED_TOKEN]"'),
    (r"'access_token'\s*:\s*'([^']{20,})'", "'access_token': '[REDACTED_TOKEN]'"),
    (r"'refresh_token'\s*:\s*'([^']{20,})'", "'refresh_token': '[REDACTED_TOKEN]'"),
    (r'access_token:\s+"([^"]{20,})"', 'access_token: "[REDACTED_TOKEN]"'),
    (r"refresh_token:\s+'([^']{20,})'", "refresh_token: '[REDACTED_TOKEN]'"),
    (r'access_token:\s+([A-Za-z0-9._-]{20,})[\s,}]', 'access_token: [REDACTED_TOKEN] '),
    (r"refresh_token:\s+([A-Za-z0-9._-]{20,})[\s,}]", "refresh_token: [REDACTED_TOKEN] "),
    
    # Passwords
    (r'"password"\s*:\s*"([^"]{6,})"', '"password": "[REDACTED]"'),
    (r"'password'\s*:\s*'([^']{6,})'", "'password': '[REDACTED]'"),
    (r'password:\s+"([^"]{6,})"', 'password: "[REDACTED]"'),
    (r"password:\s+'([^']{6,})'", "password: '[REDACTED]'"),
    (r'password:\s+([^,}\s]{6,})[\s,}]', 'password: [REDACTED] '),
    (r"password=([^&\s]{6,})", "password=[REDACTED]"),
]


def redact_sensitive_data(message: str) -> str:
    """
    Remove sensitive data from log messages.
    
    This function is called on ALL log output to prevent
    accidental leakage of encryption keys, tokens, or passwords.
    
    Args:
        message: Original log message string
    
    Returns:
        Redacted log message with sensitive fields replaced by [REDACTED]
    
    Example:
        Input:  "Job payload: {'sek_b64': 'dGVzdGtleQ==', 'job_id': '123'}"
        Output: "Job payload: {'sek_b64': '[REDACTED]', 'job_id': '123'}"
    """
    if not isinstance(message, str):
        return str(message)
    
    redacted = message
    
    for pattern, replacement in REDACT_PATTERNS:
        redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)
    
    return redacted


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Redact sensitive fields from a dictionary.
    
    Use this before logging structured data or dict arguments.
    
    Args:
        data: Dictionary that may contain sensitive fields
    
    Returns:
        New dictionary with sensitive fields replaced by "[REDACTED]"
    
    Example:
        >>> redact_dict({"sek_b64": "secret123456", "job_id": "123"})
        {"sek_b64": "[REDACTED]", "job_id": "123"}
    """
    SENSITIVE_KEYS = {
        'sek_b64',
        'storage_encryption_key',
        'access_token',
        'refresh_token',
        'password',
        'password_hash',
        'api_key',
        'secret_key',
        'nonce',
        'encryption_nonce',
    }
    
    if not isinstance(data, dict):
        return data
    
    redacted = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_KEYS:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_dict(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key] = value
    
    return redacted


class RedactingFormatter(logging.Formatter):
    """
    Logging formatter that redacts sensitive data from all log records.
    
    This formatter automatically redacts secrets from:
    - Formatted log messages
    - Log record attributes
    - Additional context (extra fields)
    
    Install this on all loggers to automatically redact secrets
    without modifying source code.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record with redaction applied.
        
        Args:
            record: LogRecord to format
        
        Returns:
            Formatted log message with sensitive data redacted
        """
        # Redact the message
        if isinstance(record.msg, str):
            record.msg = redact_sensitive_data(record.msg)
        
        # Redact args (if using % formatting)
        if record.args:
            if isinstance(record.args, dict):
                # If using named formatting like "%(key)s"
                redacted_args = redact_dict(record.args)
                record.args = redacted_args
            elif isinstance(record.args, (tuple, list)):
                # If using positional formatting like "%s"
                redacted_args = []
                for arg in record.args:
                    if isinstance(arg, str):
                        redacted_args.append(redact_sensitive_data(arg))
                    elif isinstance(arg, dict):
                        redacted_args.append(redact_dict(arg))
                    else:
                        redacted_args.append(arg)
                record.args = tuple(redacted_args)
        
        # Redact extra fields
        if hasattr(record, '__dict__'):
            for key in list(record.__dict__.keys()):
                if key.lower() in {
                    'sek_b64', 'storage_encryption_key', 'access_token',
                    'refresh_token', 'password', 'api_key'
                }:
                    record.__dict__[key] = "[REDACTED]"
        
        # Call parent formatter
        return super().format(record)


def setup_redacting_logger(logger: logging.Logger = None) -> None:
    """
    Configure logger to redact sensitive data.
    
    Call this at application startup to enable log redaction
    for all handlers on the specified logger (or root logger).
    
    Args:
        logger: Logger to configure (default: root logger)
    
    Example:
        # In main.py or __init__.py
        from app.api.utils.logging import setup_redacting_logger
        
        setup_redacting_logger()  # Enable for root logger
        logger.info("Application started")  # SEK will be redacted if present
    """
    if logger is None:
        logger = logging.getLogger()
    
    # Create redacting formatter
    formatter = RedactingFormatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Apply to all handlers
    for handler in logger.handlers:
        handler.setFormatter(formatter)
    
    logger.debug("Log redaction formatter installed")


def safe_log_job_payload(logger: logging.Logger, level: int, payload: dict) -> None:
    """
    Safely log job payload with sensitive fields redacted.
    
    Use this instead of directly logging entire payload objects.
    
    Args:
        logger: Logger instance
        level: Logging level (logging.INFO, logging.DEBUG, etc.)
        payload: Job payload dict (may contain sek_b64)
    
    Example:
        # Bad:  logger.info(f"Creating job: {payload}")
        # Good: safe_log_job_payload(logger, logging.INFO, payload)
    """
    redacted = redact_dict(payload)
    logger.log(level, f"Job payload: {redacted}")


def safe_log_user_data(logger: logging.Logger, level: int, user: dict) -> None:
    """
    Safely log user data with sensitive fields redacted.
    
    Args:
        logger: Logger instance
        level: Logging level (logging.INFO, logging.DEBUG, etc.)
        user: User dict (may contain password_hash, tokens, etc.)
    
    Example:
        # Bad:  logger.info(f"User logged in: {user}")
        # Good: safe_log_user_data(logger, logging.INFO, user)
    """
    redacted = redact_dict(user)
    logger.log(level, f"User data: {redacted}")

#!/usr/bin/env python3
"""
Rythmiq Worker Entrypoint for Camber Cloud BASE Engine.

Execution model:
1. Read job payload from STDIN (JSON)
2. Execute exactly one job
3. Print result to STDOUT (JSON)
4. Exit with code 0 (success) or 1 (error)

No server, no polling, no queues - pure function execution.

Usage:
    echo '{"job_id": "...", "artifact_url": "...", "schema": {...}}' | python main.py
    
Environment variables (optional):
    RYTHMIQ_JOB_PAYLOAD - JSON payload (alternative to STDIN)
"""

import sys
import json
import os
from typing import Dict, Any

from job_handler import JobPayload, execute_job


def read_payload() -> Dict[str, Any]:
    """
    Read job payload from STDIN or environment variable.
    
    Priority:
    1. STDIN (if not empty/TTY)
    2. RYTHMIQ_JOB_PAYLOAD environment variable
    
    Returns:
        Parsed JSON payload as dict
        
    Raises:
        ValueError: If no payload provided or invalid JSON
    """
    payload_str: str = ""
    
    # Try STDIN first (for pipe-based invocation)
    if not sys.stdin.isatty():
        payload_str = sys.stdin.read().strip()
    
    # Fallback to environment variable
    if not payload_str:
        payload_str = os.environ.get("RYTHMIQ_JOB_PAYLOAD", "").strip()
    
    if not payload_str:
        raise ValueError("No job payload provided. Use STDIN or RYTHMIQ_JOB_PAYLOAD env var.")
    
    try:
        return json.loads(payload_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON payload: {e}")


def main() -> int:
    """
    Main entrypoint.
    
    Returns:
        0 on successful execution (even if job fails - failure is valid result)
        1 on startup/infrastructure error (invalid payload, etc.)
    """
    try:
        # Read and parse payload
        payload_dict = read_payload()
        payload = JobPayload.from_dict(payload_dict)
        
        # Execute job
        result = execute_job(payload)
        
        # Output result as JSON
        print(json.dumps(result.to_dict(), indent=2))
        
        return 0
        
    except ValueError as e:
        # Payload parsing error - infrastructure failure
        error_response = {
            "status": "FAILED",
            "job_id": None,
            "error": {
                "code": "PAYLOAD_INVALID",
                "stage": "INIT",
                "details": {"reason": str(e)}
            }
        }
        print(json.dumps(error_response, indent=2))
        return 1
        
    except Exception as e:
        # Unexpected error - infrastructure failure
        error_response = {
            "status": "FAILED",
            "job_id": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "stage": "INIT",
                "details": {"reason": type(e).__name__}
            }
        }
        print(json.dumps(error_response, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())

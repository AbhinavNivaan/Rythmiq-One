#!/usr/bin/env python3
"""Single-shot document processing worker for Camber BASE.

Execution contract (hard requirements):
- Read exactly one JSON payload from STDIN
- Process once, emit exactly one JSON response to STDOUT
- No retries, no background loops, no servers
- Exit code is always 0 (success or failure is in JSON body)
"""

import json
import sys
from typing import Any, Dict, Optional

from errors.error_codes import ProcessingError, ErrorCode, ProcessingStage
from job_handler import JobPayload, execute_job


def read_payload() -> Dict[str, Any]:

    """Read and parse the job payload strictly from STDIN."""
    raw = sys.stdin.read()
    raw = raw.strip() if raw else ""

    if not raw:
        raise ProcessingError(
            code=ErrorCode.PAYLOAD_MISSING,
            stage=ProcessingStage.INIT,
            details={"reason": "empty_stdin"}
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProcessingError(
            code=ErrorCode.PAYLOAD_INVALID,
            stage=ProcessingStage.INIT,
            details={"reason": "invalid_json", "message": str(exc)}
        )

    if not isinstance(payload, dict):
        raise ProcessingError(
            code=ErrorCode.PAYLOAD_INVALID,
            stage=ProcessingStage.INIT,
            details={"reason": "payload_not_object"}
        )

    return payload


def build_error_response(job_id: Optional[str], error_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Standardized failure envelope."""
    return {
        "status": "FAILED",
        "job_id": job_id,
        "error": error_dict,
    }


def main() -> int:
    """Orchestrate single-shot execution and emit JSON response."""
    job_id: Optional[str] = None

    try:
        payload_dict = read_payload()
        job_id = payload_dict.get("job_id")
        payload = JobPayload.from_dict(payload_dict)

        result = execute_job(payload)
        output = result.to_dict()

    except ProcessingError as err:
        output = build_error_response(job_id, err.to_dict())

    except ValueError as err:
        output = build_error_response(
            job_id,
            {
                "code": ErrorCode.PAYLOAD_INVALID.value,
                "stage": ProcessingStage.INIT.value,
                "details": {"reason": str(err)},
            },
        )

    except Exception as err:
        output = build_error_response(
            job_id,
            {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "stage": ProcessingStage.INIT.value,
                "details": {"reason": type(err).__name__},
            },
        )

    print(json.dumps(output, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

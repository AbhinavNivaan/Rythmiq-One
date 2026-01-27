"""
Database client.
Owns: Supabase client instantiation and state transition logic.
"""

import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import create_client, Client

from app.api.config import get_settings
from app.api.errors import (
    InternalException,
    NotFoundException,
    StateTransitionException,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# Valid state transitions (source -> allowed targets)
# ==============================================================================
VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"processing", "failed"},
    "processing": {"completed", "failed"},
    # Terminal states: no outward transitions
    "completed": set(),
    "failed": set(),
}

TERMINAL_STATES: set[str] = {"completed", "failed"}


@lru_cache
def get_db_client() -> Client:
    """Returns Supabase client with anon key (RLS enforced)."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


@lru_cache
def get_service_db_client() -> Client:
    """Returns Supabase client with service role (bypasses RLS)."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def transition_job_state(
    job_id: UUID,
    new_state: str,
    payload: dict[str, Any] | None = None,
    *,
    camber_job_id: str | None = None,
) -> dict[str, Any]:
    """
    Atomically transition a job to a new state with enforcement.
    
    Rules:
    - Reject invalid transitions
    - Enforce monotonic progression (no state regression)
    - Persist error payloads on failure
    - Idempotent: re-transition to same terminal state is safe
    
    Args:
        job_id: The job UUID
        new_state: Target state (pending, processing, completed, failed)
        payload: Optional data to persist (error_details for failed, output_metadata for completed)
        camber_job_id: Optional Camber job ID to store
        
    Returns:
        Updated job record
        
    Raises:
        NotFoundException: Job does not exist
        StateTransitionException: Invalid transition attempted
        InternalException: Database operation failed
    """
    if new_state not in VALID_TRANSITIONS and new_state not in TERMINAL_STATES:
        raise StateTransitionException(
            f"Unknown state: {new_state}",
            details={"new_state": new_state},
        )

    db = get_service_db_client()

    # Fetch current state
    try:
        result = (
            db.table("jobs")
            .select("id, status, camber_job_id")
            .eq("id", str(job_id))
            .limit(1)
            .execute()
        )
    except APIError as e:
        logger.error("Failed to fetch job for transition", extra={"job_id": str(job_id), "error": str(e)})
        raise InternalException("Failed to fetch job state")

    if not result.data:
        raise NotFoundException(f"Job {job_id} not found")

    job = result.data[0]
    current_state = job["status"]

    # Idempotency: if already in the target terminal state, return silently
    if current_state == new_state and new_state in TERMINAL_STATES:
        logger.info(
            "Idempotent transition: job already in target state",
            extra={"job_id": str(job_id), "state": current_state},
        )
        return job

    # Validate transition
    allowed = VALID_TRANSITIONS.get(current_state, set())
    if new_state not in allowed:
        raise StateTransitionException(
            f"Cannot transition from '{current_state}' to '{new_state}'",
            details={
                "job_id": str(job_id),
                "current_state": current_state,
                "requested_state": new_state,
                "allowed_states": list(allowed),
            },
        )

    # Build update payload
    now = datetime.now(timezone.utc).isoformat()
    update_data: dict[str, Any] = {
        "status": new_state,
        "updated_at": now,
    }

    if new_state == "processing":
        update_data["started_at"] = now
        if camber_job_id:
            update_data["camber_job_id"] = camber_job_id

    if new_state in TERMINAL_STATES:
        update_data["completed_at"] = now

    if new_state == "failed" and payload:
        update_data["error_details"] = payload

    if new_state == "completed" and payload:
        update_data["output_metadata"] = payload

    # Perform update with optimistic locking on status
    try:
        update_result = (
            db.table("jobs")
            .update(update_data)
            .eq("id", str(job_id))
            .eq("status", current_state)  # Optimistic lock
            .execute()
        )
    except APIError as e:
        logger.error(
            "Failed to update job state",
            extra={"job_id": str(job_id), "error": str(e)},
        )
        raise InternalException("Failed to update job state")

    if not update_result.data:
        # Optimistic lock failed - state changed concurrently
        logger.warning(
            "Concurrent state change detected",
            extra={
                "job_id": str(job_id),
                "expected_state": current_state,
                "target_state": new_state,
            },
        )
        raise StateTransitionException(
            "Job state changed concurrently",
            details={
                "job_id": str(job_id),
                "expected_state": current_state,
                "target_state": new_state,
            },
        )

    logger.info(
        "Job state transitioned",
        extra={
            "job_id": str(job_id),
            "old_state": current_state,
            "new_state": new_state,
        },
    )

    return update_result.data[0]


def get_job_by_id(job_id: UUID, *, use_service_role: bool = False) -> dict[str, Any] | None:
    """Fetch a job by ID."""
    db = get_service_db_client() if use_service_role else get_db_client()
    result = (
        db.table("jobs")
        .select("*")
        .eq("id", str(job_id))
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_job_by_camber_id(camber_job_id: str) -> dict[str, Any] | None:
    """Fetch a job by Camber job ID."""
    db = get_service_db_client()
    result = (
        db.table("jobs")
        .select("*")
        .eq("camber_job_id", camber_job_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None

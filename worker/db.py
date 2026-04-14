"""Database helpers for worker-side writes to Supabase."""

from __future__ import annotations

import logging
import os
from typing import Any


logger = logging.getLogger(__name__)


def get_worker_db_client() -> Any | None:
    """Create a Supabase client from worker env vars, or None when unavailable."""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        return None

    try:
        from supabase import create_client
    except ImportError:
        logger.warning("supabase package not installed; worker DB writes disabled")
        return None

    try:
        return create_client(supabase_url, supabase_key)
    except Exception as exc:
        logger.warning("Failed to initialize Supabase client: %s", type(exc).__name__)
        return None


def upsert_document_extraction(
    db_client: Any,
    *,
    job_id: str,
    user_id: str,
    document_type: str,
    status: str,
    fields: dict[str, Any],
    confidence: dict[str, float],
    model_version: str | None = None,
    error: str | None = None,
) -> bool:
    """Upsert a document extraction record for GET /jobs/{job_id}/extraction."""
    if db_client is None:
        return False

    payload: dict[str, Any] = {
        "job_id": str(job_id),
        "user_id": str(user_id),
        "document_type": str(document_type or "document"),
        "status": str(status),
        "fields": fields if isinstance(fields, dict) else {},
        "confidence": confidence if isinstance(confidence, dict) else {},
        "model_version": model_version,
        "error": error,
    }

    if status == "completed":
        from datetime import datetime, timezone
        payload["extracted_at"] = datetime.now(timezone.utc).isoformat()

    try:
        db_client.table("document_extractions").upsert(
            payload,
            on_conflict="job_id",
        ).execute()
        return True
    except Exception as exc:
        logger.warning(
            "Failed to upsert document extraction for job %s: %s",
            job_id,
            type(exc).__name__,
        )
        return False

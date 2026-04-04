"""
Internal maintenance routes.
Owns: Scheduled cleanup endpoints, not exposed to end users.
Protected by X-Internal-Secret header (constant-time comparison).
"""

import hmac
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.api.config import get_settings
from app.api.db import get_service_db_client
from app.api.errors import StorageException
from app.api.services.storage import get_storage_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["internal"])

_BATCH_SIZE = 200
_FAILED_ELIGIBILITY_DELAY_HOURS = 1    # Failed jobs: 1h floor (no feedback window)
_COMPLETED_ELIGIBILITY_DELAY_HOURS = 24  # Completed jobs: 24h feedback window


def _verify_secret(provided: str | None) -> None:
    """
    Validate the X-Internal-Secret header.

    Raises:
        HTTPException 500: INTERNAL_CLEANUP_SECRET is not configured (server misconfiguration).
        HTTPException 403: Secret is missing or incorrect.
    """
    settings = get_settings()
    secret = settings.internal_cleanup_secret
    if not secret:
        raise HTTPException(status_code=500, detail="INTERNAL_CLEANUP_SECRET is not configured")
    if not hmac.compare_digest(secret, provided or ""):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/cleanup/raw-uploads")
async def cleanup_raw_uploads(
    x_internal_secret: str | None = Header(default=None),
) -> JSONResponse:
    """
    Delete stranded raw uploads from DigitalOcean Spaces.

    Finds objects under uploads/ whose associated job is in a terminal state
    (completed or failed) and older than 1 hour, then deletes them.
    Only deletes if the Spaces key exactly matches input_metadata.storage_path
    in the DB (exact-path guard).

    Returns a JSON summary: {scanned, eligible, deleted, errors}.
    """
    _verify_secret(x_internal_secret)

    storage = get_storage_service()
    db = get_service_db_client()

    # Step 1: List all uploads/ objects (generator — handles pagination internally)
    try:
        all_objects = list(storage.list_objects("uploads/"))
    except StorageException as exc:
        logger.error("Cleanup: failed to list uploads/", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail="Failed to list storage objects")

    scanned = len(all_objects)

    # Step 2: Parse keys → job_id map (tolerant split handles filenames with slashes)
    job_key_map: dict[str, str] = {}
    for obj in all_objects:
        key: str = obj["Key"]
        parts = key.split("/", 3)  # ["uploads", user_id, job_id, filename_remainder]
        if len(parts) < 4 or parts[0] != "uploads":
            logger.debug("Cleanup: skipping malformed key", extra={"key": key})
            continue
        job_id = parts[2]
        job_key_map[job_id] = key

    if not job_key_map:
        return JSONResponse({"scanned": scanned, "eligible": 0, "deleted": 0, "errors": []})

    # Step 3: Batch-query DB for terminal jobs — separate cutoffs per status
    now = datetime.now(timezone.utc)
    completed_cutoff = (now - timedelta(hours=_COMPLETED_ELIGIBILITY_DELAY_HOURS)).isoformat()
    failed_cutoff = (now - timedelta(hours=_FAILED_ELIGIBILITY_DELAY_HOURS)).isoformat()

    job_ids = list(job_key_map.keys())
    eligible_jobs: list[dict] = []

    try:
        for i in range(0, len(job_ids), _BATCH_SIZE):
            batch = job_ids[i : i + _BATCH_SIZE]

            completed = (
                db.table("jobs")
                .select("id, input_metadata")
                .in_("id", batch)
                .eq("status", "completed")
                .lt("updated_at", completed_cutoff)
                .execute()
            )
            eligible_jobs.extend(completed.data)

            failed = (
                db.table("jobs")
                .select("id, input_metadata")
                .in_("id", batch)
                .eq("status", "failed")
                .lt("updated_at", failed_cutoff)
                .execute()
            )
            eligible_jobs.extend(failed.data)
    except Exception as exc:
        logger.error("Cleanup: DB query failed", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail="Database query failed")

    # Step 4: Exact-path guard + delete
    deleted = 0
    errors: list[dict] = []

    for job in eligible_jobs:
        job_id = job["id"]
        expected_key = (job.get("input_metadata") or {}).get("storage_path")
        actual_key = job_key_map.get(job_id)

        if not expected_key or not actual_key:
            continue

        if actual_key != expected_key:
            logger.warning(
                "Cleanup: key mismatch — skipping",
                extra={"job_id": job_id, "actual": actual_key, "expected": expected_key},
            )
            continue

        try:
            storage.delete_object(actual_key)
            deleted += 1
            logger.info(
                "Cleanup: deleted stranded raw upload",
                extra={"job_id": job_id, "key": actual_key},
            )
        except StorageException as exc:
            logger.warning(
                "Cleanup: delete failed",
                extra={"key": actual_key, "error": str(exc)},
            )
            errors.append({"key": actual_key, "error": str(exc)})

    return JSONResponse({
        "scanned": scanned,
        "eligible": len(eligible_jobs),
        "deleted": deleted,
        "errors": errors,
    })

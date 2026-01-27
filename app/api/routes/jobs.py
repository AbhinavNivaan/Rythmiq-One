"""
Jobs routes.
Owns: Job CRUD operations with Camber integration.

This module is a thin orchestrator:
- No OCR
- No image processing
- No schema logic
- Only validation, persistence, and dispatch
"""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from postgrest.exceptions import APIError

from app.api.auth import AuthenticatedUser, get_current_user
from app.api.db import get_db_client, transition_job_state, TERMINAL_STATES
from app.api.errors import (
    CamberException,
    InternalException,
    InvalidInputException,
    JobNotCompleteException,
    NotFoundException,
    SchemaNotFoundException,
)
from app.api.services.storage import StorageService, get_storage_service
from app.api.services.camber import CamberService, get_camber_service
from app.api.services.packaging import PackagingService, get_packaging_service
from .models import (
    CreateJobRequest,
    CreateJobResponse,
    JobOutputResponse,
    JobStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=CreateJobResponse)
async def create_job(
    request: Request,
    body: CreateJobRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
    camber: Annotated[CamberService, Depends(get_camber_service)],
) -> CreateJobResponse:
    """
    Create a new job.
    
    Flow:
    1. Authenticate user
    2. Validate input
    3. Create DB job (status = pending)
    4. Generate signed upload URL
    5. Submit job to Camber
    6. Update job → processing
    7. Return { job_id, upload_url }
    
    If Camber submission fails → job = failed
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    db = get_db_client()

    # -------------------------------------------------------------------------
    # 1. Verify portal schema exists and is active
    # -------------------------------------------------------------------------
    schema_result = (
        db.table("portal_schemas")
        .select("id, name")
        .eq("name", body.portal_schema_name)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    if not schema_result.data:
        raise SchemaNotFoundException(
            f"Portal schema '{body.portal_schema_name}' not found or not active"
        )

    portal_schema = schema_result.data[0]
    portal_schema_id = portal_schema["id"]

    # -------------------------------------------------------------------------
    # 2. Create job record (pending)
    # -------------------------------------------------------------------------
    job_data = {
        "user_id": str(user.id),
        "status": "pending",
        "portal_schema_version_id": portal_schema_id,
        "input_metadata": {
            "original_filename": body.filename,
            "mime_type": body.mime_type,
            "file_size_bytes": body.file_size_bytes,
            "correlation_id": correlation_id,
        },
    }

    try:
        job_result = db.table("jobs").insert(job_data).execute()
    except APIError as e:
        logger.error("Failed to create job", extra={"error": str(e), "correlation_id": correlation_id})
        raise InternalException("Failed to create job record")

    if not job_result.data:
        raise InternalException("Failed to create job record")

    job = job_result.data[0]
    job_id = UUID(job["id"])

    logger.info(
        "Job created in pending state",
        extra={
            "job_id": str(job_id),
            "user_id": str(user.id),
            "correlation_id": correlation_id,
        },
    )

    # -------------------------------------------------------------------------
    # 3. Generate signed upload URL
    # -------------------------------------------------------------------------
    upload_url, storage_path, expires_at = storage.generate_upload_url(
        job_id=job_id,
        user_id=user.id,
        filename=body.filename,
        mime_type=body.mime_type,
    )

    # Update job with storage path
    try:
        db.table("jobs").update(
            {"input_metadata": {**job_data["input_metadata"], "storage_path": storage_path}}
        ).eq("id", str(job_id)).execute()
    except APIError as e:
        logger.error("Failed to update job metadata", extra={"job_id": str(job_id), "error": str(e)})
        # Non-fatal: continue

    # -------------------------------------------------------------------------
    # 4. Submit job to Camber
    # -------------------------------------------------------------------------
    camber_payload = {
        "job_id": str(job_id),
        "user_id": str(user.id),
        "storage_path": storage_path,
        "portal_schema_id": str(portal_schema_id),
        "portal_schema_name": body.portal_schema_name,
        "correlation_id": correlation_id,
    }

    try:
        camber_job_id = await camber.submit_job(job_id=job_id, payload=camber_payload)
    except CamberException as e:
        # Mark job as failed immediately
        logger.error(
            "Camber submission failed, marking job as failed",
            extra={
                "job_id": str(job_id),
                "error": e.message,
                "correlation_id": correlation_id,
            },
        )
        try:
            transition_job_state(
                job_id=job_id,
                new_state="failed",
                payload={
                    "code": "CAMBER_SUBMISSION_FAILED",
                    "message": "Failed to submit job to processing queue",
                    "details": e.details,
                },
            )
        except Exception as transition_error:
            logger.error(
                "Failed to transition job to failed state",
                extra={"job_id": str(job_id), "error": str(transition_error)},
            )
        raise InternalException(
            "Failed to submit job for processing",
            details={"job_id": str(job_id)},
        )

    # -------------------------------------------------------------------------
    # 5. Transition job to processing
    # -------------------------------------------------------------------------
    try:
        transition_job_state(
            job_id=job_id,
            new_state="processing",
            camber_job_id=camber_job_id,
        )
    except Exception as e:
        logger.error(
            "Failed to transition job to processing",
            extra={
                "job_id": str(job_id),
                "camber_job_id": camber_job_id,
                "error": str(e),
            },
        )
        # Job is submitted but state update failed - this is recoverable via webhook

    logger.info(
        "Job submitted to Camber",
        extra={
            "job_id": str(job_id),
            "camber_job_id": camber_job_id,
            "user_id": str(user.id),
            "portal_schema_name": body.portal_schema_name,
            "correlation_id": correlation_id,
        },
    )

    return CreateJobResponse(
        job_id=job_id,
        upload_url=upload_url,
        upload_expires_at=expires_at,
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    packaging: Annotated[PackagingService, Depends(get_packaging_service)],
) -> JobStatusResponse:
    """
    Get job status.
    
    Returns:
    {
        "job_id": "uuid",
        "status": "pending | processing | completed | failed",
        "created_at": "...",
        "completed_at": "...",
        "error": null | { code, message },
        "download_url": null | "signed-url"
    }
    """
    db = get_db_client()

    # RLS ensures user can only see their own jobs
    result = (
        db.table("jobs")
        .select(
            "id, status, user_id, portal_schema_version_id, created_at, started_at, completed_at, error_details"
        )
        .eq("id", str(job_id))
        .eq("user_id", str(user.id))
        .limit(1)
        .execute()
    )

    if not result.data:
        raise NotFoundException(f"Job {job_id} not found")

    job = result.data[0]

    # Get portal schema name
    portal_schema_name = None
    if job["portal_schema_version_id"]:
        schema_result = (
            db.table("portal_schemas")
            .select("name")
            .eq("id", job["portal_schema_version_id"])
            .limit(1)
            .execute()
        )
        if schema_result.data:
            portal_schema_name = schema_result.data[0]["name"]

    # Generate download URL if completed
    download_url = None
    if job["status"] == "completed":
        url_result = packaging.get_output_download_url(job_id, user.id)
        if url_result:
            download_url = url_result[0]

    # Format error for response
    error = None
    if job["error_details"]:
        error = {
            "code": job["error_details"].get("code", "UNKNOWN_ERROR"),
            "message": job["error_details"].get("message", "An error occurred"),
        }

    return JobStatusResponse(
        job_id=UUID(job["id"]),
        status=job["status"],
        portal_schema_name=portal_schema_name,
        created_at=job["created_at"],
        started_at=job["started_at"],
        completed_at=job["completed_at"],
        error_details=error,
        download_url=download_url,
    )


@router.get("/{job_id}/output", response_model=JobOutputResponse)
async def get_job_output(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
    packaging: Annotated[PackagingService, Depends(get_packaging_service)],
) -> JobOutputResponse:
    """
    Get job output data.
    
    Only available for completed jobs.
    """
    db = get_db_client()

    # Get job status first (RLS enforced)
    job_result = (
        db.table("jobs")
        .select("id, status, user_id")
        .eq("id", str(job_id))
        .eq("user_id", str(user.id))
        .limit(1)
        .execute()
    )

    if not job_result.data:
        raise NotFoundException(f"Job {job_id} not found")

    job = job_result.data[0]

    if job["status"] != "completed":
        raise JobNotCompleteException(
            f"Job {job_id} is not complete",
            details={"current_status": job["status"]},
        )

    # Get document output (RLS enforced)
    doc_result = (
        db.table("documents")
        .select("portal_outputs, canonical_output")
        .eq("job_id", str(job_id))
        .eq("user_id", str(user.id))
        .limit(1)
        .execute()
    )

    if not doc_result.data:
        raise NotFoundException(f"Output for job {job_id} not found")

    document = doc_result.data[0]
    portal_outputs = document.get("portal_outputs", {})

    # Get first portal output
    portal_output = {}
    if portal_outputs:
        first_portal = next(iter(portal_outputs.values()), {})
        portal_output = first_portal.get("payload", {})

    # Get download URL
    download_url = None
    url_result = packaging.get_output_download_url(job_id, user.id)
    if url_result:
        download_url = url_result[0]

    return JobOutputResponse(
        job_id=job_id,
        portal_output=portal_output,
        download_url=download_url,
    )

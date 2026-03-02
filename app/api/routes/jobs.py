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
from app.api.db import get_db_client, get_service_db_client, transition_job_state, TERMINAL_STATES
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
from app.api.config import get_settings
from app.api.routes.webhooks import _persist_worker_output
from .models import (
    CreateJobRequest,
    CreateJobResponse,
    JobOutputResponse,
    SubmitJobResponse,
    JobStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _submit_job_to_processing(
    *,
    job_id: UUID,
    user_id: UUID,
    job_type: str,
    document_type: str,
    portal_schema_id: str | None,
    portal_schema_name: str | None,
    portal_schema_version: int | None,
    portal_schema_definition: dict[str, Any] | None,
    storage_path: str,
    input_metadata: dict[str, Any] | None,
    correlation_id: str,
    camber: CamberService,
) -> None:
    settings = get_settings()

    if settings.execution_backend.lower() == "cloudrun":
        metadata = input_metadata or {}

        camber_payload: dict[str, Any] = {
            "job_id": str(job_id),
            "user_id": str(user_id),
            "mode": job_type,
            "document_type": document_type,
            "input": {
                "raw_path": storage_path,
                "artifact_url": None,
                "mime_type": metadata.get("mime_type", "image/jpeg"),
                "original_filename": metadata.get("original_filename", f"{job_id}.jpg"),
            },
            "storage": {
                "bucket": settings.spaces_bucket,
                "region": settings.spaces_region,
                "endpoint": settings.spaces_endpoint,
            },
            "correlation_id": correlation_id,
        }

        if job_type == "adapt":
            camber_payload["portal_schema"] = {
                "id": str(portal_schema_id),
                "name": portal_schema_name,
                "version": int(portal_schema_version or 1),
                "schema_definition": portal_schema_definition or {},
            }
        else:
            camber_payload["master_constraints"] = {
                "max_kb": 2000,
                "target_dpi": 300,
                "output_format": "jpeg",
                "quality": 92,
                "filename_pattern": "{job_id}_master",
            }
            # Backward compatibility: older worker images still require portal_schema.
            # Newer master-mode workers ignore this for mode=master.
            camber_payload["portal_schema"] = {
                "id": "master-generic-v1",
                "name": "master_generic",
                "version": 1,
                "schema_definition": {
                    "target_width": 1200,
                    "target_height": 1600,
                    "target_dpi": 300,
                    "max_kb": 2000,
                    "filename_pattern": "{job_id}_master",
                    "output_format": "jpeg",
                    "quality": 92,
                },
            }
    else:
        camber_payload = {
            "job_id": str(job_id),
            "user_id": str(user_id),
            "job_type": job_type,
            "document_type": document_type,
            "storage_path": storage_path,
            "portal_schema_id": str(portal_schema_id) if portal_schema_id else None,
            "portal_schema_name": portal_schema_name,
            "correlation_id": correlation_id,
        }

    try:
        worker_job_id = await camber.submit_job(job_id=job_id, payload=camber_payload)
    except CamberException as e:
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

    try:
        transition_job_state(
            job_id=job_id,
            new_state="processing",
        )
    except Exception as e:
        logger.error(
            "Failed to transition job to processing",
            extra={
                "job_id": str(job_id),
                "error": str(e),
            },
        )

    logger.info(
        "Job submitted for processing",
        extra={
            "job_id": str(job_id),
            "user_id": str(user_id),
            "job_type": job_type,
            "correlation_id": correlation_id,
        },
    )

    if settings.execution_backend.lower() == "cloudrun":
        try:
            status_result = await camber.get_job_status(worker_job_id)
            success = status_result.get("success") is not False and status_result.get("status") != "failed"

            worker_result = {
                "status": "success" if success else "failed",
                "output": status_result.get("output") or {},
                "error": status_result.get("error"),
            }

            if success:
                transition_job_state(
                    job_id=job_id,
                    new_state="completed",
                )
                packaging = get_packaging_service()
                try:
                    output_path = packaging.package_job_output(
                        job_id=job_id,
                        user_id=user_id,
                        worker_result=worker_result,
                    )
                    db = get_db_client()
                    db.table("jobs").update({
                        "metadata": {
                            "output_path": output_path,
                            "packaged": True,
                        }
                    }).eq("id", str(job_id)).execute()
                except Exception as e:
                    logger.error(
                        "Failed to package Cloud Run output",
                        extra={
                            "job_id": str(job_id),
                            "error_type": type(e).__name__,
                            "error": str(e),
                        },
                        exc_info=True,  # Include full traceback
                    )
                    # Store error in metadata for debugging
                    try:
                        db.table("jobs").update({
                            "metadata": {
                                "packaging_error": str(e),
                                "error_type": type(e).__name__,
                            }
                        }).eq("id", str(job_id)).execute()
                    except Exception as meta_error:
                        logger.warning(
                            "Could not update job with packaging error",
                            extra={"job_id": str(job_id), "error": str(meta_error)},
                        )

                _persist_worker_output(get_service_db_client(), job_id, user_id, worker_result, correlation_id)
            else:
                error = worker_result.get("error") or {}
                transition_job_state(
                    job_id=job_id,
                    new_state="failed",
                    payload={
                        "code": error.get("code", "WORKER_ERROR"),
                        "message": error.get("message", "Worker processing failed"),
                        "details": error,
                    },
                )
        except Exception as e:
            logger.error(
                "Failed to finalize Cloud Run job",
                extra={"job_id": str(job_id), "error": str(e)},
            )


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

    portal_schema: dict[str, Any] | None = None
    portal_schema_id: str | None = None

    if body.job_type == "adapt":
        if not body.portal_schema_name:
            raise InvalidInputException("portal_schema_name is required for adapt jobs")

        schema_result = (
            db.table("portal_schemas")
            .select("id, name, version, schema_definition")
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
        portal_schema_id = str(portal_schema["id"])

    # -------------------------------------------------------------------------
    # 2. Create job record (pending)
    # -------------------------------------------------------------------------
    job_data = {
        "user_id": str(user.id),
        "status": "pending",
        "portal_schema_version_id": portal_schema_id,
        "input_metadata": {
            "mode": body.job_type,
            "document_type": body.document_type,
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

    if not body.defer_processing:
        await _submit_job_to_processing(
            job_id=job_id,
            user_id=user.id,
            job_type=body.job_type,
            document_type=body.document_type,
            portal_schema_id=portal_schema_id,
            portal_schema_name=portal_schema.get("name") if portal_schema else None,
            portal_schema_version=int(portal_schema.get("version", 1)) if portal_schema else None,
            portal_schema_definition=portal_schema.get("schema_definition") if portal_schema else None,
            storage_path=storage_path,
            input_metadata=job_data["input_metadata"],
            correlation_id=correlation_id,
            camber=camber,
        )
    else:
        logger.info(
            "Job created with deferred processing",
            extra={
                "job_id": str(job_id),
                "user_id": str(user.id),
                "job_type": body.job_type,
                "correlation_id": correlation_id,
            },
        )

    return CreateJobResponse(
        job_id=job_id,
        upload_url=upload_url,
        upload_expires_at=expires_at,
    )


@router.post("/{job_id}/submit", response_model=SubmitJobResponse)
async def submit_job(
    request: Request,
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    camber: Annotated[CamberService, Depends(get_camber_service)],
) -> SubmitJobResponse:
    """
    Submit an existing pending job for processing.

    Expected usage:
    1) Create job with defer_processing=true
    2) Upload file to returned upload_url
    3) Call this endpoint to dispatch processing
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    db = get_db_client()

    result = (
        db.table("jobs")
        .select("id, user_id, status, portal_schema_version_id, input_metadata")
        .eq("id", str(job_id))
        .eq("user_id", str(user.id))
        .limit(1)
        .execute()
    )

    if not result.data:
        raise NotFoundException(f"Job {job_id} not found")

    job = result.data[0]
    if job["status"] != "pending":
        raise InvalidInputException(
            f"Job {job_id} is not pending",
            details={"current_status": job["status"]},
        )

    metadata = job.get("input_metadata") or {}
    storage_path = metadata.get("storage_path")
    if not storage_path:
        raise InvalidInputException(
            "Job is missing upload metadata",
            details={"job_id": str(job_id)},
        )

    job_type = metadata.get("mode", "master")
    document_type = metadata.get("document_type", "document")

    portal_schema: dict[str, Any] | None = None
    if job_type == "adapt":
        schema_result = (
            db.table("portal_schemas")
            .select("id, name, version, schema_definition")
            .eq("id", str(job["portal_schema_version_id"]))
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

        if not schema_result.data:
            raise SchemaNotFoundException("Portal schema for job not found or inactive")

        portal_schema = schema_result.data[0]

    await _submit_job_to_processing(
        job_id=job_id,
        user_id=user.id,
        job_type=job_type,
        document_type=document_type,
        portal_schema_id=str(portal_schema["id"]) if portal_schema else None,
        portal_schema_name=portal_schema.get("name") if portal_schema else None,
        portal_schema_version=int(portal_schema.get("version", 1)) if portal_schema else None,
        portal_schema_definition=portal_schema.get("schema_definition") if portal_schema else None,
        storage_path=storage_path,
        input_metadata=metadata,
        correlation_id=correlation_id,
        camber=camber,
    )

    return SubmitJobResponse(job_id=job_id, status="processing")


@router.get("")
async def list_jobs(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> dict[str, list[dict[str, Any]]]:
    """
    List jobs for the authenticated user.

    Response shape matches mobile UI expectations.
    """
    db = get_db_client()

    result = (
        db.table("jobs")
        .select("id, status, created_at, updated_at, error_details, input_metadata")
        .eq("user_id", str(user.id))
        .order("created_at", desc=True)
        .execute()
    )

    jobs: list[dict[str, Any]] = []
    for row in result.data or []:
        metadata = row.get("input_metadata") or {}
        is_adapt = metadata.get("mode") == "adapt" or metadata.get("source_job_id") is not None
        job_type = "adapt" if is_adapt else "master"

        error = None
        if row.get("error_details"):
            error_details = row["error_details"]
            error = {
                "code": error_details.get("code", "UNKNOWN_ERROR"),
                "message": error_details.get("message", "An error occurred"),
            }

        # Generate preview URL optimistically for completed master jobs.
        # Preview JPEGs are unencrypted. URL generation is a local signing
        # operation (no S3 round-trip). The app handles 404s gracefully.
        preview_url = None
        if row["status"] == "completed" and job_type == "master":
            try:
                preview_path = f"output/{user.id}/{row['id']}/preview.jpg"
                preview_url, _ = storage.generate_download_url(preview_path)
            except Exception:
                pass  # Non-fatal: app falls back to icon

        jobs.append(
            {
                "job_id": row["id"],
                "status": row["status"],
                "job_type": job_type,
                "document_type": metadata.get("document_type", "photo" if job_type == "master" else "document"),
                "document_name": metadata.get("original_filename"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "quality_score": None,
                "preview_url": preview_url,
                "error": error,
            }
        )

    return {"jobs": jobs}


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    packaging: Annotated[PackagingService, Depends(get_packaging_service)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
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

    # Generate output URLs if completed
    download_url = None
    preview_url = None
    if job["status"] == "completed":
        url_result = packaging.get_output_download_url(job_id, user.id)
        if url_result:
            download_url = url_result[0]

        preview_path = f"output/{user.id}/{job_id}/preview.jpg"
        if storage.object_exists(preview_path):
            preview_url, _ = storage.generate_download_url(preview_path)

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
        preview_url=preview_url,
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
        url_result = packaging.get_output_download_url(job_id, user.id)
        if not url_result:
            raise NotFoundException(f"Output for job {job_id} not found")

        return JobOutputResponse(
            job_id=job_id,
            portal_output={},
            download_url=url_result[0],
        )

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

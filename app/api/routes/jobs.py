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
import re as _re
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from postgrest.exceptions import APIError

from app.api.auth import AuthenticatedUser, get_current_user
from app.api.db import get_db_client, get_service_db_client, transition_job_state, TERMINAL_STATES
from app.api.errors import (
    CamberException,
    ConflictException,
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
from app.api.services.gemini import categorize_document
from app.api.services import feedback_gcs
from app.api import slack
from .models import (
    CategorizationResponse,
    CreateJobRequest,
    CreateJobResponse,
    ExtractionResponse,
    FeedbackRequest,
    JobOutputResponse,
    SubmitJobRequest,
    SubmitJobResponse,
    JobStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])

# ---------------------------------------------------------------------------
# Download filename helpers
# ---------------------------------------------------------------------------

_SUBTYPE_DISPLAY: dict[str, str] = {
    "pan_card": "PAN Card",
    "aadhaar_card": "Aadhaar Card",
    "aadhaar": "Aadhaar Card",
    "voter_id": "Voter ID Card",
    "voter_id_card": "Voter ID Card",
    "driving_licence": "Driving Licence",
    "driving_license": "Driving Licence",
    "passport": "Passport",
    "ration_card": "Ration Card",
    "birth_certificate": "Birth Certificate",
    "marriage_certificate": "Marriage Certificate",
    "class_10_marksheet": "Class 10 Marksheet",
    "class_12_marksheet": "Class 12 Marksheet",
    "class_10_certificate": "Class 10 Certificate",
    "class_12_certificate": "Class 12 Certificate",
    "passport_photo": "Passport Photo",
    "postcard_photo": "Postcard Photo",
    "profile_photo": "Profile Photo",
    "id_photo": "ID Photo",
    "personal_signature": "Signature",
}


def _humanize_subtype(subtype: str | None) -> str:
    """Return a display-ready document subtype name."""
    if not subtype:
        return "Document"
    key = subtype.lower().replace(" ", "_").replace("-", "_")
    if key in _SUBTYPE_DISPLAY:
        return _SUBTYPE_DISPLAY[key]
    return subtype.replace("_", " ").replace("-", " ").title()


def _safe_filename_part(s: str) -> str:
    """Strip characters that are invalid in filenames and collapse whitespace."""
    sanitized = _re.sub(r'[\\/:*?"<>|]', "", s)
    return _re.sub(r"\s+", " ", sanitized).strip()


def _build_download_filename(metadata: dict, ext: str) -> str:
    """
    Return a human-readable download filename for a completed job.

    Priority chain:
    1. required_output_filename in metadata (portal-mandated name for adapt jobs)
    2. [{label} ]{subtype} {portal}.{ext}  — adapt jobs
       [{label} ]{subtype} master.{ext}    — master jobs
    """
    required = _safe_filename_part(metadata.get("required_output_filename") or "")
    if required:
        return f"{required}.{ext}"

    label = _safe_filename_part(metadata.get("document_label") or "")
    subtype = _humanize_subtype(metadata.get("document_subtype"))
    mode = metadata.get("mode", "master")

    if mode == "adapt":
        portal = _safe_filename_part(metadata.get("portal_label") or "Export")
        core = f"{subtype} {portal}"
    else:
        core = f"{subtype} master"

    name = f"{label} {core}" if label else core
    return f"{_safe_filename_part(name)}.{ext}"


async def _submit_job_to_processing(
    *,
    job_id: UUID,
    user_id: UUID,
    job_type: str,
    document_type: str,
    document_category: str | None = None,
    document_subtype: str | None = None,
    portal_schema_id: str | None,
    portal_schema_name: str | None,
    portal_schema_version: int | None,
    portal_schema_definition: dict[str, Any] | None,
    storage_path: str,
    input_metadata: dict[str, Any] | None,
    correlation_id: str,
    camber: CamberService,
    sek_b64: str | None = None,
    encrypted_input: bool = False,
    output_format: str = "jpeg",
    confirmed_crop_quad: list[list[float]] | None = None,
    quad_source: str | None = None,
) -> None:
    settings = get_settings()

    if settings.execution_backend.lower() == "cloudrun":
        metadata = input_metadata or {}

        camber_payload: dict[str, Any] = {
            "job_id": str(job_id),
            "user_id": str(user_id),
            "mode": job_type,
            "document_type": document_type,
            "document_category": document_category,
            "document_subtype": document_subtype,
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
            "encrypted_input": encrypted_input,
        }

        if confirmed_crop_quad is not None:
            camber_payload["confirmed_crop_quad"] = confirmed_crop_quad
        if quad_source is not None:
            camber_payload["quad_source"] = quad_source

        # Forward SEK when provided (zero-knowledge: key transits in-memory only,
        # never stored server-side). Required for encrypt-on-output and
        # decrypt-on-input (adapt-from-master) flows.
        if sek_b64:
            camber_payload["sek_b64"] = sek_b64

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
                "output_format": output_format,
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

    # Transition to processing BEFORE submitting to the worker.
    # The Cloud Run client is synchronous — submit_job() blocks until the worker
    # completes and the worker writes completed/failed directly to the DB.
    # Transitioning after submit_job() returns means the job is already in a
    # terminal state and the pending→processing transition is rejected.
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

                # --- Step 1: Extract master_path from worker result and persist it IMMEDIATELY.
                # This must happen before packaging so that output_url is available even if
                # ZIP creation later fails.  (Bug: previously db was defined inside the try
                # block below, so a packaging exception left master_path un-written.)
                output_data = worker_result.get("output") or {}
                artifacts_data = output_data.get("artifacts", {})
                master_path_from_worker = artifacts_data.get("master_path")
                db = get_service_db_client()
                if master_path_from_worker:
                    try:
                        db.table("jobs").update({"master_path": master_path_from_worker}).eq("id", str(job_id)).execute()
                        logger.info(
                            "master_path persisted",
                            extra={"job_id": str(job_id), "master_path": master_path_from_worker},
                        )
                    except Exception as mp_err:
                        logger.error(
                            "Failed to persist master_path",
                            extra={"job_id": str(job_id), "error": str(mp_err)},
                        )

                # --- Step 2: Package artifacts into ZIP (best-effort; not required for download).
                # ZIP packaging failure must NOT prevent master_path from being accessible.
                packaging = get_packaging_service()
                try:
                    output_path = packaging.package_job_output(
                        job_id=job_id,
                        user_id=user_id,
                        worker_result=worker_result,
                    )
                    # Merge quality scores + output path into existing input_metadata
                    job_row = db.table("jobs").select("input_metadata").eq("id", str(job_id)).limit(1).execute()
                    current_meta = ((job_row.data or [{}])[0].get("input_metadata") or {})
                    merged_meta = {
                        **current_meta,
                        "output_path": output_path,
                        "packaged": True,
                        "input_quality_score": output_data.get("input_quality_score"),
                        "output_quality_score": output_data.get("output_quality_score"),
                        "output_encrypted": artifacts_data.get("encrypted", False),
                        "output_nonce": artifacts_data.get("encryption_nonce"),
                    }
                    job_update: dict[str, Any] = {"input_metadata": merged_meta}
                    # Ensure master_path is set even if Step 1 above failed
                    if master_path_from_worker:
                        job_update["master_path"] = master_path_from_worker
                    db.table("jobs").update(job_update).eq("id", str(job_id)).execute()
                except Exception as e:
                    logger.error(
                        "Failed to package Cloud Run output",
                        extra={
                            "job_id": str(job_id),
                            "error_type": type(e).__name__,
                            "error": str(e),
                        },
                        exc_info=True,
                    )
                    # Log packaging error in input_metadata for debugging
                    try:
                        err_row = db.table("jobs").select("input_metadata").eq("id", str(job_id)).limit(1).execute()
                        err_meta = ((err_row.data or [{}])[0].get("input_metadata") or {})
                        db.table("jobs").update({
                            "input_metadata": {
                                **err_meta,
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

    # -------------------------------------------------------------------------
    # 1b. Adapt from existing master (source_job_id path — no upload needed)
    # -------------------------------------------------------------------------
    if body.job_type == "adapt" and body.source_job_id:
        has_form_schema = bool(body.form_schema_id and body.doc_id)
        has_portal_schema = bool(body.portal_schema_name)

        if not has_form_schema and not has_portal_schema:
            raise InvalidInputException(
                "Either form_schema_id + doc_id (recommended) or portal_schema_name (legacy) is required for adapt jobs"
            )

        # ---- Step A: resolve the schema definition ----
        if has_form_schema:
            # New path: form_schemas table + doc_id → pixel spec
            fs_result = (
                db.table("form_schemas")
                .select("id, body")
                .eq("id", body.form_schema_id)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            if not fs_result.data:
                raise SchemaNotFoundException(
                    f"Form schema '{body.form_schema_id}' not found or not active"
                )
            form_schema_body = fs_result.data[0]["body"]
            doc_uploads = form_schema_body.get("document_uploads", [])
            doc_entry = next((d for d in doc_uploads if d.get("doc_id") == body.doc_id), None)
            if doc_entry is None:
                raise InvalidInputException(
                    f"Document ID '{body.doc_id}' not found in form schema '{body.form_schema_id}'",
                    details={"available_doc_ids": [d.get("doc_id") for d in doc_uploads]},
                )
            schema_def: dict[str, Any] = {
                # Pass None when the schema omits fixed dimensions (e.g. PDF
                # document slots).  The worker will preserve natural image size
                # rather than forcing a resize to an arbitrary fallback.
                "target_width": doc_entry.get("target_width"),
                "target_height": doc_entry.get("target_height"),
                "target_dpi": doc_entry.get("target_dpi", 200),
                "max_kb": doc_entry.get("size_max_kb", 200),
                "min_kb": doc_entry.get("size_min_kb", 0),
                "fit_mode": doc_entry.get("fit_mode", "stretch"),
                "output_format": doc_entry.get("output_format", "jpeg"),
                "filename_pattern": f"{{job_id}}_{body.doc_id}",
            }
            portal_schema = {
                "id": f"{body.form_schema_id}:{body.doc_id}",
                "name": f"{body.form_schema_id}:{body.doc_id}",
                "version": 1,
                "schema_definition": schema_def,
            }
            portal_schema_id = None  # No legacy portal_schema_version_id for form-schema path
            # First word of short_name — e.g. "NEET" from "NEET 2026". Consistent with legacy path.
            _short_name: str = form_schema_body.get("metadata", {}).get("short_name") or body.form_schema_id or ""
            portal_label: str = _short_name.split()[0] if _short_name else ""
        else:
            # Legacy path: portal_schemas table
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
            # e.g. "UPSC" from "UPSC Photo" — take everything before the first space
            _ps_name: str = portal_schema.get("name") or ""
            portal_label = _ps_name.split()[0] if _ps_name else ""

        # ---- Step B: look up the source (master) job ----
        source_result = (
            db.table("jobs")
            .select("id, status, user_id, input_metadata, master_path")
            .eq("id", str(body.source_job_id))
            .eq("user_id", str(user.id))
            .limit(1)
            .execute()
        )
        if not source_result.data:
            raise NotFoundException(f"Source job {body.source_job_id} not found")

        source = source_result.data[0]
        if source["status"] != "completed":
            raise InvalidInputException(
                "Source job is not completed",
                details={"source_job_id": str(body.source_job_id), "status": source["status"]},
            )

        source_metadata = source.get("input_metadata") or {}

        # Prefer master_path over raw storage_path (deleted after processing).
        # master_path is populated for jobs processed after migration 20260305.
        # It may or may not be encrypted depending on whether sek_b64 was provided at master creation time.
        master_stored_path: str | None = source.get("master_path")
        raw_storage_path: str | None = source_metadata.get("storage_path")

        if master_stored_path:
            storage_path = master_stored_path
            # Use the actual encrypted flag from the source job rather than assuming True.
            # Masters are only encrypted when sek_b64 was provided at processing time.
            encrypted_input = bool(source_metadata.get("output_encrypted", False))
        elif raw_storage_path:
            storage_path = raw_storage_path   # Legacy fallback (raw upload, not yet deleted)
            encrypted_input = False
        else:
            raise InvalidInputException(
                "Source job has no retrievable input file. "
                "master_path is missing and raw upload was already deleted.",
                details={"source_job_id": str(body.source_job_id)},
            )

        document_type = source_metadata.get("document_type", body.document_type)

        adapt_job_data: dict[str, Any] = {
            "user_id": str(user.id),
            "status": "pending",
            "portal_schema_version_id": portal_schema_id,  # NULL for form-schema path
            "adapted_from_job_id": str(body.source_job_id),
            "input_metadata": {
                "mode": "adapt",
                "document_type": document_type,
                "document_category": source_metadata.get("document_category"),
                "document_subtype": source_metadata.get("document_subtype"),
                # Inherit whose document this is from the source master job.
                "document_label": source_metadata.get("document_label"),
                # Human-readable portal name used in the download filename.
                "portal_label": portal_label,
                "storage_path": storage_path,
                "adapted_from_job_id": str(body.source_job_id),
                "form_schema_id": body.form_schema_id,
                "doc_id": body.doc_id,
                "encrypted_input": encrypted_input,
                "correlation_id": correlation_id,
                # Store output_format so GET /jobs/{id} returns it for correct
                # MIME type / file extension when the client downloads the output.
                "output_format": schema_def.get("output_format", "jpeg"),
            },
        }

        try:
            adapt_result = db.table("jobs").insert(adapt_job_data).execute()
        except APIError as e:
            logger.error("Failed to create adapt job", extra={"error": str(e), "correlation_id": correlation_id})
            raise InternalException("Failed to create job record")

        if not adapt_result.data:
            raise InternalException("Failed to create job record")

        adapt_job = adapt_result.data[0]
        adapt_job_id = UUID(adapt_job["id"])

        logger.info(
            "Adapt job created from master",
            extra={
                "job_id": str(adapt_job_id),
                "source_job_id": str(body.source_job_id),
                "user_id": str(user.id),
                "form_schema_id": body.form_schema_id,
                "doc_id": body.doc_id,
                "encrypted_input": encrypted_input,
                "correlation_id": correlation_id,
            },
        )

        await _submit_job_to_processing(
            job_id=adapt_job_id,
            user_id=user.id,
            job_type="adapt",
            document_type=document_type,
            document_category=source_metadata.get("document_category"),
            document_subtype=source_metadata.get("document_subtype"),
            portal_schema_id=portal_schema_id,
            portal_schema_name=portal_schema.get("name"),
            portal_schema_version=int(portal_schema.get("version", 1)),
            portal_schema_definition=portal_schema.get("schema_definition"),
            storage_path=storage_path,
            input_metadata=adapt_job_data["input_metadata"],
            correlation_id=correlation_id,
            camber=camber,
            sek_b64=body.sek_b64,
            encrypted_input=encrypted_input,
            confirmed_crop_quad=None,
        )

        return CreateJobResponse(job_id=adapt_job_id)

    # -------------------------------------------------------------------------
    # 1c. Validate upload fields for master / legacy adapt-with-upload
    # -------------------------------------------------------------------------
    if body.job_type == "adapt":
        has_form_schema = bool(body.form_schema_id and body.doc_id)
        has_portal_schema = bool(body.portal_schema_name)

        if not has_form_schema and not has_portal_schema:
            raise InvalidInputException(
                "Either form_schema_id + doc_id (recommended) or portal_schema_name (legacy) is required for adapt jobs"
            )

        if has_form_schema:
            # New form-schema path
            fs_result = (
                db.table("form_schemas")
                .select("id, body")
                .eq("id", body.form_schema_id)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            if not fs_result.data:
                raise SchemaNotFoundException(
                    f"Form schema '{body.form_schema_id}' not found or not active"
                )
            form_schema_body = fs_result.data[0]["body"]
            doc_uploads = form_schema_body.get("document_uploads", [])
            doc_entry = next((d for d in doc_uploads if d.get("doc_id") == body.doc_id), None)
            if doc_entry is None:
                raise InvalidInputException(
                    f"Document ID '{body.doc_id}' not found in form schema '{body.form_schema_id}'",
                    details={"available_doc_ids": [d.get("doc_id") for d in doc_uploads]},
                )
            schema_def_upload: dict[str, Any] = {
                "target_width": doc_entry.get("target_width"),
                "target_height": doc_entry.get("target_height"),
                "target_dpi": doc_entry.get("target_dpi", 200),
                "max_kb": doc_entry.get("size_max_kb", 200),
                "min_kb": doc_entry.get("size_min_kb", 0),
                "fit_mode": doc_entry.get("fit_mode", "stretch"),
                "output_format": doc_entry.get("output_format", "jpeg"),
                "filename_pattern": f"{{job_id}}_{body.doc_id}",
            }
            portal_schema = {
                "id": f"{body.form_schema_id}:{body.doc_id}",
                "name": f"{body.form_schema_id}:{body.doc_id}",
                "version": 1,
                "schema_definition": schema_def_upload,
            }
            portal_schema_id = None  # No legacy portal_schema_version_id
        else:
            # Legacy portal_schema path
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

    if not body.filename or not body.mime_type or not body.file_size_bytes:
        raise InvalidInputException(
            "filename, mime_type, and file_size_bytes are required",
            details={"job_type": body.job_type},
        )

    # -------------------------------------------------------------------------
    # 2. Create job record (pending)
    # -------------------------------------------------------------------------
    job_data: dict[str, Any] = {
        "user_id": str(user.id),
        "status": "pending",
        "portal_schema_version_id": portal_schema_id,
        "input_metadata": {
            "mode": body.job_type,
            "document_type": body.document_type,
            "document_category": body.document_category,
            "document_subtype": body.document_subtype,
            "document_label": body.document_label or None,
            "original_filename": body.filename,
            "mime_type": body.mime_type,
            "file_size_bytes": body.file_size_bytes,
            "correlation_id": correlation_id,
            # Master jobs always produce JPEG output by default.
            # Stored so GET /jobs/{id} can return it for correct MIME type / extension.
            "output_format": "jpeg",
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
            document_category=body.document_category,
            document_subtype=body.document_subtype,
            portal_schema_id=portal_schema_id,
            portal_schema_name=portal_schema.get("name") if portal_schema else None,
            portal_schema_version=int(portal_schema.get("version", 1)) if portal_schema else None,
            portal_schema_definition=portal_schema.get("schema_definition") if portal_schema else None,
            storage_path=storage_path,
            input_metadata=job_data["input_metadata"],
            correlation_id=correlation_id,
            camber=camber,
            sek_b64=body.sek_b64,
            encrypted_input=False,  # Fresh upload is never pre-encrypted
            confirmed_crop_quad=None,
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
    body: SubmitJobRequest = SubmitJobRequest(),
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
        document_category=metadata.get("document_category"),
        document_subtype=metadata.get("document_subtype"),
        portal_schema_id=str(portal_schema["id"]) if portal_schema else None,
        portal_schema_name=portal_schema.get("name") if portal_schema else None,
        portal_schema_version=int(portal_schema.get("version", 1)) if portal_schema else None,
        portal_schema_definition=portal_schema.get("schema_definition") if portal_schema else None,
        storage_path=storage_path,
        input_metadata=metadata,
        correlation_id=correlation_id,
        camber=camber,
        output_format=body.output_format,
        confirmed_crop_quad=body.confirmed_crop_quad,
        quad_source=body.quad_source,
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
                "document_category": metadata.get("document_category"),
                "document_subtype": metadata.get("document_subtype"),
                "document_name": metadata.get("original_filename"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "input_quality_score": (row.get("input_metadata") or {}).get("input_quality_score"),
                "output_quality_score": (row.get("input_metadata") or {}).get("output_quality_score"),
                "preview_url": preview_url,
                "error": error,
            }
        )

    return {"jobs": jobs}


@router.post("/categorize", response_model=ExtractionResponse)
async def categorize_document_endpoint(
    image: UploadFile = File(...),
    image_width: int = Form(...),
    image_height: int = Form(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ExtractionResponse:
    """
    Classify a document image using Gemini Flash Vision.

    Returns document category, subtype, and naming suggestions.
    Always returns HTTP 200 - on any error, all fields are null.
    Image bytes are never logged or stored server-side.
    """
    # Ensure multipart metadata fields are provided and parsed.
    _ = (image_width, image_height, current_user)

    settings = get_settings()
    if not settings.gemini_api_key:
        return ExtractionResponse()

    image_bytes = await image.read()
    result = categorize_document(image_bytes, api_key=settings.gemini_api_key)

    if result is None:
        return ExtractionResponse()

    return ExtractionResponse(
        document_category=result.get("document_category"),
        document_subtype=result.get("document_subtype"),
        suggested_name=result.get("suggested_name"),
        suggested_owner=result.get("suggested_owner"),
        confidence=result.get("confidence"),
    )


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
            "id, status, user_id, portal_schema_version_id, created_at, started_at, completed_at, error_details, input_metadata, master_path"
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
    output_url = None
    meta = job.get("input_metadata") or {}
    output_encrypted = bool(meta.get("output_encrypted", False))
    output_nonce = meta.get("output_nonce")
    # "jpeg" | "pdf" — format of the processed file stored at master_path / output_url.
    # Stored in input_metadata at job creation time from the form schema's output_format.
    output_format = meta.get("output_format")  # e.g. "jpeg", "pdf"
    if job["status"] == "completed":
        url_result = packaging.get_output_download_url(job_id, user.id)
        if url_result:
            download_url = url_result[0]

        preview_path = f"output/{user.id}/{job_id}/preview.jpg"
        if storage.object_exists(preview_path):
            preview_url, _ = storage.generate_download_url(preview_path)

        master_path_stored = job.get("master_path")
        if master_path_stored:
            fmt = (output_format or "jpeg").lower()
            if fmt == "pdf":
                dl_filename = _build_download_filename(meta, "pdf")
                dl_content_type = "application/pdf"
            else:
                dl_filename = _build_download_filename(meta, "jpg")
                dl_content_type = "image/jpeg"
            output_url, _ = storage.generate_download_url(
                master_path_stored,
                filename=dl_filename,
                content_type=dl_content_type,
            )

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
        output_url=output_url,
        output_encrypted=output_encrypted,
        output_nonce=output_nonce,
        output_format=output_format,
        input_quality_score=meta.get("input_quality_score"),
        output_quality_score=meta.get("output_quality_score"),
        document_subtype=meta.get("document_subtype"),
        document_label=meta.get("document_label"),
        portal_label=meta.get("portal_label"),
    )


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> None:
    """
    Delete a job and its associated storage objects.

    Hard-deletes the DB row. Storage cleanup (input file + output directory)
    is best-effort — failures are logged but do not block the response.
    """
    db = get_db_client()

    result = (
        db.table("jobs")
        .select("id, user_id, input_metadata, master_path")
        .eq("id", str(job_id))
        .eq("user_id", str(user.id))
        .limit(1)
        .execute()
    )

    if not result.data:
        raise NotFoundException(f"Job {job_id} not found")

    job = result.data[0]
    metadata = job.get("input_metadata") or {}

    db.table("jobs").delete().eq("id", str(job_id)).eq("user_id", str(user.id)).execute()

    logger.info(
        "Job deleted",
        extra={"job_id": str(job_id), "user_id": str(user.id)},
    )

    # Best-effort: remove input file
    try:
        storage_path = metadata.get("storage_path")
        if storage_path:
            storage.delete_object(storage_path)
    except Exception:
        pass

    # Best-effort: remove output directory
    try:
        storage.delete_objects_by_prefix(f"output/{user.id}/{job_id}/", str(user.id))
    except Exception:
        pass

    # Best-effort: remove master file
    if job.get("master_path"):
        try:
            storage.delete_object(job["master_path"])
        except Exception:
            pass


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


@router.post("/{job_id}/dismiss", status_code=200)
async def dismiss_job(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> dict:
    """
    Dismiss the one-time Document Preview and delete the raw upload.
    Idempotent — returns 200 if raw upload was already deleted.
    """
    db = get_db_client()
    result = (
        db.table("jobs")
        .select("id, user_id, status, input_metadata")
        .eq("id", str(job_id))
        .eq("user_id", str(user.id))
        .limit(1)
        .execute()
    )
    if not result.data:
        raise NotFoundException(f"Job {job_id} not found")

    job_status = result.data[0].get("status")
    raw_path = (result.data[0].get("input_metadata") or {}).get("storage_path")
    if raw_path and job_status in ("completed", "failed"):
        try:
            storage.delete_object(raw_path)
            logger.info("Dismissed: raw upload deleted", extra={"job_id": str(job_id)})
        except Exception as exc:
            logger.warning(
                "Dismiss: delete failed — cleanup scheduler will retry within 24h",
                extra={"job_id": str(job_id), "error": str(exc)},
            )
    return {"status": "ok"}


@router.post("/{job_id}/feedback", status_code=201)
async def submit_feedback(
    job_id: UUID,
    body: FeedbackRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
) -> dict:
    """
    Submit a bad-output report for a completed job.
    Full report: archives raw upload to GCS, sends Slack with both signed URLs.
    Output-only report (adapt jobs): sends Slack with output preview URL only.
    Returns 409 if a report already exists for this job.
    Returns 500 if GCS archive fails — raw upload is NOT deleted, user can retry.
    """
    if not body.consent_granted:
        raise InvalidInputException("consent_granted must be true")

    settings = get_settings()
    db = get_db_client()

    result = (
        db.table("jobs")
        .select("id, user_id, status, input_metadata, master_path")
        .eq("id", str(job_id))
        .eq("user_id", str(user.id))
        .limit(1)
        .execute()
    )
    if not result.data:
        raise NotFoundException(f"Job {job_id} not found")

    job = result.data[0]
    job_status = job.get("status")
    if job_status not in ("completed", "failed"):
        raise InvalidInputException(f"Cannot report feedback on a job with status '{job_status}'")
    meta = job.get("input_metadata") or {}
    raw_path = meta.get("storage_path")
    master_path = job.get("master_path")
    user_id_str = str(user.id)
    job_id_str = str(job_id)

    pipeline_snapshot = {
        "input_quality_score": meta.get("input_quality_score"),
        "output_quality_score": meta.get("output_quality_score"),
        "stages_used": meta.get("stages_used"),
        "quad_source": meta.get("quad_source"),
        "tflite_confidence": meta.get("tflite_confidence"),
        "guard_001_triggered": meta.get("guard_001_triggered"),
        "document_type": meta.get("document_type"),
        "document_subtype": meta.get("document_subtype"),
        "document_category": meta.get("document_category"),
        "output_format": meta.get("output_format"),
    }

    raw_signed_url: str | None = None
    raw_feedback_path: str | None = None

    if body.report_type == "full" and raw_path:
        raw_bytes = storage.fetch_object(raw_path)
        # If GCS archive fails: propagate exception → 500, do not delete raw upload
        raw_feedback_path = feedback_gcs.archive_raw_upload(
            raw_bytes, job_id_str, settings.gcs_feedback_bucket
        )
        feedback_gcs.write_metadata(job_id_str, pipeline_snapshot, settings.gcs_feedback_bucket)
        raw_signed_url = feedback_gcs.generate_signed_url(raw_feedback_path, settings.gcs_feedback_bucket)

    output_preview_url: str | None = None
    preview_path = f"output/{user_id_str}/{job_id_str}/preview.jpg"
    try:
        output_preview_url, _ = storage.generate_download_url(
            preview_path, expiry_seconds=4 * 3600
        )
    except Exception:
        pass

    try:
        insert_result = (
            db.table("feedback_reports")
            .insert({
                "job_id": job_id_str,
                "user_id": user_id_str,
                "report_type": body.report_type,
                "category": body.category,
                "note": body.note,
                "consent_granted": True,
                "raw_feedback_path": raw_feedback_path,
                "master_path": master_path,
                "pipeline_snapshot": pipeline_snapshot,
                "status": "pending",
            })
            .execute()
        )
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise ConflictException(f"Feedback already submitted for job {job_id}")
        raise

    feedback_id = insert_result.data[0]["id"] if insert_result.data else "unknown"

    slack.post_feedback_report_alert(
        job_id=job_id_str,
        document_type=meta.get("document_type"),
        document_subtype=meta.get("document_subtype"),
        category=body.category,
        note=body.note,
        input_quality_score=meta.get("input_quality_score"),
        output_quality_score=meta.get("output_quality_score"),
        quad_source=meta.get("quad_source"),
        tflite_confidence=meta.get("tflite_confidence"),
        raw_input_url=raw_signed_url,
        output_preview_url=output_preview_url,
    )

    if raw_path and body.report_type == "full":
        try:
            storage.delete_object(raw_path)
        except Exception as exc:
            logger.warning(
                "Feedback: failed to delete raw upload after archiving",
                extra={"job_id": job_id_str, "error": str(exc)},
            )

    return {"status": "received", "feedback_id": feedback_id}

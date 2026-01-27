"""
FastAPI routes for artifact upload and download.

Example integration showing how to use the Spaces storage client
for signed URL generation with proper path safety enforcement.

This is a standalone example file - integrate into your FastAPI app as needed.
"""

import time
from typing import Optional
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.storage import (
    SpacesClient,
    SpacesConfig,
    SpacesStorageError,
    PathValidationError,
    build_raw_path,
    build_output_path,
    sanitize_filename,
)


# -----------------------------------------------------------------------------
# Pydantic Models
# -----------------------------------------------------------------------------

# UUIDv4 pattern: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
UUIDV4_PATTERN = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'


class UploadRequest(BaseModel):
    """Request body for upload URL generation."""
    job_id: str = Field(..., pattern=UUIDV4_PATTERN, description="Job UUID (UUIDv4 format)")
    filename: str = Field(..., min_length=1, max_length=255, description="Original filename")


class UploadResponse(BaseModel):
    """Response containing signed upload URL."""
    upload_url: str
    object_key: str
    expires_in: int


class DownloadRequest(BaseModel):
    """Request body for download URL generation."""
    job_id: str = Field(..., pattern=UUIDV4_PATTERN, description="Job UUID (UUIDv4 format)")


class DownloadResponse(BaseModel):
    """Response containing signed download URL."""
    download_url: str
    expires_in: int


# -----------------------------------------------------------------------------
# Dependency Injection
# -----------------------------------------------------------------------------

@dataclass
class AuthenticatedUser:
    """Authenticated user from JWT token."""
    user_id: str  # UUIDv4 format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx


def get_current_user() -> AuthenticatedUser:
    """
    Dependency to extract authenticated user from JWT.
    
    In production, this would:
    1. Extract JWT from Authorization header
    2. Verify signature with public key
    3. Extract user_id from claims
    
    Raises:
        HTTPException: If authentication fails
    """
    # PLACEHOLDER: Replace with actual JWT verification
    # Example implementation:
    #
    # from fastapi import Header
    # from jose import jwt, JWTError
    #
    # def get_current_user(authorization: str = Header(...)) -> AuthenticatedUser:
    #     if not authorization.startswith("Bearer "):
    #         raise HTTPException(status_code=401, detail="Invalid authorization header")
    #     token = authorization[7:]
    #     try:
    #         payload = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"])
    #         user_id = payload.get("sub")
    #         if not user_id:
    #             raise HTTPException(status_code=401, detail="Invalid token claims")
    #         return AuthenticatedUser(user_id=user_id)
    #     except JWTError:
    #         raise HTTPException(status_code=401, detail="Invalid token")
    
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="JWT verification not implemented - replace this placeholder"
    )


def get_spaces_client() -> SpacesClient:
    """
    Dependency to create Spaces client.
    
    Creates fresh client on each request (no caching).
    
    Raises:
        HTTPException: If Spaces configuration is missing
    """
    try:
        config = SpacesConfig.from_env()
        return SpacesClient(config)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Storage service not configured: {e}"
        )


# -----------------------------------------------------------------------------
# Router
# -----------------------------------------------------------------------------

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.post("/upload-url", response_model=UploadResponse)
def request_upload_url(
    request: UploadRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    spaces: SpacesClient = Depends(get_spaces_client),
) -> UploadResponse:
    """
    Generate a pre-signed URL for uploading a raw artifact.
    
    The client uploads directly to DigitalOcean Spaces using this URL.
    Files must be encrypted client-side before upload.
    
    URL expires in 5 minutes.
    """
    timestamp_ms = int(time.time() * 1000)
    
    try:
        # Build validated path with sanitized filename
        object_key = build_raw_path(
            user_id=user.user_id,
            job_id=request.job_id,
            timestamp_ms=timestamp_ms,
            filename=request.filename,
        )
        
        # Generate signed PUT URL (5 minutes)
        expires_in = 300
        upload_url = spaces.generate_upload_url(
            path=object_key,
            expires_in=expires_in,
            content_type="application/octet-stream",
        )
        
        return UploadResponse(
            upload_url=upload_url,
            object_key=object_key,
            expires_in=expires_in,
        )
    
    except PathValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid path: {e}"
        )
    except SpacesStorageError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Storage error: {e.reason}"
        )


@router.get("/download-url/{job_id}", response_model=DownloadResponse)
def request_download_url(
    job_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    spaces: SpacesClient = Depends(get_spaces_client),
) -> DownloadResponse:
    """
    Generate a pre-signed URL for downloading output ZIP.
    
    The client downloads directly from DigitalOcean Spaces using this URL.
    Files are encrypted; client must decrypt after download.
    
    URL expires in 15 minutes.
    
    Prerequisites:
    - Job must be completed (check job status before calling)
    - Output artifact must exist
    """
    # Validate job_id format (UUIDv4)
    import re
    if not re.fullmatch(UUIDV4_PATTERN, job_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job_id format: must be UUIDv4 (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
        )
    
    try:
        # Build output path
        # In production: query database for actual output timestamp
        # For now, we construct the path pattern and check existence
        
        # PRODUCTION NOTE: You would query your database here to get:
        # 1. Verify the job belongs to this user
        # 2. Verify the job status is COMPLETED
        # 3. Get the actual output_key stored when worker uploaded
        
        # Example database query:
        # job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.user_id).first()
        # if not job:
        #     raise HTTPException(status_code=404, detail="Job not found")
        # if job.status != "COMPLETED":
        #     raise HTTPException(status_code=409, detail="Job not completed")
        # object_key = job.output_key
        
        # PLACEHOLDER: This assumes you have the object_key from database
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Database query for output_key not implemented"
        )
        
        # Once you have object_key from database:
        # expires_in = 900  # 15 minutes
        # download_url = spaces.generate_download_url(
        #     path=object_key,
        #     expires_in=expires_in,
        # )
        # return DownloadResponse(
        #     download_url=download_url,
        #     expires_in=expires_in,
        # )
    
    except PathValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid path: {e}"
        )
    except SpacesStorageError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Storage error: {e.reason}"
        )


# -----------------------------------------------------------------------------
# Complete Download Endpoint (Production-Ready Example)
# -----------------------------------------------------------------------------

@router.get("/output/{job_id}/download")
def download_output(
    job_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    spaces: SpacesClient = Depends(get_spaces_client),
):
    """
    Redirect to pre-signed download URL for job output.
    
    This endpoint:
    1. Validates user owns the job
    2. Verifies job is completed
    3. Generates signed URL
    4. Returns 302 redirect
    
    The client follows the redirect to download directly from Spaces.
    """
    from fastapi.responses import RedirectResponse
    import re
    
    # Validate job_id format (UUIDv4)
    if not re.fullmatch(UUIDV4_PATTERN, job_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job_id format: must be UUIDv4 (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
        )
    
    # PRODUCTION: Replace with actual database query
    # job = await get_job_with_ownership_check(job_id, user.user_id)
    # if job.status != "COMPLETED":
    #     raise HTTPException(status_code=409, detail="Job not completed")
    # output_key = job.output_key
    
    # PLACEHOLDER
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Database integration required"
    )
    
    # Production code:
    # try:
    #     download_url = spaces.generate_download_url(
    #         path=output_key,
    #         expires_in=900,
    #     )
    #     return RedirectResponse(url=download_url, status_code=302)
    # except SpacesStorageError as e:
    #     raise HTTPException(status_code=502, detail=f"Storage error: {e.reason}")


# -----------------------------------------------------------------------------
# App Integration Example
# -----------------------------------------------------------------------------

def create_app():
    """
    Example FastAPI app factory showing router integration.
    
    Usage:
        uvicorn app.api.routes:create_app --factory
    """
    from fastapi import FastAPI
    
    app = FastAPI(
        title="Rythmiq One API",
        version="2.0.0",
        description="Document processing API with DigitalOcean Spaces storage",
    )
    
    app.include_router(router)
    
    @app.get("/health")
    def health():
        return {"status": "ok"}
    
    return app

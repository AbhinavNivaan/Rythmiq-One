"""
Auth routes.
Owns: Login, signup, logout, session validation.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from supabase import create_client, Client

from app.api.config import Settings, get_settings
from app.api.auth.dependencies import get_current_user
from app.api.auth.models import AuthenticatedUser
from app.api.db import get_service_db_client
from app.api.services.storage import StorageService, get_storage_service
from app.api.errors import StorageException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
account_router = APIRouter(tags=["account"])


# Request/Response Models
class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: dict


class SessionResponse(BaseModel):
    user_id: str
    email: str | None
    name: str | None = None
    expires_at: int


class RefreshRequest(BaseModel):
    refresh_token: str


# Supabase client factory
def get_supabase_client(settings: Settings = Depends(get_settings)) -> Client:
    return create_client(settings.supabase_url, settings.supabase_anon_key)


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    request: SignUpRequest,
    supabase: Annotated[Client, Depends(get_supabase_client)],
):
    """
    Register a new user with email and password.
    
    Returns access token and user info on success.
    """
    try:
        response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
            "options": {
                "data": {
                    "name": request.name,
                }
            }
        })
        
        if response.user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": "SIGNUP_FAILED", "message": "Failed to create user"},
            )
        
        if response.session is None:
            # Email confirmation required
            return AuthResponse(
                access_token="",
                refresh_token="",
                expires_in=0,
                user={
                    "id": str(response.user.id),
                    "email": response.user.email,
                    "name": request.name,
                    "email_confirmed": False,
                }
            )
        
        logger.info(f"User signed up: {response.user.id}")
        
        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            expires_in=response.session.expires_in,
            user={
                "id": str(response.user.id),
                "email": response.user.email,
                "name": request.name,
                "email_confirmed": response.user.email_confirmed_at is not None,
            }
        )
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Signup error: {error_msg}")
        
        if "already registered" in error_msg.lower() or "already exists" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": "EMAIL_EXISTS", "message": "Email already registered"},
            )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "SIGNUP_FAILED", "message": error_msg},
        )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    supabase: Annotated[Client, Depends(get_supabase_client)],
):
    """
    Authenticate user with email and password.
    
    Returns access token and user info on success.
    """
    try:
        response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password,
        })
        
        if response.user is None or response.session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "INVALID_CREDENTIALS", "message": "Invalid email or password"},
            )
        
        logger.info(f"User logged in: {response.user.id}")
        
        # Get user metadata
        user_meta = response.user.user_metadata or {}
        
        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            expires_in=response.session.expires_in,
            user={
                "id": str(response.user.id),
                "email": response.user.email,
                "name": user_meta.get("name"),
                "email_confirmed": response.user.email_confirmed_at is not None,
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Login error: {error_msg}")

        if "email not confirmed" in error_msg.lower() or "email not confirmed" in error_msg.replace("_", " ").lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error_code": "EMAIL_NOT_CONFIRMED", "message": "Please verify your email before signing in"},
            )
        
        if "invalid" in error_msg.lower() or "incorrect" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "INVALID_CREDENTIALS", "message": "Invalid email or password"},
            )
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "LOGIN_FAILED", "message": error_msg},
        )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    request: RefreshRequest,
    supabase: Annotated[Client, Depends(get_supabase_client)],
):
    """
    Refresh access token using refresh token.
    
    Returns new access token and refresh token.
    """
    try:
        response = supabase.auth.refresh_session(request.refresh_token)
        
        if response.user is None or response.session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "REFRESH_FAILED", "message": "Invalid or expired refresh token"},
            )
        
        user_meta = response.user.user_metadata or {}
        
        return AuthResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            expires_in=response.session.expires_in,
            user={
                "id": str(response.user.id),
                "email": response.user.email,
                "name": user_meta.get("name"),
                "email_confirmed": response.user.email_confirmed_at is not None,
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Refresh error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "REFRESH_FAILED", "message": "Failed to refresh token"},
        )


@router.get("/session", response_model=SessionResponse)
async def get_session(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    """
    Validate current session and return user info.
    
    Requires valid Bearer token in Authorization header.
    """
    return SessionResponse(
        user_id=str(user.id),
        email=user.email,
        name=user.name,
        expires_at=user.exp,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    supabase: Annotated[Client, Depends(get_supabase_client)],
):
    """
    Sign out user and invalidate session.
    
    Requires valid Bearer token in Authorization header.
    """
    try:
        supabase.auth.sign_out()
        logger.info(f"User logged out: {user.id}")
    except Exception as e:
        logger.warning(f"Logout warning (session may already be invalid): {str(e)}")

    return None


@account_router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    storage: Annotated[StorageService, Depends(get_storage_service)],
    db: Annotated[Client, Depends(get_service_db_client)],
) -> None:
    """
    Permanently delete the authenticated user's account and all associated data.

    Deletion sequence:
    1. Guard: return 409 if any jobs are pending/processing
    2. Delete all Spaces objects under uploads/{user_id}/ and output/{user_id}/
    3. Delete documents rows linked to user's jobs
    4. Delete feedback_reports rows for this user
    5. Delete all jobs rows for this user
    6. Delete Supabase auth user (invalidates all sessions immediately)
    """
    user_id = str(user.id)

    # Step 1: Guard — reject if any jobs are in-flight
    in_flight = (
        db.table("jobs")
        .select("id")
        .eq("user_id", user_id)
        .in_("status", ["pending", "processing"])
        .limit(1)
        .execute()
    )
    if in_flight.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "JOBS_IN_PROGRESS",
                "message": "Documents are still being processed — please wait and try again.",
            },
        )

    # Step 2: Storage cleanup — enumerate and delete by user prefix (best-effort)
    try:
        uploads_deleted, uploads_failed = storage.delete_objects_by_prefix(f"uploads/{user_id}/", user_id)
        output_deleted, output_failed = storage.delete_objects_by_prefix(f"output/{user_id}/", user_id)
        total_failed = uploads_failed + output_failed
        if total_failed > 0:
            logger.warning(
                "delete_account: some storage objects could not be deleted",
                extra={"user_id": user_id, "failed_count": total_failed},
            )
    except StorageException:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "STORAGE_CLEANUP_FAILED",
                "message": "Failed to enumerate storage for deletion. Please try again.",
            },
        )

    # Step 3: Delete documents rows (must precede jobs deletion — FK dependency)
    try:
        job_ids_result = (
            db.table("jobs")
            .select("id")
            .eq("user_id", user_id)
            .execute()
        )
        job_ids = [row["id"] for row in (job_ids_result.data or [])]
        if job_ids:
            db.table("documents").delete().in_("job_id", job_ids).execute()
    except Exception as e:
        logger.error(
            "delete_account: failed to delete documents rows",
            extra={"user_id": user_id, "error_type": type(e).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "DB_DELETION_FAILED",
                "message": "Failed to delete account data. Please try again.",
            },
        )

    # Step 4: Delete feedback_reports rows
    try:
        db.table("feedback_reports").delete().eq("user_id", user_id).execute()
    except Exception as e:
        logger.error(
            "delete_account: failed to delete feedback_reports rows",
            extra={"user_id": user_id, "error_type": type(e).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "DB_DELETION_FAILED",
                "message": "Failed to delete account data. Please try again.",
            },
        )

    # Step 5: Delete jobs rows
    try:
        db.table("jobs").delete().eq("user_id", user_id).execute()
    except Exception as e:
        logger.error(
            "delete_account: failed to delete jobs rows",
            extra={"user_id": user_id, "error_type": type(e).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "DB_DELETION_FAILED",
                "message": "Failed to delete account data. Please try again.",
            },
        )

    # Step 6: Delete Supabase auth user (invalidates all sessions immediately)
    try:
        db.auth.admin.delete_user(user_id)
        logger.info("delete_account: auth user deleted", extra={"user_id": user_id})
    except Exception as e:
        err_msg = str(e).lower()
        if "not found" in err_msg or "user not found" in err_msg:
            # Already deleted — treat as success (idempotent)
            logger.info("delete_account: auth user already deleted", extra={"user_id": user_id})
        else:
            logger.error(
                "delete_account: failed to delete auth user",
                extra={"user_id": user_id, "error_type": type(e).__name__},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error_code": "AUTH_DELETION_FAILED",
                    "message": "Account data deleted but auth user removal failed. Please try again.",
                },
            )

    return None

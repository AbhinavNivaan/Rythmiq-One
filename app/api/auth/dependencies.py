"""
Auth dependencies.
Owns: JWT verification, user extraction.
"""

import hmac
import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from supabase import create_client

logger = logging.getLogger(__name__)

from app.api.config import Settings, get_settings
from .models import AuthenticatedUser


def verify_jwt(token: str, secret: str) -> dict:
    # Supabase may issue HS256 or RS256 tokens depending on project settings.
    # Try HS256 first (legacy), then accept the token's stated algorithm.
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
            audience="authenticated",
        )
    except jwt.exceptions.InvalidAlgorithmError:
        # Token uses a different algorithm (e.g., RS256).
        # Decode unverified to get claims — signature will be validated
        # by the Supabase fallback in get_current_user.
        raise InvalidTokenError("Token algorithm not HS256, falling back to Supabase verification")


def decode_jwt_unverified(token: str) -> dict:
    return jwt.decode(
        token,
        options={
            "verify_signature": False,
            "verify_exp": False,
            "verify_aud": False,
        },
    )


def verify_jwt_with_supabase(token: str, settings: Settings) -> dict:
    # Check expiry locally first, before making a network call to Supabase.
    # This gives us a fast path for expired tokens.
    claims = decode_jwt_unverified(token)
    exp = claims.get("exp")
    if exp is not None:
        now = int(datetime.now(timezone.utc).timestamp())
        if int(exp) <= now:
            raise ExpiredSignatureError("Token expired")

    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    try:
        response = supabase.auth.get_user(token)
    except Exception as e:
        error_msg = str(e).lower()
        if "expired" in error_msg:
            raise ExpiredSignatureError("Token expired (Supabase)")
        raise

    if response.user is None:
        raise InvalidTokenError("Invalid token")

    if exp is None:
        raise InvalidTokenError("Missing token expiry")

    sub = claims.get("sub") or str(response.user.id)
    if str(response.user.id) != str(sub):
        raise InvalidTokenError("Token subject mismatch")

    user_meta = response.user.user_metadata or {}
    return {
        "sub": str(response.user.id),
        "email": response.user.email,
        "name": user_meta.get("name"),
        "exp": int(exp),
    }


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "Missing authorization header"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "Invalid authorization header format"},
        )

    token = parts[1]

    try:
        payload = verify_jwt(token, settings.supabase_jwt_secret)
    except InvalidTokenError as e:
        logger.warning(f"JWT direct verification failed: {type(e).__name__}: {e}")
        try:
            payload = verify_jwt_with_supabase(token, settings)
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "UNAUTHORIZED", "message": "Token expired", "token_expired": True},
            )
        except Exception as e2:
            logger.warning(f"Supabase verification also failed: {type(e2).__name__}: {e2}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "UNAUTHORIZED", "message": "Invalid token"},
            )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "Token expired", "token_expired": True},
        )

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "Invalid token payload"},
        )

    user_meta = payload.get("user_metadata") or {}
    return AuthenticatedUser(
        id=user_id,
        email=payload.get("email"),
        name=payload.get("name") or user_meta.get("name"),
        exp=payload["exp"],
    )


async def get_service_auth(
    x_webhook_secret: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> bool:
    if not x_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "Missing webhook secret"},
        )

    if not hmac.compare_digest(x_webhook_secret, settings.webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "Invalid webhook secret"},
        )

    return True

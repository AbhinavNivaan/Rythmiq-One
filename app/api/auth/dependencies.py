"""
Auth dependencies.
Owns: JWT verification, user extraction.
"""

import hmac
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from supabase import create_client

from app.api.config import Settings, get_settings
from .models import AuthenticatedUser


def verify_jwt(token: str, secret: str) -> dict:
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"require": ["exp", "sub"]},
        audience="authenticated",
    )


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
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    response = supabase.auth.get_user(token)

    if response.user is None:
        raise InvalidTokenError("Invalid token")

    claims = decode_jwt_unverified(token)
    exp = claims.get("exp")
    if exp is None:
        raise InvalidTokenError("Missing token expiry")

    now = int(datetime.now(timezone.utc).timestamp())
    if int(exp) <= now:
        raise ExpiredSignatureError("Token expired")

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
    except InvalidTokenError:
        try:
            payload = verify_jwt_with_supabase(token, settings)
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "UNAUTHORIZED", "message": "Token expired", "token_expired": True},
            )
        except Exception:
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

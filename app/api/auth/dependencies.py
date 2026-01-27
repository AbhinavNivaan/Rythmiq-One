"""
Auth dependencies.
Owns: JWT verification, user extraction.
"""

import hmac
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

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
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "Token expired", "token_expired": True},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "Invalid token"},
        )

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "Invalid token payload"},
        )

    return AuthenticatedUser(
        id=user_id,
        email=payload.get("email"),
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

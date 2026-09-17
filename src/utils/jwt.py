"""Encoding and decoding of the JWTs used for access and refresh tokens."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status

from src.config import settings

ACCESS_TOKEN = "access"
REFRESH_TOKEN = "refresh"


def create_token(user_id: str, refresh: bool = False) -> str:
    """Create a signed token. Refresh tokens get their own, longer lifetime."""
    lifetime_minutes = (
        settings.REFRESH_TOKEN_EXPIRE_MINUTES if refresh else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    now = datetime.now(UTC)

    payload: dict[str, Any] = {
        "user": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=lifetime_minutes),
        "jti": str(uuid.uuid4()),
        "refresh": refresh,
        "type": REFRESH_TOKEN if refresh else ACCESS_TOKEN,
    }

    return jwt.encode(payload=payload, key=settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: str, refresh: bool = False) -> str:
    """Backwards-compatible alias for :func:`create_token`."""
    return create_token(user_id=user_id, refresh=refresh)


def create_refresh_token(user_id: str) -> str:
    return create_token(user_id=user_id, refresh=True)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "jti", "user"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

"""Authentication dependencies shared by the routers."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.models.user import User
from src.services.users import UserService
from src.utils.jwt import decode_token
from src.utils.redis import is_token_revoked, revoke_token

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=_UNAUTHORIZED_HEADERS,
    )


class TokenBearer(HTTPBearer):
    """Validates the bearer token's signature, kind and revocation status."""

    expected_refresh: bool = False

    def __init__(self, **kwargs) -> None:
        # auto_error would answer a missing header with 403; 401 is the correct
        # status for "no credentials supplied", so we raise it ourselves.
        kwargs.setdefault("auto_error", False)
        super().__init__(**kwargs)

    async def __call__(self, request: Request) -> dict[str, Any]:  # type: ignore[override]
        credentials: HTTPAuthorizationCredentials | None = await super().__call__(request)
        if credentials is None:
            raise _unauthorized("Not authenticated")

        token_data = decode_token(credentials.credentials)

        if bool(token_data.get("refresh")) is not self.expected_refresh:
            expected = "refresh" if self.expected_refresh else "access"
            raise _unauthorized(f"A {expected} token is required")

        if await is_token_revoked(str(token_data.get("jti"))):
            raise _unauthorized("Token has been revoked")

        return token_data


class AccessTokenBearer(TokenBearer):
    expected_refresh = False


class RefreshTokenBearer(TokenBearer):
    expected_refresh = True


async def get_current_user(
    token_data: dict[str, Any] = Depends(AccessTokenBearer()),
    session: AsyncSession = Depends(get_session),
) -> User:
    try:
        user_id = uuid.UUID(str(token_data["user"]))
    except (KeyError, ValueError):
        raise _unauthorized("Invalid token subject") from None

    user = await UserService().get_user_by_id(user_id, session)
    if user is None:
        raise _unauthorized("User no longer exists")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return current_user


async def revoke_token_data(token_data: dict[str, Any]) -> None:
    """Blocklist a token for whatever lifetime it has left."""
    jti = str(token_data.get("jti", ""))
    exp = token_data.get("exp")
    if not jti or exp is None:
        return

    expires_in = int(float(exp) - datetime.now(UTC).timestamp())
    await revoke_token(jti=jti, expires_in=expires_in)

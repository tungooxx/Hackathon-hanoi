"""FastAPI dependencies that resolve cookies to authenticated users."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AUTH_ACCESS_COOKIE_NAME, AUTH_REFRESH_COOKIE_NAME
from db import get_db_session

from .exceptions import InvalidToken
from .service import AuthService, UserIdentity

access_cookie = APIKeyCookie(
    name=AUTH_ACCESS_COOKIE_NAME,
    scheme_name="AccessCookie",
    description="Short-lived HttpOnly access JWT.",
    auto_error=False,
)
refresh_cookie = APIKeyCookie(
    name=AUTH_REFRESH_COOKIE_NAME,
    scheme_name="RefreshCookie",
    description="Rotating HttpOnly refresh JWT.",
    auto_error=False,
)

DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
AccessCookie = Annotated[str | None, Security(access_cookie)]
RefreshCookie = Annotated[str | None, Security(refresh_cookie)]


def get_auth_service(session: DatabaseSession) -> AuthService:
    return AuthService(session)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


async def require_refresh_token(token: RefreshCookie) -> str:
    if not token:
        raise InvalidToken("Refresh cookie is missing")
    return token


RequiredRefreshToken = Annotated[str, Depends(require_refresh_token)]


async def get_current_user(
    token: AccessCookie,
    service: AuthServiceDependency,
) -> UserIdentity:
    if not token:
        raise InvalidToken("Access cookie is missing")
    return await service.authenticate_access_token(token)


async def get_optional_user(
    token: AccessCookie,
    service: AuthServiceDependency,
) -> UserIdentity | None:
    if not token:
        return None
    return await service.authenticate_access_token(token)


CurrentUser = Annotated[UserIdentity, Depends(get_current_user)]
OptionalUser = Annotated[UserIdentity | None, Depends(get_optional_user)]

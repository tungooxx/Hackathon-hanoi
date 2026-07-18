"""Set and clear the JWT cookies with one consistent policy."""

from __future__ import annotations

from fastapi import Response

from app.config import (
    AUTH_ACCESS_COOKIE_NAME,
    AUTH_ACCESS_COOKIE_PATH,
    AUTH_COOKIE_DOMAIN,
    AUTH_COOKIE_SAMESITE,
    AUTH_COOKIE_SECURE,
    AUTH_REFRESH_COOKIE_NAME,
    AUTH_REFRESH_COOKIE_PATH,
    JWT_ACCESS_TTL_SECONDS,
    JWT_REFRESH_TTL_SECONDS,
)

from .security import TokenPair


def set_auth_cookies(response: Response, tokens: TokenPair) -> None:
    response.set_cookie(
        key=AUTH_ACCESS_COOKIE_NAME,
        value=tokens.access_token,
        max_age=JWT_ACCESS_TTL_SECONDS,
        expires=tokens.access_expires_at,
        path=AUTH_ACCESS_COOKIE_PATH,
        domain=AUTH_COOKIE_DOMAIN,
        secure=AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=AUTH_COOKIE_SAMESITE,
    )
    response.set_cookie(
        key=AUTH_REFRESH_COOKIE_NAME,
        value=tokens.refresh_token,
        max_age=JWT_REFRESH_TTL_SECONDS,
        expires=tokens.refresh_expires_at,
        path=AUTH_REFRESH_COOKIE_PATH,
        domain=AUTH_COOKIE_DOMAIN,
        secure=AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=AUTH_COOKIE_SAMESITE,
    )
    set_no_store(response)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_ACCESS_COOKIE_NAME,
        path=AUTH_ACCESS_COOKIE_PATH,
        domain=AUTH_COOKIE_DOMAIN,
        secure=AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=AUTH_COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key=AUTH_REFRESH_COOKIE_NAME,
        path=AUTH_REFRESH_COOKIE_PATH,
        domain=AUTH_COOKIE_DOMAIN,
        secure=AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=AUTH_COOKIE_SAMESITE,
    )
    set_no_store(response)


def set_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

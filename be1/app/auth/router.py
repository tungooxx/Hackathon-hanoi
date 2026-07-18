"""HTTP routes for phone/password login and cookie-based JWT sessions."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from .cookies import clear_auth_cookies, set_auth_cookies, set_no_store
from .dependencies import (
    AuthServiceDependency,
    CurrentUser,
    RefreshCookie,
    RequiredRefreshToken,
)
from .exceptions import AuthServiceError
from .phone import mask_phone
from .schemas import (
    ApiErrorResponse,
    AuthSessionResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from .service import AuthenticationResult, UserIdentity

router = APIRouter(prefix="/auth", tags=["Authentication"])

AUTH_ERROR_RESPONSES = {
    401: {"model": ApiErrorResponse, "description": "Invalid credentials/session"},
    409: {"model": ApiErrorResponse, "description": "Phone already registered"},
    422: {"model": ApiErrorResponse, "description": "Invalid request"},
    429: {"model": ApiErrorResponse, "description": "Rate limited"},
    503: {
        "model": ApiErrorResponse,
        "description": "Authentication unavailable",
    },
}


@router.post(
    "/register",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses=AUTH_ERROR_RESPONSES,
)
async def register(
    payload: RegisterRequest,
    response: Response,
    service: AuthServiceDependency,
) -> AuthSessionResponse:
    result = await service.register(payload.phone, payload.password)
    set_auth_cookies(response, result.tokens)
    return _session_response(result)


@router.post(
    "/login",
    response_model=AuthSessionResponse,
    responses=AUTH_ERROR_RESPONSES,
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthServiceDependency,
) -> AuthSessionResponse:
    client_ip = request.client.host if request.client is not None else None
    result = await service.login(
        payload.phone,
        payload.password,
        client_ip=client_ip,
    )
    set_auth_cookies(response, result.tokens)
    return _session_response(result)


@router.post(
    "/refresh",
    response_model=AuthSessionResponse,
    responses=AUTH_ERROR_RESPONSES,
)
async def refresh_session(
    response: Response,
    refresh_token: RequiredRefreshToken,
    service: AuthServiceDependency,
) -> AuthSessionResponse:
    result = await service.refresh(refresh_token)
    set_auth_cookies(response, result.tokens)
    return _session_response(result)


@router.get(
    "/me",
    response_model=UserResponse,
    responses=AUTH_ERROR_RESPONSES,
)
async def get_me(
    response: Response,
    user: CurrentUser,
) -> UserResponse:
    set_no_store(response)
    return _user_response(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: AUTH_ERROR_RESPONSES[401]},
)
async def logout(
    service: AuthServiceDependency,
    refresh_token: RefreshCookie,
) -> Response:
    if refresh_token:
        try:
            await service.revoke_refresh_token(refresh_token)
        except AuthServiceError:
            pass
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response


def _session_response(result: AuthenticationResult) -> AuthSessionResponse:
    return AuthSessionResponse(
        user=_user_response(result.user),
        access_expires_at=result.tokens.access_expires_at,
        is_new_user=result.is_new_user,
    )


def _user_response(user: UserIdentity) -> UserResponse:
    return UserResponse(
        id=user.id,
        phone_e164=user.phone_e164,
        masked_phone=mask_phone(user.phone_e164),
        is_active=user.is_active,
    )

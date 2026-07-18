"""Sanitized JSON exception handlers for authentication and validation."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .exceptions import (
    AuthConfigurationError,
    AuthServiceError,
    ExpiredToken,
    InactiveUser,
    InvalidCredentials,
    InvalidPhoneNumber,
    InvalidToken,
    LoginRateLimited,
    PhoneAlreadyRegistered,
    RevokedAuthSession,
    WeakPassword,
)
from .schemas import ApiError, ApiErrorResponse, ValidationIssue

_UNAUTHORIZED_SESSION_ERRORS = (
    ExpiredToken,
    InactiveUser,
    InvalidToken,
    RevokedAuthSession,
)


def install_auth_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AuthServiceError, auth_exception_handler)
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )


async def auth_exception_handler(
    _request: Request,
    exc: AuthServiceError,
) -> JSONResponse:
    headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}

    if isinstance(exc, InvalidPhoneNumber):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        error = ApiError(
            code="invalid_phone",
            message="Số điện thoại không hợp lệ.",
        )
    elif isinstance(exc, WeakPassword):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        error = ApiError(
            code="weak_password",
            message="Mật khẩu không đáp ứng yêu cầu bảo mật.",
        )
    elif isinstance(exc, PhoneAlreadyRegistered):
        status_code = status.HTTP_409_CONFLICT
        error = ApiError(
            code="phone_already_registered",
            message="Số điện thoại này đã được đăng ký.",
        )
    elif isinstance(exc, LoginRateLimited):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
        retry_after = exc.retry_after_seconds
        headers["Retry-After"] = str(retry_after)
        error = ApiError(
            code="login_rate_limited",
            message="Bạn đã thử đăng nhập quá nhiều lần. Vui lòng thử lại sau.",
            details={"retry_after_seconds": retry_after},
        )
    elif isinstance(exc, InvalidCredentials):
        status_code = status.HTTP_401_UNAUTHORIZED
        error = ApiError(
            code="invalid_credentials",
            message="Số điện thoại hoặc mật khẩu không đúng.",
        )
    elif isinstance(exc, AuthConfigurationError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        error = ApiError(
            code="auth_unavailable",
            message="Dịch vụ xác thực đang tạm thời gián đoạn.",
        )
    elif isinstance(exc, _UNAUTHORIZED_SESSION_ERRORS):
        status_code = status.HTTP_401_UNAUTHORIZED
        error = ApiError(
            code="unauthorized",
            message="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
        )
    else:
        status_code = status.HTTP_400_BAD_REQUEST
        error = ApiError(
            code="authentication_failed",
            message="Không thể hoàn tất yêu cầu xác thực.",
        )

    payload = ApiErrorResponse(error=error)
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    issues = [
        ValidationIssue(
            field=".".join(str(part) for part in error["loc"]),
            code=str(error["type"]),
            message=str(error["msg"]),
        )
        for error in exc.errors()
    ]
    payload = ApiErrorResponse(
        error=ApiError(
            code="validation_error",
            message="Dữ liệu gửi lên không hợp lệ.",
            details=issues,
        )
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=payload.model_dump(mode="json", exclude_none=True),
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )

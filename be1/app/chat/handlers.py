"""Sanitized errors for user-owned chat endpoints."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.auth.schemas import ApiError, ApiErrorResponse

from .exceptions import (
    ChatRuntimeUnavailable,
    ChatServiceError,
    ChatSessionNotFound,
)


def install_chat_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ChatServiceError, chat_exception_handler)


async def chat_exception_handler(
    _request: Request,
    exc: ChatServiceError,
) -> JSONResponse:
    if isinstance(exc, ChatSessionNotFound):
        status_code = status.HTTP_404_NOT_FOUND
        error = ApiError(
            code="chat_session_not_found",
            message="Không tìm thấy cuộc trò chuyện.",
        )
    elif isinstance(exc, ChatRuntimeUnavailable):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        error = ApiError(
            code="chat_unavailable",
            message="Trợ lý đang tạm thời gián đoạn.",
        )
    else:
        status_code = status.HTTP_400_BAD_REQUEST
        error = ApiError(
            code="chat_request_failed",
            message="Không thể hoàn tất yêu cầu trò chuyện.",
        )

    payload = ApiErrorResponse(error=error)
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", exclude_none=True),
        headers={"Cache-Control": "no-store"},
    )

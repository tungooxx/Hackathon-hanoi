"""Authenticated CRUD and streaming routes for user-owned conversations."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Query, Response, status
from sse_starlette.sse import EventSourceResponse

from app.auth.dependencies import CurrentUser
from app.auth.schemas import ApiErrorResponse
from app.tracing import set_session
from app.turnlog import log_turn
from db.models import ChatSession

from .dependencies import (
    ChatGraphRuntimeDependency,
    ChatSessionServiceDependency,
)
from .schemas import (
    ChatMessageRequest,
    ChatSessionListResponse,
    ChatSessionResponse,
    CreateChatSessionRequest,
    UpdateChatSessionRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat/sessions", tags=["Chat sessions"])
guest_router = APIRouter(prefix="/chat/guest", tags=["Guest chat"])

CHAT_ERROR_RESPONSES = {
    401: {"model": ApiErrorResponse, "description": "Authentication required"},
    404: {"model": ApiErrorResponse, "description": "Chat session not found"},
    422: {"model": ApiErrorResponse, "description": "Invalid request"},
    503: {"model": ApiErrorResponse, "description": "Chat runtime unavailable"},
}
GUEST_CHAT_ERROR_RESPONSES = {
    422: {"model": ApiErrorResponse, "description": "Invalid request"},
    503: {"model": ApiErrorResponse, "description": "Chat runtime unavailable"},
}


@guest_router.post(
    "/messages",
    responses=GUEST_CHAT_ERROR_RESPONSES,
)
async def stream_guest_chat_message(
    payload: ChatMessageRequest,
    runtime: ChatGraphRuntimeDependency,
) -> EventSourceResponse:
    """Stream one independent turn without storing session metadata or state."""

    async def generate():
        try:
            async for event_payload in runtime.stream_guest(
                message=payload.message,
            ):
                if not event_payload["type"].startswith("_"):
                    yield _sse_event(event_payload)
        except Exception:
            logger.exception("Guest chat graph failed")
            yield _error_event()

    return EventSourceResponse(
        generate(),
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses=CHAT_ERROR_RESPONSES,
)
async def create_chat_session(
    payload: CreateChatSessionRequest,
    user: CurrentUser,
    service: ChatSessionServiceDependency,
) -> ChatSessionResponse:
    chat_session = await service.create(user.id, title=payload.title)
    return _response(chat_session)


@router.get(
    "",
    response_model=ChatSessionListResponse,
    responses=CHAT_ERROR_RESPONSES,
)
async def list_chat_sessions(
    user: CurrentUser,
    service: ChatSessionServiceDependency,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ChatSessionListResponse:
    sessions = await service.list_owned(
        user.id,
        limit=limit,
        offset=offset,
    )
    return ChatSessionListResponse(items=[_response(item) for item in sessions])


@router.get(
    "/{chat_session_id}",
    response_model=ChatSessionResponse,
    responses=CHAT_ERROR_RESPONSES,
)
async def get_chat_session(
    chat_session_id: uuid.UUID,
    user: CurrentUser,
    service: ChatSessionServiceDependency,
) -> ChatSessionResponse:
    return _response(await service.get_owned(chat_session_id, user.id))


@router.patch(
    "/{chat_session_id}",
    response_model=ChatSessionResponse,
    responses=CHAT_ERROR_RESPONSES,
)
async def update_chat_session(
    chat_session_id: uuid.UUID,
    payload: UpdateChatSessionRequest,
    user: CurrentUser,
    service: ChatSessionServiceDependency,
) -> ChatSessionResponse:
    chat_session = await service.update_title(
        chat_session_id,
        user.id,
        title=payload.title,
    )
    return _response(chat_session)


@router.delete(
    "/{chat_session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=CHAT_ERROR_RESPONSES,
)
async def delete_chat_session(
    chat_session_id: uuid.UUID,
    user: CurrentUser,
    service: ChatSessionServiceDependency,
    runtime: ChatGraphRuntimeDependency,
) -> Response:
    # Check ownership before touching an internal thread identifier.
    chat_session = await service.get_owned(chat_session_id, user.id)
    await runtime.delete_thread(str(chat_session.langgraph_thread_id))
    await service.delete_owned(chat_session_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{chat_session_id}/messages",
    responses=CHAT_ERROR_RESPONSES,
)
async def stream_chat_message(
    chat_session_id: uuid.UUID,
    payload: ChatMessageRequest,
    user: CurrentUser,
    service: ChatSessionServiceDependency,
    runtime: ChatGraphRuntimeDependency,
) -> EventSourceResponse:
    chat_session = await service.prepare_message(
        chat_session_id,
        user.id,
        message=payload.message,
    )
    public_session_id = str(chat_session.id)
    thread_id = str(chat_session.langgraph_thread_id)

    async def generate():
        set_session(public_session_id)
        events: list[dict] = []
        try:
            async for event_payload in runtime.stream(
                thread_id=thread_id,
                message=payload.message,
            ):
                events.append(event_payload)
                if not event_payload["type"].startswith("_"):
                    yield _sse_event(event_payload)
        except Exception:
            logger.exception(
                "Chat graph failed for session %s",
                public_session_id,
            )
            yield _error_event()
        finally:
            log_turn(public_session_id, payload.message, events)

    return EventSourceResponse(generate())


def _response(chat_session: ChatSession) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=chat_session.id,
        title=chat_session.title,
        created_at=chat_session.created_at,
        updated_at=chat_session.updated_at,
    )


def _sse_event(payload: dict) -> dict[str, str]:
    return {
        "event": payload["type"],
        "data": json.dumps(payload, ensure_ascii=False),
    }


def _error_event() -> dict[str, str]:
    return _sse_event(
        {
            "type": "error",
            "message": "Trợ lý đang tạm thời gián đoạn.",
        }
    )

"""Transactional user-owned chat-session workflows."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import utc_now
from app.repositories import ChatSessionRepository
from db.models import ChatSession

from .exceptions import ChatSessionNotFound

DEFAULT_CHAT_TITLE = "Cuộc trò chuyện mới"
AUTO_TITLE_MAX_LENGTH = 72


class ChatSessionService:
    """Manage conversations without accepting a client-supplied user ID."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.session = session
        self.clock = clock
        self.chat_sessions = ChatSessionRepository(session)

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        title: str | None = None,
    ) -> ChatSession:
        now = self.clock()
        async with self.session.begin():
            return await self.chat_sessions.create(
                user_id,
                title=title or DEFAULT_CHAT_TITLE,
                now=now,
            )

    async def list_owned(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> list[ChatSession]:
        async with self.session.begin():
            return await self.chat_sessions.list_owned(
                user_id,
                limit=limit,
                offset=offset,
            )

    async def get_owned(
        self,
        chat_session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSession:
        async with self.session.begin():
            chat_session = await self.chat_sessions.get_owned(
                chat_session_id,
                user_id,
            )
            return self._require(chat_session)

    async def update_title(
        self,
        chat_session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        title: str,
    ) -> ChatSession:
        async with self.session.begin():
            chat_session = self._require(
                await self.chat_sessions.get_owned(
                    chat_session_id,
                    user_id,
                    for_update=True,
                )
            )
            chat_session.title = title
            chat_session.updated_at = self.clock()
            await self.session.flush()
            return chat_session

    async def prepare_message(
        self,
        chat_session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        message: str,
    ) -> ChatSession:
        """Validate ownership and update title/activity before graph execution."""

        async with self.session.begin():
            chat_session = self._require(
                await self.chat_sessions.get_owned(
                    chat_session_id,
                    user_id,
                    for_update=True,
                )
            )
            if chat_session.title == DEFAULT_CHAT_TITLE:
                chat_session.title = _title_from_message(message)
            chat_session.updated_at = self.clock()
            await self.session.flush()
            return chat_session

    async def update_session_content(
        self,
        chat_session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        session_content: str,
    ) -> ChatSession:
        """Persist Markdown emitted by the history-control graph node."""

        async with self.session.begin():
            chat_session = self._require(
                await self.chat_sessions.get_owned(
                    chat_session_id,
                    user_id,
                    for_update=True,
                )
            )
            chat_session.session_content = session_content
            await self.session.flush()
            return chat_session

    async def delete_owned(
        self,
        chat_session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> uuid.UUID:
        async with self.session.begin():
            chat_session = self._require(
                await self.chat_sessions.get_owned(
                    chat_session_id,
                    user_id,
                    for_update=True,
                )
            )
            thread_id = chat_session.langgraph_thread_id
            await self.chat_sessions.delete(chat_session)
            return thread_id

    @staticmethod
    def _require(chat_session: ChatSession | None) -> ChatSession:
        if chat_session is None:
            # A single 404 prevents callers from discovering another user's IDs.
            raise ChatSessionNotFound("Chat session was not found")
        return chat_session


def _title_from_message(message: str) -> str:
    normalized = " ".join(message.split())
    if len(normalized) <= AUTO_TITLE_MAX_LENGTH:
        return normalized
    return normalized[: AUTO_TITLE_MAX_LENGTH - 1].rstrip() + "…"

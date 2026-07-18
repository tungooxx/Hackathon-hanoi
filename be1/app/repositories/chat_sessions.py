"""User-scoped chat-session persistence operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ChatSession


class ChatSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        title: str,
        now: datetime,
    ) -> ChatSession:
        chat_session = ChatSession(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title,
            langgraph_thread_id=uuid.uuid4(),
            created_at=now,
            updated_at=now,
        )
        self.session.add(chat_session)
        await self.session.flush()
        return chat_session

    async def list_owned(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> list[ChatSession]:
        statement = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .limit(limit)
            .offset(offset)
            .execution_options(populate_existing=True)
        )
        return list((await self.session.scalars(statement)).all())

    async def get_owned(
        self,
        chat_session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> ChatSession | None:
        statement = select(ChatSession).where(
            ChatSession.id == chat_session_id,
            ChatSession.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        statement = statement.execution_options(populate_existing=True)
        return await self.session.scalar(statement)

    async def delete(self, chat_session: ChatSession) -> None:
        await self.session.delete(chat_session)
        await self.session.flush()

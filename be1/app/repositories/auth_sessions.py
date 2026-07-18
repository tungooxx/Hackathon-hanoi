"""Authentication-session persistence operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuthSession


class AuthSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, auth_session: AuthSession) -> None:
        self.session.add(auth_session)

    async def get_by_id(
        self,
        session_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> AuthSession | None:
        statement = select(AuthSession).where(AuthSession.id == session_id)
        if for_update:
            statement = statement.with_for_update()
        statement = statement.execution_options(populate_existing=True)
        return await self.session.scalar(statement)

    async def revoke(
        self,
        auth_session: AuthSession,
        *,
        revoked_at: datetime,
    ) -> None:
        auth_session.revoked_at = revoked_at
        auth_session.updated_at = revoked_at
        await self.session.flush()

    async def rotate(
        self,
        auth_session: AuthSession,
        *,
        refresh_token_digest: str,
        expires_at: datetime,
        used_at: datetime,
    ) -> None:
        auth_session.refresh_token_digest = refresh_token_digest
        auth_session.expires_at = expires_at
        auth_session.last_used_at = used_at
        auth_session.updated_at = used_at
        await self.session.flush()

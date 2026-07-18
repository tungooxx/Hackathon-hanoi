"""User persistence operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        statement = (
            select(User)
            .where(User.id == user_id)
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(statement)

    async def get_by_phone(self, phone_e164: str) -> User | None:
        statement = (
            select(User)
            .where(User.phone_e164 == phone_e164)
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(statement)

    async def create(
        self,
        phone_e164: str,
        *,
        password_hash: str,
        now: datetime,
    ) -> User:
        user = User(
            phone_e164=phone_e164,
            password_hash=password_hash,
            is_active=True,
            last_login_at=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(user)
        await self.session.flush()
        return user

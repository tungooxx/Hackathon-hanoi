"""Failed-login persistence and rate-window queries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuthLoginAttempt


@dataclass(frozen=True)
class RateWindowStats:
    count: int
    oldest_at: datetime | None


class LoginAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_failure(
        self,
        phone_digest: str,
        *,
        request_ip_digest: str | None,
        created_at: datetime,
    ) -> None:
        self.session.add(
            AuthLoginAttempt(
                id=uuid.uuid4(),
                phone_digest=phone_digest,
                request_ip_digest=request_ip_digest,
                created_at=created_at,
            )
        )

    async def phone_window_stats(
        self,
        phone_digest: str,
        *,
        since: datetime,
    ) -> RateWindowStats:
        statement = select(
            func.count(AuthLoginAttempt.id),
            func.min(AuthLoginAttempt.created_at),
        ).where(
            AuthLoginAttempt.phone_digest == phone_digest,
            AuthLoginAttempt.created_at >= since,
        )
        count, oldest_at = (await self.session.execute(statement)).one()
        return RateWindowStats(count=int(count), oldest_at=oldest_at)

    async def ip_window_stats(
        self,
        request_ip_digest: str,
        *,
        since: datetime,
    ) -> RateWindowStats:
        statement = select(
            func.count(AuthLoginAttempt.id),
            func.min(AuthLoginAttempt.created_at),
        ).where(
            AuthLoginAttempt.request_ip_digest == request_ip_digest,
            AuthLoginAttempt.created_at >= since,
        )
        count, oldest_at = (await self.session.execute(statement)).one()
        return RateWindowStats(count=int(count), oldest_at=oldest_at)

    async def clear_phone_failures(self, phone_digest: str) -> None:
        await self.session.execute(
            delete(AuthLoginAttempt).where(
                AuthLoginAttempt.phone_digest == phone_digest
            )
        )

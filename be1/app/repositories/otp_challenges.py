"""OTP challenge persistence and rate-window queries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import OtpChallenge


@dataclass(frozen=True)
class RateWindowStats:
    count: int
    oldest_at: datetime | None


class OtpChallengeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, challenge: OtpChallenge) -> None:
        self.session.add(challenge)

    async def latest_for_phone(
        self,
        phone_e164: str,
    ) -> OtpChallenge | None:
        statement = (
            select(OtpChallenge)
            .where(OtpChallenge.phone_e164 == phone_e164)
            .order_by(OtpChallenge.created_at.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(statement)

    async def get_phone(self, challenge_id: uuid.UUID) -> str | None:
        statement = select(OtpChallenge.phone_e164).where(
            OtpChallenge.id == challenge_id
        )
        return await self.session.scalar(statement)

    async def phone_window_stats(
        self,
        phone_e164: str,
        *,
        since: datetime,
    ) -> RateWindowStats:
        statement = select(
            func.count(OtpChallenge.id),
            func.min(OtpChallenge.created_at),
        ).where(
            OtpChallenge.phone_e164 == phone_e164,
            OtpChallenge.created_at >= since,
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
            func.count(OtpChallenge.id),
            func.min(OtpChallenge.created_at),
        ).where(
            OtpChallenge.request_ip_digest == request_ip_digest,
            OtpChallenge.created_at >= since,
        )
        count, oldest_at = (await self.session.execute(statement)).one()
        return RateWindowStats(count=int(count), oldest_at=oldest_at)

    async def invalidate_active_for_phone(
        self,
        phone_e164: str,
        *,
        consumed_at: datetime,
    ) -> None:
        statement = (
            update(OtpChallenge)
            .where(
                OtpChallenge.phone_e164 == phone_e164,
                OtpChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=consumed_at, updated_at=consumed_at)
        )
        await self.session.execute(statement)

    async def get_by_id(
        self,
        challenge_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> OtpChallenge | None:
        statement = select(OtpChallenge).where(OtpChallenge.id == challenge_id)
        if for_update:
            statement = statement.with_for_update()
        statement = statement.execution_options(populate_existing=True)
        return await self.session.scalar(statement)

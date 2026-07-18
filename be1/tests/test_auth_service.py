from __future__ import annotations

import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.auth.exceptions import (
    InvalidOtpCode,
    OtpChallengeConsumed,
    OtpChallengeExpired,
    OtpCooldown,
    OtpDeliveryError,
    OtpRateLimited,
    RevokedAuthSession,
)
from app.auth.security import client_ip_digest
from app.auth.service import AuthService
from app.config import OTP_IP_RATE_LIMIT_COUNT
from db.models import AuthSession, OtpChallenge, User

BE1_ROOT = Path(__file__).resolve().parent.parent


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: int) -> None:
        self.current += timedelta(**kwargs)


class CaptureOtpProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.deliveries: list[tuple[str, str, int]] = []

    async def send_otp(
        self,
        phone_e164: str,
        code: str,
        *,
        expires_in_seconds: int,
    ) -> None:
        if self.fail:
            raise OtpDeliveryError("simulated delivery failure")
        self.deliveries.append((phone_e164, code, expires_in_seconds))


def test_database_url() -> str:
    configured = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if configured:
        return configured

    values = dotenv_values(BE1_ROOT / "docker" / ".env.docker")
    password = values.get("POSTGRES_PASSWORD")
    if not password:
        raise unittest.SkipTest(
            "Set TEST_DATABASE_URL or docker/.env.docker to run DB tests"
        )
    user = quote(values.get("POSTGRES_USER") or "be1", safe="")
    database = quote(values.get("POSTGRES_DB") or "be1", safe="")
    port = values.get("POSTGRES_PORT") or "5432"
    return (
        f"postgresql+asyncpg://{user}:{quote(password, safe='')}"
        f"@127.0.0.1:{port}/{database}"
    )


class AuthServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine(test_database_url())
        self.connection = await self.engine.connect()
        self.transaction = await self.connection.begin()
        factory = async_sessionmaker(
            bind=self.connection,
            class_=AsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        self.session = factory()
        self.clock = MutableClock(datetime.now(UTC).replace(microsecond=0))
        self.provider = CaptureOtpProvider()
        self.service = AuthService(
            self.session,
            otp_provider=self.provider,
            clock=self.clock,
        )

    async def asyncTearDown(self) -> None:
        await self.session.close()
        if self.transaction.is_active:
            await self.transaction.rollback()
        await self.connection.close()
        await self.engine.dispose()

    async def test_request_verify_and_authenticate(self) -> None:
        request = await self.service.request_otp(
            "0901234567",
            client_ip="127.0.0.1",
        )
        phone, code, _ = self.provider.deliveries[-1]
        self.assertEqual(phone, "+84901234567")

        async with self.session.begin():
            challenge = await self.session.get(
                OtpChallenge,
                request.challenge_id,
            )
            assert challenge is not None
            self.assertNotEqual(challenge.code_digest, code)
            self.assertNotEqual(
                challenge.request_ip_digest,
                "127.0.0.1",
            )

        authenticated = await self.service.verify_otp(
            request.challenge_id,
            code,
        )
        self.assertTrue(authenticated.is_new_user)
        identity = await self.service.authenticate_access_token(
            authenticated.tokens.access_token
        )
        self.assertEqual(identity.id, authenticated.user.id)

        with self.assertRaises(OtpChallengeConsumed):
            await self.service.verify_otp(request.challenge_id, code)

        async with self.session.begin():
            users = list((await self.session.scalars(select(User))).all())
            sessions = list((await self.session.scalars(select(AuthSession))).all())
            self.assertEqual(len(users), 1)
            self.assertEqual(len(sessions), 1)
            self.assertNotEqual(
                sessions[0].refresh_token_digest,
                authenticated.tokens.refresh_token,
            )

    async def test_wrong_codes_persist_attempts_and_consume_challenge(self) -> None:
        request = await self.service.request_otp("0901234567")

        for expected_remaining in (4, 3, 2, 1, 0):
            with self.assertRaises(InvalidOtpCode) as caught:
                await self.service.verify_otp(
                    request.challenge_id,
                    "111111",
                )
            self.assertEqual(
                caught.exception.attempts_remaining,
                expected_remaining,
            )

        with self.assertRaises(OtpChallengeConsumed):
            await self.service.verify_otp(
                request.challenge_id,
                self.provider.deliveries[-1][1],
            )

    async def test_expired_challenge_is_consumed(self) -> None:
        request = await self.service.request_otp("0901234567")
        code = self.provider.deliveries[-1][1]
        self.clock.advance(minutes=6)

        with self.assertRaises(OtpChallengeExpired):
            await self.service.verify_otp(request.challenge_id, code)
        with self.assertRaises(OtpChallengeConsumed):
            await self.service.verify_otp(request.challenge_id, code)

    async def test_refresh_rotation_detects_replay_and_revokes_session(
        self,
    ) -> None:
        request = await self.service.request_otp("0901234567")
        authenticated = await self.service.verify_otp(
            request.challenge_id,
            self.provider.deliveries[-1][1],
        )
        original_refresh = authenticated.tokens.refresh_token
        rotated = await self.service.refresh(original_refresh)

        await self.service.authenticate_access_token(rotated.tokens.access_token)
        with self.assertRaises(RevokedAuthSession):
            await self.service.refresh(original_refresh)
        with self.assertRaises(RevokedAuthSession):
            await self.service.authenticate_access_token(rotated.tokens.access_token)

    async def test_logout_revokes_access_and_is_idempotent(self) -> None:
        request = await self.service.request_otp("0901234567")
        authenticated = await self.service.verify_otp(
            request.challenge_id,
            self.provider.deliveries[-1][1],
        )

        self.assertTrue(
            await self.service.revoke_refresh_token(authenticated.tokens.refresh_token)
        )
        self.assertTrue(
            await self.service.revoke_refresh_token(authenticated.tokens.refresh_token)
        )
        with self.assertRaises(RevokedAuthSession):
            await self.service.authenticate_access_token(
                authenticated.tokens.access_token
            )

    async def test_cooldown_and_phone_window_rate_limit(self) -> None:
        await self.service.request_otp("0901234567")
        with self.assertRaises(OtpCooldown):
            await self.service.request_otp("0901234567")

        for _ in range(4):
            self.clock.advance(seconds=61)
            await self.service.request_otp("0901234567")

        self.clock.advance(seconds=61)
        with self.assertRaises(OtpRateLimited):
            await self.service.request_otp("0901234567")

    async def test_resend_invalidates_the_previous_challenge(self) -> None:
        first = await self.service.request_otp("0901234567")
        first_code = self.provider.deliveries[-1][1]
        self.clock.advance(seconds=61)
        second = await self.service.request_otp("0901234567")
        second_code = self.provider.deliveries[-1][1]

        with self.assertRaises(OtpChallengeConsumed):
            await self.service.verify_otp(first.challenge_id, first_code)
        authenticated = await self.service.verify_otp(
            second.challenge_id,
            second_code,
        )
        self.assertTrue(authenticated.is_new_user)

    async def test_ip_window_rate_limit_uses_only_digest(self) -> None:
        ip_address = "10.0.0.8"
        ip_digest = client_ip_digest(ip_address)
        async with self.session.begin():
            self.session.add_all(
                [
                    OtpChallenge(
                        id=uuid.uuid4(),
                        phone_e164="+84999999999",
                        request_ip_digest=ip_digest,
                        code_digest="0" * 64,
                        expires_at=self.clock.current + timedelta(minutes=5),
                        attempts_remaining=5,
                        resend_available_at=self.clock.current,
                        consumed_at=self.clock.current,
                        created_at=self.clock.current,
                        updated_at=self.clock.current,
                    )
                    for _ in range(OTP_IP_RATE_LIMIT_COUNT)
                ]
            )

        with self.assertRaises(OtpRateLimited):
            await self.service.request_otp(
                "0912345678",
                client_ip=ip_address,
            )

    async def test_delivery_failure_consumes_challenge_without_cooldown(
        self,
    ) -> None:
        failing_provider = CaptureOtpProvider(fail=True)
        service = AuthService(
            self.session,
            otp_provider=failing_provider,
            clock=self.clock,
        )
        with self.assertRaises(OtpDeliveryError):
            await service.request_otp("0901234567")

        async with self.session.begin():
            challenge = await self.session.scalar(
                select(OtpChallenge).order_by(OtpChallenge.created_at.desc())
            )
            assert challenge is not None
            self.assertIsNotNone(challenge.consumed_at)
            self.assertEqual(
                challenge.resend_available_at,
                challenge.consumed_at,
            )


if __name__ == "__main__":
    unittest.main()

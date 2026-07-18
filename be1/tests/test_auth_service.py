from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.auth.exceptions import (
    InvalidCredentials,
    LoginRateLimited,
    PhoneAlreadyRegistered,
    RevokedAuthSession,
    WeakPassword,
)
from app.auth.security import phone_login_digest, verify_password
from app.auth.service import AuthService
from app.config import LOGIN_PHONE_RATE_LIMIT_COUNT
from db.models import AuthLoginAttempt, AuthSession, User

BE1_ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "correct-password-123"


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: int) -> None:
        self.current += timedelta(**kwargs)


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
        self.service = AuthService(self.session, clock=self.clock)

    async def asyncTearDown(self) -> None:
        await self.session.close()
        if self.transaction.is_active:
            await self.transaction.rollback()
        await self.connection.close()
        await self.engine.dispose()

    async def test_register_hashes_password_and_authenticates(self) -> None:
        registered = await self.service.register("0901234567", PASSWORD)

        self.assertTrue(registered.is_new_user)
        identity = await self.service.authenticate_access_token(
            registered.tokens.access_token
        )
        self.assertEqual(identity.id, registered.user.id)

        async with self.session.begin():
            user = await self.session.get(User, registered.user.id)
            assert user is not None
            self.assertNotEqual(user.password_hash, PASSWORD)
            self.assertTrue(verify_password(PASSWORD, user.password_hash))
            self.assertIsNotNone(user.last_login_at)

            sessions = list((await self.session.scalars(select(AuthSession))).all())
            self.assertEqual(len(sessions), 1)
            self.assertNotEqual(
                sessions[0].refresh_token_digest,
                registered.tokens.refresh_token,
            )

    async def test_registration_rejects_duplicate_and_legacy_user(self) -> None:
        await self.service.register("0901234567", PASSWORD)
        with self.assertRaises(PhoneAlreadyRegistered):
            await self.service.register("0901234567", PASSWORD)

        async with self.session.begin():
            self.session.add(
                User(
                    phone_e164="+84987654321",
                    password_hash=None,
                    is_active=True,
                    created_at=self.clock.current,
                    updated_at=self.clock.current,
                )
            )

        with self.assertRaises(PhoneAlreadyRegistered):
            await self.service.register("0987654321", PASSWORD)

    async def test_registration_enforces_password_length(self) -> None:
        with self.assertRaises(WeakPassword):
            await self.service.register("0901234567", "short")

    async def test_login_succeeds_and_clears_previous_failures(self) -> None:
        registered = await self.service.register("0901234567", PASSWORD)
        await self.service.revoke_refresh_token(registered.tokens.refresh_token)

        with self.assertRaises(InvalidCredentials):
            await self.service.login(
                "0901234567",
                "incorrect-password",
                client_ip="127.0.0.1",
            )

        logged_in = await self.service.login(
            "0901234567",
            PASSWORD,
            client_ip="127.0.0.1",
        )
        self.assertFalse(logged_in.is_new_user)

        async with self.session.begin():
            attempts = await self.session.scalar(
                select(func.count(AuthLoginAttempt.id)).where(
                    AuthLoginAttempt.phone_digest == phone_login_digest("+84901234567")
                )
            )
            self.assertEqual(attempts, 0)

    async def test_invalid_credentials_are_persisted_and_rate_limited(
        self,
    ) -> None:
        await self.service.register("0901234567", PASSWORD)

        for _ in range(LOGIN_PHONE_RATE_LIMIT_COUNT):
            with self.assertRaises(InvalidCredentials):
                await self.service.login(
                    "0901234567",
                    "incorrect-password",
                    client_ip="127.0.0.1",
                )

        with self.assertRaises(LoginRateLimited) as caught:
            await self.service.login(
                "0901234567",
                PASSWORD,
                client_ip="127.0.0.1",
            )
        self.assertGreater(caught.exception.retry_after_seconds, 0)

        self.clock.advance(minutes=16)
        logged_in = await self.service.login(
            "0901234567",
            PASSWORD,
            client_ip="127.0.0.1",
        )
        self.assertEqual(logged_in.user.id, (await self._only_user()).id)

    async def test_unknown_phone_uses_same_public_failure(self) -> None:
        with self.assertRaises(InvalidCredentials):
            await self.service.login(
                "0901234567",
                PASSWORD,
                client_ip="127.0.0.1",
            )

        async with self.session.begin():
            attempts = await self.session.scalar(
                select(func.count(AuthLoginAttempt.id))
            )
            self.assertEqual(attempts, 1)

    async def test_inactive_user_cannot_login(self) -> None:
        await self.service.register("0901234567", PASSWORD)
        async with self.session.begin():
            user = await self._only_user()
            user.is_active = False

        with self.assertRaises(InvalidCredentials):
            await self.service.login("0901234567", PASSWORD)

    async def test_refresh_rotation_detects_replay_and_revokes_session(
        self,
    ) -> None:
        registered = await self.service.register("0901234567", PASSWORD)
        original_refresh = registered.tokens.refresh_token
        rotated = await self.service.refresh(original_refresh)

        await self.service.authenticate_access_token(rotated.tokens.access_token)
        with self.assertRaises(RevokedAuthSession):
            await self.service.refresh(original_refresh)
        with self.assertRaises(RevokedAuthSession):
            await self.service.authenticate_access_token(rotated.tokens.access_token)

    async def test_logout_revokes_access_and_is_idempotent(self) -> None:
        registered = await self.service.register("0901234567", PASSWORD)

        self.assertTrue(
            await self.service.revoke_refresh_token(registered.tokens.refresh_token)
        )
        self.assertTrue(
            await self.service.revoke_refresh_token(registered.tokens.refresh_token)
        )
        with self.assertRaises(RevokedAuthSession):
            await self.service.authenticate_access_token(registered.tokens.access_token)

    async def _only_user(self) -> User:
        user = await self.session.scalar(select(User))
        assert user is not None
        return user


if __name__ == "__main__":
    unittest.main()

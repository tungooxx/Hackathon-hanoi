from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import dotenv_values
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.auth.dependencies import get_auth_service
from app.auth.service import AuthService
from app.config import (
    AUTH_ACCESS_COOKIE_NAME,
    AUTH_REFRESH_COOKIE_NAME,
    FRONTEND_ORIGINS,
    LOGIN_PHONE_RATE_LIMIT_COUNT,
)
from app.main import app

BE1_ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "correct-password-123"


def test_database_url() -> str:
    configured = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if configured:
        return configured

    values = dotenv_values(BE1_ROOT / "docker" / ".env.docker")
    password = values.get("POSTGRES_PASSWORD")
    if not password:
        raise unittest.SkipTest(
            "Set TEST_DATABASE_URL or docker/.env.docker to run API tests"
        )
    user = quote(values.get("POSTGRES_USER") or "be1", safe="")
    database = quote(values.get("POSTGRES_DB") or "be1", safe="")
    port = values.get("POSTGRES_PORT") or "5432"
    return (
        f"postgresql+asyncpg://{user}:{quote(password, safe='')}"
        f"@127.0.0.1:{port}/{database}"
    )


class AuthApiTests(unittest.IsolatedAsyncioTestCase):
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
        self.service = AuthService(
            self.session,
            clock=lambda: datetime.now(UTC),
        )

        def override_auth_service() -> AuthService:
            return self.service

        app.dependency_overrides[get_auth_service] = override_auth_service
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=app,
                client=("127.0.0.1", 43123),
            ),
            base_url="http://localhost",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.pop(get_auth_service, None)
        await self.session.close()
        if self.transaction.is_active:
            await self.transaction.rollback()
        await self.connection.close()
        await self.engine.dispose()

    async def test_complete_register_cookie_login_flow(self) -> None:
        registered = await self._register()
        self.assertEqual(registered.status_code, 201)
        registered_body = registered.json()
        self.assertNotIn("access_token", registered_body)
        self.assertNotIn("refresh_token", registered_body)
        self.assertTrue(registered_body["is_new_user"])
        self.assertEqual(registered.headers["cache-control"], "no-store")

        cookie_headers = registered.headers.get_list("set-cookie")
        access_header = next(
            value
            for value in cookie_headers
            if value.startswith(f"{AUTH_ACCESS_COOKIE_NAME}=")
        )
        refresh_header = next(
            value
            for value in cookie_headers
            if value.startswith(f"{AUTH_REFRESH_COOKIE_NAME}=")
        )
        self.assertIn("HttpOnly", access_header)
        self.assertIn("SameSite=lax", access_header)
        self.assertIn("Path=/", access_header)
        self.assertNotIn("Secure", access_header)
        self.assertIn("HttpOnly", refresh_header)
        self.assertIn("SameSite=lax", refresh_header)
        self.assertIn("Path=/auth", refresh_header)

        me = await self.client.get("/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["phone_e164"], "+84901234567")
        self.assertEqual(me.json()["id"], registered_body["user"]["id"])

        old_refresh = self.client.cookies.get(AUTH_REFRESH_COOKIE_NAME)
        refreshed = await self.client.post("/auth/refresh")
        self.assertEqual(refreshed.status_code, 200)
        self.assertNotIn("refresh_token", refreshed.json())
        self.assertNotEqual(
            self.client.cookies.get(AUTH_REFRESH_COOKIE_NAME),
            old_refresh,
        )

        logged_out = await self.client.post("/auth/logout")
        self.assertEqual(logged_out.status_code, 204)
        self.assertIsNone(self.client.cookies.get(AUTH_ACCESS_COOKIE_NAME))
        self.assertIsNone(self.client.cookies.get(AUTH_REFRESH_COOKIE_NAME))
        self.assertEqual((await self.client.get("/auth/me")).status_code, 401)

        logged_in = await self.client.post(
            "/auth/login",
            json={"phone": "0901234567", "password": PASSWORD},
        )
        self.assertEqual(logged_in.status_code, 200)
        self.assertFalse(logged_in.json()["is_new_user"])
        self.assertEqual(
            logged_in.json()["user"]["id"],
            registered_body["user"]["id"],
        )

    async def test_registration_and_login_errors_are_sanitized(self) -> None:
        mismatch = await self.client.post(
            "/auth/register",
            json={
                "phone": "0901234567",
                "password": PASSWORD,
                "password_confirmation": "different-password",
                "unexpected": "secret",
            },
        )
        self.assertEqual(mismatch.status_code, 422)
        self.assertEqual(
            mismatch.json()["error"]["code"],
            "validation_error",
        )
        self.assertNotIn("secret", mismatch.text)
        self.assertNotIn(PASSWORD, mismatch.text)

        invalid_phone = await self.client.post(
            "/auth/register",
            json={
                "phone": "12345",
                "password": PASSWORD,
                "password_confirmation": PASSWORD,
            },
        )
        self.assertEqual(invalid_phone.status_code, 422)
        self.assertEqual(
            invalid_phone.json()["error"]["code"],
            "invalid_phone",
        )
        self.assertNotIn("12345", invalid_phone.text)

        self.assertEqual((await self._register()).status_code, 201)
        duplicate = await self._register()
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            duplicate.json()["error"]["code"],
            "phone_already_registered",
        )

        bad_login = await self.client.post(
            "/auth/login",
            json={
                "phone": "0901234567",
                "password": "incorrect-password",
            },
        )
        self.assertEqual(bad_login.status_code, 401)
        self.assertEqual(
            bad_login.json()["error"]["code"],
            "invalid_credentials",
        )
        self.assertNotIn("incorrect-password", bad_login.text)

    async def test_failed_login_rate_limit_and_cors_headers(self) -> None:
        self.assertEqual((await self._register()).status_code, 201)

        for _ in range(LOGIN_PHONE_RATE_LIMIT_COUNT):
            response = await self.client.post(
                "/auth/login",
                json={
                    "phone": "0901234567",
                    "password": "incorrect-password",
                },
            )
            self.assertEqual(response.status_code, 401)

        limited = await self.client.post(
            "/auth/login",
            json={"phone": "0901234567", "password": PASSWORD},
            headers={"Origin": FRONTEND_ORIGINS[0]},
        )
        self.assertEqual(limited.status_code, 429)
        self.assertGreater(int(limited.headers["retry-after"]), 0)
        self.assertEqual(
            limited.headers["access-control-allow-origin"],
            FRONTEND_ORIGINS[0],
        )
        self.assertIn(
            "Retry-After",
            limited.headers["access-control-expose-headers"],
        )

    async def test_missing_refresh_cors_and_removed_otp_routes(self) -> None:
        missing = await self.client.post("/auth/refresh")
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(
            missing.json()["error"]["code"],
            "unauthorized",
        )

        self.assertEqual(
            (
                await self.client.post(
                    "/auth/otp/request",
                    json={"phone": "0901234567"},
                )
            ).status_code,
            404,
        )

        preflight = await self.client.options(
            "/auth/me",
            headers={
                "Origin": FRONTEND_ORIGINS[0],
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(
            preflight.headers["access-control-allow-origin"],
            FRONTEND_ORIGINS[0],
        )
        self.assertEqual(
            preflight.headers["access-control-allow-credentials"],
            "true",
        )

        rejected = await self.client.options(
            "/auth/me",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertNotIn(
            "access-control-allow-origin",
            rejected.headers,
        )

    async def _register(self) -> httpx.Response:
        return await self.client.post(
            "/auth/register",
            json={
                "phone": "090 123 4567",
                "password": PASSWORD,
                "password_confirmation": PASSWORD,
            },
        )


if __name__ == "__main__":
    unittest.main()

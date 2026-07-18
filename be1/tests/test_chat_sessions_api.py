from __future__ import annotations

import os
import unittest
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import dotenv_values
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.auth.dependencies import get_auth_service
from app.auth.service import AuthService
from app.chat.dependencies import (
    get_chat_graph_runtime,
    get_chat_session_service,
)
from app.chat.service import ChatSessionService
from app.main import app
from db import get_db_session
from db.models import ChatSession

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


class FakeChatRuntime:
    def __init__(self) -> None:
        self.deleted_threads: list[str] = []
        self.stream_calls: list[tuple[str, str]] = []
        self.guest_stream_calls: list[str] = []

    async def delete_thread(self, thread_id: str) -> None:
        self.deleted_threads.append(thread_id)

    async def stream(
        self,
        *,
        thread_id: str,
        message: str,
    ) -> AsyncIterator[dict]:
        self.stream_calls.append((thread_id, message))
        yield {"type": "text_chunk", "content": "Đã nhận"}
        yield {"type": "done", "turn_type": "off_topic"}

    async def stream_guest(
        self,
        *,
        message: str,
    ) -> AsyncIterator[dict]:
        self.guest_stream_calls.append(message)
        yield {"type": "text_chunk", "content": "Đã nhận"}
        yield {"type": "done", "turn_type": "off_topic"}


class ChatSessionApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        suffix = uuid.uuid4().int % 10_000_000
        self.owner_phone = f"090{suffix:07d}"
        self.other_phone = f"091{(suffix + 1) % 10_000_000:07d}"
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
        self.auth_service = AuthService(
            self.session,
            clock=lambda: datetime.now(UTC),
        )
        self.chat_service = ChatSessionService(
            self.session,
            clock=lambda: datetime.now(UTC),
        )
        self.runtime = FakeChatRuntime()

        async def override_db_session() -> AsyncIterator[AsyncSession]:
            yield self.session

        def override_auth_service() -> AuthService:
            return self.auth_service

        def override_chat_service() -> ChatSessionService:
            return self.chat_service

        def override_chat_runtime() -> FakeChatRuntime:
            return self.runtime

        app.dependency_overrides[get_db_session] = override_db_session
        app.dependency_overrides[get_auth_service] = override_auth_service
        app.dependency_overrides[get_chat_session_service] = override_chat_service
        app.dependency_overrides[get_chat_graph_runtime] = override_chat_runtime

        transport = httpx.ASGITransport(
            app=app,
            client=("127.0.0.1", 43124),
        )
        self.anonymous = httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
        )
        self.owner = httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
        )
        self.other_user = httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
        )

    async def asyncTearDown(self) -> None:
        await self.anonymous.aclose()
        await self.owner.aclose()
        await self.other_user.aclose()
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_auth_service, None)
        app.dependency_overrides.pop(get_chat_session_service, None)
        app.dependency_overrides.pop(get_chat_graph_runtime, None)
        await self.session.close()
        if self.transaction.is_active:
            await self.transaction.rollback()
        await self.connection.close()
        await self.engine.dispose()

    async def test_crud_requires_auth_and_never_exposes_internal_thread(self) -> None:
        unauthenticated = await self.anonymous.post(
            "/chat/sessions",
            json={},
        )
        self.assertEqual(unauthenticated.status_code, 401)

        await self._register(self.owner, self.owner_phone)
        created = await self.owner.post(
            "/chat/sessions",
            json={"title": "Máy lạnh phòng ngủ"},
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertEqual(body["title"], "Máy lạnh phòng ngủ")
        self.assertNotIn("user_id", body)
        self.assertNotIn("langgraph_thread_id", body)
        session_id = body["id"]

        listed = await self.owner.get("/chat/sessions")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            [item["id"] for item in listed.json()["items"]],
            [session_id],
        )

        renamed = await self.owner.patch(
            f"/chat/sessions/{session_id}",
            json={"title": "Đã đổi tên"},
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["title"], "Đã đổi tên")

        deleted = await self.owner.delete(f"/chat/sessions/{session_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(len(self.runtime.deleted_threads), 1)
        self.assertNotEqual(self.runtime.deleted_threads[0], session_id)
        uuid.UUID(self.runtime.deleted_threads[0])
        self.assertEqual(
            (await self.owner.get(f"/chat/sessions/{session_id}")).status_code,
            404,
        )

    async def test_guest_chat_is_stateless_and_creates_no_session(self) -> None:
        async with self.session.begin():
            before = await self.session.scalar(
                select(func.count(ChatSession.id))
            )

        first = await self.anonymous.post(
            "/chat/guest/messages",
            json={"message": "Tư vấn máy lạnh"},
        )
        second = await self.anonymous.post(
            "/chat/guest/messages",
            json={"message": "Ngân sách 10 triệu"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertIn('"type": "done"', first.text)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            self.runtime.guest_stream_calls,
            ["Tư vấn máy lạnh", "Ngân sách 10 triệu"],
        )
        self.assertEqual(self.runtime.stream_calls, [])

        async with self.session.begin():
            after = await self.session.scalar(
                select(func.count(ChatSession.id))
            )
        self.assertEqual(after, before)

        forged = await self.anonymous.post(
            "/chat/guest/messages",
            json={
                "message": "Không được nhận ID từ client",
                "session_id": "forged",
            },
        )
        self.assertEqual(forged.status_code, 422)

    async def test_every_operation_enforces_cross_user_ownership(self) -> None:
        await self._register(self.owner, self.owner_phone)
        created = await self.owner.post("/chat/sessions", json={})
        self.assertEqual(created.status_code, 201)
        session_id = created.json()["id"]

        await self._register(self.other_user, self.other_phone)
        self.assertEqual(
            (await self.other_user.get("/chat/sessions")).json()["items"],
            [],
        )

        requests = [
            self.other_user.get(f"/chat/sessions/{session_id}"),
            self.other_user.patch(
                f"/chat/sessions/{session_id}",
                json={"title": "Chiếm quyền"},
            ),
            self.other_user.delete(f"/chat/sessions/{session_id}"),
            self.other_user.post(
                f"/chat/sessions/{session_id}/messages",
                json={"message": "Dùng phiên người khác"},
            ),
        ]
        for response in [await request for request in requests]:
            self.assertEqual(response.status_code, 404)
            self.assertEqual(
                response.json()["error"]["code"],
                "chat_session_not_found",
            )
        self.assertEqual(self.runtime.deleted_threads, [])
        self.assertEqual(self.runtime.stream_calls, [])

        owner_can_still_read = await self.owner.get(
            f"/chat/sessions/{session_id}"
        )
        self.assertEqual(owner_can_still_read.status_code, 200)

    async def test_stream_uses_one_private_thread_and_auto_titles_session(self) -> None:
        await self._register(self.owner, self.owner_phone)
        created = await self.owner.post("/chat/sessions", json={})
        session_id = created.json()["id"]

        first = await self.owner.post(
            f"/chat/sessions/{session_id}/messages",
            json={"message": "Tư vấn máy lạnh cho phòng 20 mét vuông"},
        )
        second = await self.owner.post(
            f"/chat/sessions/{session_id}/messages",
            json={"message": "Ngân sách dưới 12 triệu"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertIn('"type": "done"', first.text)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(self.runtime.stream_calls), 2)

        first_thread, first_message = self.runtime.stream_calls[0]
        second_thread, _ = self.runtime.stream_calls[1]
        self.assertEqual(first_thread, second_thread)
        self.assertNotEqual(first_thread, session_id)
        self.assertEqual(
            first_message,
            "Tư vấn máy lạnh cho phòng 20 mét vuông",
        )

        refreshed = await self.owner.get(f"/chat/sessions/{session_id}")
        self.assertEqual(
            refreshed.json()["title"],
            "Tư vấn máy lạnh cho phòng 20 mét vuông",
        )

    async def test_client_cannot_supply_identity_or_empty_content(self) -> None:
        await self._register(self.owner, self.owner_phone)
        user_id = (await self.owner.get("/auth/me")).json()["id"]

        forged = await self.owner.post(
            "/chat/sessions",
            json={"title": "Test", "user_id": user_id},
        )
        self.assertEqual(forged.status_code, 422)

        blank_title = await self.owner.post(
            "/chat/sessions",
            json={"title": "   "},
        )
        self.assertEqual(blank_title.status_code, 422)

        created = await self.owner.post("/chat/sessions", json={})
        blank_message = await self.owner.post(
            f"/chat/sessions/{created.json()['id']}/messages",
            json={"message": "   "},
        )
        self.assertEqual(blank_message.status_code, 422)

    async def _register(
        self,
        client: httpx.AsyncClient,
        phone: str,
    ) -> None:
        response = await client.post(
            "/auth/register",
            json={
                "phone": phone,
                "password": PASSWORD,
                "password_confirmation": PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)


if __name__ == "__main__":
    unittest.main()

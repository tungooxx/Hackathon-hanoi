"""Application-lifetime PostgreSQL LangGraph checkpoint runtime."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import (
    LANGGRAPH_DATABASE_URL,
    LANGGRAPH_POOL_MAX_SIZE,
    LANGGRAPH_POOL_MIN_SIZE,
)
from app.graph import build_graph

from .exceptions import ChatRuntimeUnavailable


class ChatGraphRuntime:
    """Own the checkpointer pool and compiled graph for one app process."""

    def __init__(self) -> None:
        self._pool: AsyncConnectionPool | None = None
        self._checkpointer: AsyncPostgresSaver | None = None
        self._graph: Any | None = None
        self._guest_graph: Any | None = None
        self._lifecycle_lock = asyncio.Lock()

    @property
    def is_started(self) -> bool:
        return self._graph is not None

    async def start(self) -> ChatGraphRuntime:
        if self.is_started:
            return self
        async with self._lifecycle_lock:
            if self.is_started:
                return self
            pool = AsyncConnectionPool(
                LANGGRAPH_DATABASE_URL,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                },
                min_size=LANGGRAPH_POOL_MIN_SIZE,
                max_size=LANGGRAPH_POOL_MAX_SIZE,
                open=False,
                name="langgraph-checkpoints",
            )
            try:
                await pool.open()
                await pool.wait()
                checkpointer = AsyncPostgresSaver(
                    pool,
                    serde=JsonPlusSerializer(
                        allowed_msgpack_modules=None,
                    ),
                )
                await checkpointer.setup()
                graph = build_graph(checkpointer=checkpointer)
                guest_graph = build_graph(checkpointer=None)
            except Exception:
                await pool.close()
                raise
            self._pool = pool
            self._checkpointer = checkpointer
            self._graph = graph
            self._guest_graph = guest_graph
        return self

    async def close(self) -> None:
        async with self._lifecycle_lock:
            pool = self._pool
            self._graph = None
            self._guest_graph = None
            self._checkpointer = None
            self._pool = None
            if pool is not None:
                await pool.close()

    async def stream(
        self,
        *,
        thread_id: str,
        message: str,
    ) -> AsyncIterator[dict[str, Any]]:
        graph = self._require_graph()
        config = {"configurable": {"thread_id": thread_id}}
        async for payload in graph.astream(
            {"user_input": message},
            config,
            stream_mode="custom",
        ):
            yield payload

    async def stream_guest(
        self,
        *,
        message: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run one stateless turn without a session or checkpoint."""

        graph = self._guest_graph
        if graph is None:
            raise ChatRuntimeUnavailable("Guest chat graph is not running")
        async for payload in graph.astream(
            {"user_input": message},
            stream_mode="custom",
        ):
            yield payload

    async def delete_thread(self, thread_id: str) -> None:
        checkpointer = self._checkpointer
        if checkpointer is None:
            raise ChatRuntimeUnavailable("Chat graph is not running")
        await checkpointer.adelete_thread(thread_id)

    def _require_graph(self) -> Any:
        if self._graph is None:
            raise ChatRuntimeUnavailable("Chat graph is not running")
        return self._graph

    async def __aenter__(self) -> ChatGraphRuntime:
        return await self.start()

    async def __aexit__(self, *_args: object) -> None:
        await self.close()


chat_graph_runtime = ChatGraphRuntime()

"""Shared asynchronous PostgreSQL engine and request-scoped sessions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import (
    DATABASE_ECHO,
    DATABASE_MAX_OVERFLOW,
    DATABASE_POOL_RECYCLE_SECONDS,
    DATABASE_POOL_SIZE,
    DATABASE_URL,
)


class PostgresDatabase:
    """Own the SQLAlchemy connection pool for the application lifespan."""

    def __init__(
        self,
        url: str,
        *,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_recycle: int = 1800,
    ) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url,
            echo=echo,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            autoflush=False,
            expire_on_commit=False,
        )
        self._started = False
        self._lifecycle_lock = asyncio.Lock()

    @property
    def is_started(self) -> bool:
        return self._started

    async def start(self) -> PostgresDatabase:
        """Open and validate one pooled connection, failing fast on bad config."""

        if self._started:
            return self
        async with self._lifecycle_lock:
            if self._started:
                return self
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            self._started = True
        return self

    async def close(self) -> None:
        """Dispose every connection held by the pool."""

        async with self._lifecycle_lock:
            await self.engine.dispose()
            self._started = False

    async def __aenter__(self) -> PostgresDatabase:
        return await self.start()

    async def __aexit__(self, *_args: object) -> None:
        await self.close()


postgres = PostgresDatabase(
    DATABASE_URL,
    echo=DATABASE_ECHO,
    pool_size=DATABASE_POOL_SIZE,
    max_overflow=DATABASE_MAX_OVERFLOW,
    pool_recycle=DATABASE_POOL_RECYCLE_SECONDS,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield one transaction-capable session per FastAPI request."""

    async with postgres.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_postgres() -> PostgresDatabase:
    """Return the shared database lifecycle owner."""

    return postgres

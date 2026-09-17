"""Async SQLAlchemy engine and session factory."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


class Database:
    """Thin wrapper around an async engine + session factory.

    Kept as an explicit object (instead of module-level globals) so it can be
    constructed once in `main.py`/`bot.py` and injected into middlewares,
    which makes the whole data layer easy to swap out in tests (e.g. for an
    in-memory SQLite engine).
    """

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self.engine: AsyncEngine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session, committing on success and rolling back on error."""
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def dispose(self) -> None:
        logger.info("Disposing database engine")
        await self.engine.dispose()

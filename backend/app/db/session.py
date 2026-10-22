from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


@asynccontextmanager
async def open_session_factory(
    database_url: str,
    *,
    pooled: bool = True,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Движок и фабрика сессий на время блока; при выходе соединения закрываются.

    pooled=False — для кода, который живёт один asyncio.run (CLI, задачи Celery):
    пул соединений asyncpg привязан к event loop и не переживает его закрытие.
    """
    if pooled:
        engine = create_async_engine(database_url, pool_pre_ping=True)
    else:
        engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()

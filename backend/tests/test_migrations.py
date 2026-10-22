from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base


def _diff(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(connection)
    return list(compare_metadata(context, Base.metadata))


async def test_migrations_match_models(engine: AsyncEngine) -> None:
    """Если модель поменяли, а миграцию не написали, тест упадёт."""
    async with engine.connect() as conn:
        diff = await conn.run_sync(_diff)

    assert diff == []

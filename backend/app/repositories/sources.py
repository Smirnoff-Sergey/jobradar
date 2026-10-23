from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Source


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, code: str) -> Source | None:
        return await self._session.get(Source, code)

    async def list_all(self) -> Sequence[Source]:
        return (await self._session.scalars(select(Source).order_by(Source.code))).all()

    async def count_failure(self, code: str) -> None:
        """+1 к счётчику неудачных сборов — в SQL, без чтения строки и без гонки."""
        stmt = update(Source).where(Source.code == code)
        await self._session.execute(stmt.values(failed_runs=Source.failed_runs + 1))

    async def try_lock_for_collect(self, code: str) -> bool:
        """Advisory-блокировка сбора источника до конца текущей транзакции.

        Снимается сама при commit или rollback. False — источник уже пишет другой процесс.
        """
        acquired = await self._session.scalar(
            select(func.pg_try_advisory_xact_lock(func.hashtext(f"collect:{code}")))
        )
        return bool(acquired)

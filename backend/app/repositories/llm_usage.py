from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LLMDailyUsage, LLMGuard

_GUARD_ID = 1


class LLMUsageRepository:
    """Дневной счётчик запросов к LLM и аварийная остановка."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(self, day: date, limit: int) -> bool:
        """Атомарно резервирует один запрос в счётчике дня. False — лимит исчерпан."""
        if limit <= 0:
            return False
        insert_stmt = insert(LLMDailyUsage).values(day=day, requests=1)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[LLMDailyUsage.day],
            set_={"requests": LLMDailyUsage.requests + 1},
            where=LLMDailyUsage.requests < limit,
        ).returning(LLMDailyUsage.requests)
        return await self._session.scalar(stmt) is not None

    async def used(self, day: date) -> int:
        # Колонкой, а не session.get: счётчик меняется атомарным UPDATE в обход identity map.
        used = await self._session.scalar(
            select(LLMDailyUsage.requests).where(LLMDailyUsage.day == day)
        )
        return used or 0

    async def pause(self, until: datetime | None, reason: str | None) -> None:
        """until=None — снять остановку."""
        stmt = insert(LLMGuard).values(id=_GUARD_ID, paused_until=until, reason=reason)
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[LLMGuard.id],
                set_={"paused_until": until, "reason": reason},
            )
        )

    async def pause_state(self) -> tuple[datetime | None, str | None]:
        row = (
            await self._session.execute(
                select(LLMGuard.paused_until, LLMGuard.reason).where(LLMGuard.id == _GUARD_ID)
            )
        ).first()
        return (None, None) if row is None else (row[0], row[1])

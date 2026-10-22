import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LLMSettings
from app.repositories.llm_usage import LLMUsageRepository

logger = logging.getLogger(__name__)

# После отказа в доступе (ключ, регион) пробуем снова не раньше чем через час:
# иначе досыл оценок каждый час тратил бы лимит на заведомо провальные запросы.
ACCESS_PAUSE = timedelta(hours=1)
# Платный ответ останавливает оценку до ручного снятия (python -m app.cli llm-unpause).
PAUSED_INDEFINITELY = datetime(9999, 1, 1, tzinfo=UTC)


def utc_today() -> date:
    return datetime.now(UTC).date()


@dataclass(frozen=True, slots=True)
class LLMUsage:
    day: date
    used: int
    limit: int
    enabled: bool
    models: tuple[str, ...]
    paused_until: datetime | None
    pause_reason: str | None


class LLMBudget:
    """Дневной лимит запросов к LLM и аварийная остановка. Все изменения сразу фиксируются:
    счётчик и остановка должны быть видны другим задачам до запроса к модели."""

    def __init__(self, session: AsyncSession, settings: LLMSettings) -> None:
        self._session = session
        self._settings = settings
        self._usage = LLMUsageRepository(session)

    async def usage(self) -> LLMUsage:
        day = utc_today()
        paused_until, reason = await self._active_pause()
        return LLMUsage(
            day=day,
            used=await self._usage.used(day),
            limit=self._settings.daily_request_limit,
            enabled=self._settings.enabled,
            models=tuple(self._settings.models),
            paused_until=paused_until,
            pause_reason=reason,
        )

    async def available(self) -> int:
        """Сколько запросов можно сделать сейчас: 0 — выключено, на паузе или лимит исчерпан."""
        if not self._settings.enabled or (await self._active_pause())[0] is not None:
            return 0
        used = await self._usage.used(utc_today())
        return max(self._settings.daily_request_limit - used, 0)

    async def reserve(self) -> bool:
        if (await self._active_pause())[0] is not None:
            return False
        reserved = await self._usage.reserve(utc_today(), self._settings.daily_request_limit)
        await self._session.commit()
        return reserved

    async def pause_after_access_error(self, reason: str) -> None:
        logger.warning("LLM недоступен (%s) — оценка на паузе на %s", reason, ACCESS_PAUSE)
        await self._pause(datetime.now(UTC) + ACCESS_PAUSE, reason)

    async def stop_after_paid_response(self, reason: str) -> None:
        logger.error("Платный ответ LLM (%s) — оценка остановлена до ручного снятия", reason)
        await self._pause(PAUSED_INDEFINITELY, reason)

    async def unpause(self) -> None:
        await self._pause(None, None)

    async def _pause(self, until: datetime | None, reason: str | None) -> None:
        await self._usage.pause(until, reason)
        await self._session.commit()

    async def _active_pause(self) -> tuple[datetime | None, str | None]:
        until, reason = await self._usage.pause_state()
        if until is None or until <= datetime.now(UTC):
            return None, None
        return until, reason

import dataclasses
import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.db.models import Source
from app.repositories.evaluations import EvaluationRepository
from app.repositories.sources import SourceRepository
from app.repositories.vacancies import VacancyRepository
from app.services.filtering import VacancyFilterService
from app.services.queue import TaskQueue
from app.sources.base import SourceAdapter, VacancyData

logger = logging.getLogger(__name__)

RunStatus = Literal["success", "failed", "skipped", "disabled"]

# Если обход вернул заметно меньше вакансий, чем сейчас активно, скорее всего сбой источника:
# деактивацию пропускаем, чтобы не погасить живые вакансии.
MIN_COMPLETENESS = 0.8


@dataclass(frozen=True, slots=True)
class CollectStats:
    status: RunStatus
    received: int = 0
    changed: int = 0
    deactivated: int = 0
    deactivation_skipped: bool = False
    details_queued: int = 0

    def as_run_stats(self) -> dict[str, object]:
        """Для Source.last_run_stats: статус там хранится отдельной колонкой."""
        stats = dataclasses.asdict(self)
        stats.pop("status")
        return stats


class CollectorService:
    """Полный сбор вакансий одного источника.

    Сначала все страницы загружаются из сети — без открытой транзакции. Затем изменения
    записываются одной короткой транзакцией под advisory-блокировкой PostgreSQL:
    два параллельных сбора одного источника не перепишут данные друг друга.
    """

    def __init__(self, session: AsyncSession, adapter: SourceAdapter, queue: TaskQueue) -> None:
        self._session = session
        self._adapter = adapter
        self._queue = queue
        self._sources = SourceRepository(session)
        self._vacancies = VacancyRepository(session)
        self._evaluations = EvaluationRepository(session)
        self._filter = VacancyFilterService(session)

    async def collect(self) -> CollectStats:
        code = self._adapter.code
        source = await self._sources.get(code)
        if source is None:
            raise NotFoundError(f"Источник {code} не зарегистрирован")
        if not source.is_enabled:
            return CollectStats(status="disabled")
        await self._session.commit()  # не держим транзакцию открытой во время сетевых запросов

        try:
            items = await self._fetch_all()
            stats = await self._save(source, items)
        except Exception as exc:
            logger.exception("Сбор %s не удался", code)
            await self._session.rollback()
            source.finish_run(
                "failed", error=exc.message if isinstance(exc, AppError) else repr(exc)
            )
            await self._session.commit()
            raise

        if stats.status == "success":
            stats = dataclasses.replace(stats, details_queued=await self._queue_descriptions(code))
            source.finish_run(stats.status, stats=stats.as_run_stats())
            await self._session.commit()
        logger.info("Сбор %s завершён: %s", code, stats)
        return stats

    async def _fetch_all(self) -> list[VacancyData]:
        # Закреплённые вакансии могут повторяться на разных страницах — оставляем по одной.
        unique: dict[str, VacancyData] = {}
        async for page in self._adapter.iter_pages():
            unique.update((item.external_id, item) for item in page)
        return list(unique.values())

    async def _save(self, source: Source, items: list[VacancyData]) -> CollectStats:
        if not await self._sources.try_lock_for_collect(source.code):
            logger.info("Сбор %s уже записывает данные в другом процессе — пропуск", source.code)
            return CollectStats(status="skipped", received=len(items))

        active_before = await self._vacancies.count_active(source.code)
        changed = await self._vacancies.upsert_many(source.code, items)
        # Оценки старого текста вакансии больше не верны — их пересчитает досыл.
        await self._evaluations.delete_for_vacancies(changed)
        complete = len(items) >= active_before * MIN_COMPLETENESS
        if complete and items:
            seen = [item.external_id for item in items]
            deactivated = await self._vacancies.deactivate_missing(source.code, seen)
        else:
            deactivated = 0
            logger.warning(
                "Сбор %s: получено %d вакансий при %d активных — деактивация пропущена",
                source.code,
                len(items),
                active_before,
            )
        await self._filter.apply_for_all_users(changed)

        stats = CollectStats(
            status="success",
            received=len(items),
            changed=len(changed),
            deactivated=deactivated,
            deactivation_skipped=not (complete and items),
        )
        source.finish_run(stats.status, stats=stats.as_run_stats())
        await self._session.commit()
        return stats

    async def _queue_descriptions(self, source_code: str) -> int:
        pending = await self._filter.pending_descriptions(source_code)
        await self._session.commit()
        if pending:
            await self._queue.fetch_details(pending)
        return len(pending)

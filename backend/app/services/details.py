import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PermanentExternalError
from app.repositories.vacancies import VacancyRepository
from app.sources.base import SourceAdapter

logger = logging.getLogger(__name__)

AdapterFactory = Callable[[str], SourceAdapter]


class VacancyDetailsService:
    def __init__(self, session: AsyncSession, adapter_factory: AdapterFactory) -> None:
        self._session = session
        self._vacancies = VacancyRepository(session)
        self._adapter_factory = adapter_factory

    async def load_description(self, vacancy_id: int) -> bool:
        """Загружает полное описание. Повторный вызов ничего не делает — задача идемпотентна.

        Временные ошибки источника пробрасываются (задачу повторит Celery). Постоянные
        (вакансию удалили, 404) запоминаются как «описания нет», чтобы не запрашивать вечно.
        """
        vacancy = await self._vacancies.get(vacancy_id)
        if vacancy is None or not vacancy.is_active or vacancy.description_fetched_at is not None:
            return False
        await self._session.commit()  # сетевой запрос — вне транзакции

        adapter = self._adapter_factory(vacancy.source_code)
        try:
            vacancy.description = await adapter.fetch_description(vacancy.external_id)
        except PermanentExternalError as exc:
            logger.warning("Описание вакансии %d недоступно: %s", vacancy_id, exc.message)
            vacancy.description = None
        vacancy.description_fetched_at = datetime.now(UTC)
        await self._session.commit()
        return vacancy.description is not None

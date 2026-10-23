from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LLMSettings
from app.core.errors import ConflictError, InvalidUrlError, NotFoundError, PermanentExternalError
from app.repositories.evaluations import EvaluationRepository
from app.repositories.search_profiles import SearchProfileRepository
from app.repositories.sources import SourceRepository
from app.repositories.vacancies import VacancyRepository
from app.services.evaluation import EvaluationScheduler
from app.services.filtering import VacancyFilterService
from app.services.queue import TaskQueue
from app.sources.base import SourceAdapter, VacancyImporter
from app.sources.registry import parse_vacancy_url

AdapterFactory = Callable[[str], SourceAdapter]


class VacancyImportService:
    """Ручное добавление вакансии по ссылке — для той, что не попала в сбор или нужна сразу.

    Дальше вакансия живёт как собранная: фильтр, оценка, следующий полный сбор снимет её
    с публикации, если источник её больше не отдаёт.
    """

    def __init__(
        self,
        session: AsyncSession,
        adapters: AdapterFactory,
        queue: TaskQueue,
        llm_settings: LLMSettings,
    ) -> None:
        self._session = session
        self._adapters = adapters
        self._queue = queue
        self._vacancies = VacancyRepository(session)
        self._sources = SourceRepository(session)
        self._profiles = SearchProfileRepository(session)
        self._evaluations = EvaluationRepository(session)
        self._filter = VacancyFilterService(session)
        self._scheduler = EvaluationScheduler(session, queue, llm_settings)

    async def import_url(self, user_id: int, url: str) -> int:
        """Загружает вакансию по ссылке и возвращает её id. Повтор с той же ссылкой безопасен."""
        code, external_id = parse_vacancy_url(url)
        source = await self._sources.get(code)
        if source is None or not source.is_enabled:
            raise ConflictError(f"Источник {code} выключен")
        adapter = self._adapters(code)
        if not isinstance(adapter, VacancyImporter):
            raise InvalidUrlError(f"Источник {code} не умеет загружать вакансию по ссылке")
        # Запрос к источнику — вне транзакции.
        await self._session.commit()
        try:
            imported = await adapter.fetch_vacancy(external_id)
        except PermanentExternalError as exc:
            raise NotFoundError(f"Не удалось загрузить вакансию с {code}: {exc.message}") from exc
        if not imported.is_active:
            raise ConflictError("Вакансия снята с публикации на источнике")

        changed = await self._vacancies.upsert_many(code, [imported.data])
        if changed:
            # Текст изменился — прежняя оценка устарела.
            await self._evaluations.delete_for_vacancies(changed)
        # id — из карточки, а не из ссылки: в ссылке он может быть записан иначе (0036738).
        vacancy = await self._vacancies.get_by_external(code, imported.data.external_id)
        assert vacancy is not None  # строка только что вставлена или обновлена
        has_description = vacancy.description_fetched_at is not None
        if imported.description and not has_description:
            vacancy.description = imported.description
            vacancy.description_fetched_at = datetime.now(UTC)
            has_description = True
        profile = await self._profiles.get_by_user(user_id)
        if profile is not None:
            await self._filter.apply(profile, [vacancy.id])
        await self._session.commit()

        if has_description:
            # Оценка встанет в очередь, только если вакансия прошла фильтр и есть лимит.
            await self._scheduler.queue_pending(vacancy.id)
        else:
            await self._queue.fetch_details([vacancy.id])
        return vacancy.id

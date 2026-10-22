from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import Vacancy
from app.domain.vacancies import VacancyListQuery
from app.llm.prompts import PROMPT_VERSION
from app.repositories.vacancies import VacancyRepository, VacancyRow


class VacancyService:
    """Выдача вакансий с оценкой текущей версии промпта."""

    def __init__(self, session: AsyncSession) -> None:
        self._vacancies = VacancyRepository(session)

    async def search(self, query: VacancyListQuery) -> tuple[list[VacancyRow], int]:
        return await self._vacancies.list_for_user(query, PROMPT_VERSION)

    async def for_labeling(self, limit: int) -> Sequence[Vacancy]:
        """Вакансии для ручной разметки набора проверки качества (scripts/eval.py)."""
        return await self._vacancies.list_passed_with_description(limit)

    async def get(self, vacancy_id: int, user_id: int) -> VacancyRow:
        found = await self._vacancies.get_for_user(vacancy_id, user_id, PROMPT_VERSION)
        if found is None:
            raise NotFoundError("Вакансия не найдена")
        return found

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SearchProfile
from app.domain.filtering import evaluate
from app.repositories.filter_results import FilterResultRepository
from app.repositories.search_profiles import SearchProfileRepository
from app.repositories.vacancies import VacancyRepository


class VacancyFilterService:
    """Применяет критерии поиска к вакансиям и сохраняет решения. Транзакцию не завершает."""

    def __init__(self, session: AsyncSession) -> None:
        self._vacancies = VacancyRepository(session)
        self._results = FilterResultRepository(session)
        self._profiles = SearchProfileRepository(session)

    async def apply(self, profile: SearchProfile, vacancy_ids: Sequence[int] | None = None) -> None:
        """Фильтрует активные вакансии: все или только указанные."""
        if vacancy_ids is not None and not vacancy_ids:
            return
        vacancies = await self._vacancies.list_active(vacancy_ids)
        decisions = {vacancy.id: evaluate(profile, vacancy) for vacancy in vacancies}
        await self._results.save(profile.user_id, decisions)

    async def apply_for_all_users(self, vacancy_ids: Sequence[int]) -> None:
        for profile in await self._profiles.list_all():
            await self.apply(profile, vacancy_ids)

    async def pending_descriptions(self, source_code: str | None = None) -> list[int]:
        return await self._results.pending_descriptions(source_code)

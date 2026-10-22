from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.domain.vacancies import VacancyListQuery
from app.repositories.vacancies import VacancyRepository, VacancyWithDecision


class VacancyService:
    def __init__(self, session: AsyncSession) -> None:
        self._vacancies = VacancyRepository(session)

    async def search(self, query: VacancyListQuery) -> tuple[list[VacancyWithDecision], int]:
        return await self._vacancies.list_for_user(query)

    async def get(self, vacancy_id: int, user_id: int) -> VacancyWithDecision:
        found = await self._vacancies.get_for_user(vacancy_id, user_id)
        if found is None:
            raise NotFoundError("Вакансия не найдена")
        return found

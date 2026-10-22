from dataclasses import fields

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SearchProfile
from app.domain.filtering import SearchCriteria
from app.repositories.search_profiles import SearchProfileRepository
from app.services.filtering import VacancyFilterService
from app.services.queue import TaskQueue


class SearchProfileService:
    def __init__(self, session: AsyncSession, queue: TaskQueue) -> None:
        self._session = session
        self._queue = queue
        self._profiles = SearchProfileRepository(session)
        self._filter = VacancyFilterService(session)

    async def get_or_create(self, user_id: int) -> SearchProfile:
        """Профиль пользователя. Новый создаётся с критериями по умолчанию, и сразу ставится
        перефильтрация: иначе уже собранные вакансии остались бы без решения фильтра."""
        profile = await self._profiles.get_by_user(user_id)
        if profile is None:
            profile = await self._profiles.add(SearchProfile(user_id=user_id))
            await self._session.commit()
            await self._session.refresh(profile)
            await self._queue.refilter_user(user_id)
        return profile

    async def update(self, user_id: int, criteria: SearchCriteria) -> tuple[SearchProfile, str]:
        """Сохраняет критерии и ставит перефильтрацию вакансий. Возвращает профиль и id задачи."""
        profile = await self.get_or_create(user_id)
        for field in fields(criteria):
            setattr(profile, field.name, getattr(criteria, field.name))
        await self._session.commit()
        await self._session.refresh(profile)
        return profile, await self._queue.refilter_user(user_id)

    async def refilter(self, user_id: int) -> int:
        """Перефильтровывает все активные вакансии пользователя и ставит загрузку описаний.

        Возвращает число вакансий, поставленных на загрузку описания.
        """
        profile = await self._profiles.get_by_user(user_id)
        if profile is None:
            return 0
        await self._filter.apply(profile)
        await self._session.commit()
        pending = await self._filter.pending_descriptions()
        await self._session.commit()
        if pending:
            await self._queue.fetch_details(pending)
        return len(pending)

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidStatusError, NotFoundError, StatusLockedError
from app.db.models import Application, StatusHistory, Vacancy
from app.domain.applications import (
    APPLICATION_STATUSES,
    BUTTON_OVERRIDABLE,
    ApplicationStatus,
)
from app.repositories.applications import ApplicationRepository
from app.repositories.vacancies import VacancyRepository


class ApplicationService:
    """Журнал откликов. Каждая смена статуса пишется в историю."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._applications = ApplicationRepository(session)
        self._vacancies = VacancyRepository(session)

    async def set_status(
        self,
        user_id: int,
        vacancy_id: int,
        status: str,
        *,
        notes: str | None = None,
        from_button: bool = False,
    ) -> Application:
        """Создаёт отклик на вакансию или меняет его статус.

        from_button — нажатие кнопки бота: меняет только «ранние» статусы, чтобы кнопка
        в старом сообщении не откатила «пригласили» или «отказ».
        """
        if status not in APPLICATION_STATUSES:
            raise InvalidStatusError  # из бота статус приходит строкой
        if await self._vacancies.get(vacancy_id) is None:
            raise NotFoundError("Вакансия не найдена")
        application, created = await self._applications.get_or_create(user_id, vacancy_id, status)
        if created:
            await self._applications.add_history(application.id, None, status)
        elif from_button and application.status not in BUTTON_OVERRIDABLE:
            current = application.status
            await self._session.rollback()  # снимаем блокировку строки
            raise StatusLockedError(current)
        else:
            await self._change_status(application, status)
        return await self._save(application, notes)

    async def update(
        self,
        user_id: int,
        application_id: int,
        *,
        status: ApplicationStatus | None = None,
        notes: str | None = None,
    ) -> Application:
        application = await self._applications.get(user_id, application_id, for_update=True)
        if application is None:
            raise NotFoundError("Отклик не найден")
        if status is not None:
            await self._change_status(application, status)
        return await self._save(application, notes)

    async def get(self, user_id: int, application_id: int) -> Application:
        application = await self._applications.get(user_id, application_id)
        if application is None:
            raise NotFoundError("Отклик не найден")
        return application

    async def history(self, application_id: int) -> Sequence[StatusHistory]:
        return await self._applications.history(application_id)

    async def list_for_user(
        self, user_id: int, status: ApplicationStatus | None, limit: int, offset: int
    ) -> tuple[list[tuple[Application, Vacancy]], int]:
        return await self._applications.list_for_user(user_id, status, limit, offset)

    async def _save(self, application: Application, notes: str | None) -> Application:
        if notes is not None:
            application.notes = notes
        await self._session.commit()
        await self._session.refresh(application)  # updated_at выставила БД
        return application

    async def _change_status(self, application: Application, status: str) -> None:
        if application.status == status:
            return
        await self._applications.add_history(application.id, application.status, status)
        application.status = status

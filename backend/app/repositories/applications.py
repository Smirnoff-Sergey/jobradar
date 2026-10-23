from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Application, StatusHistory, Vacancy


class ApplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, user_id: int, application_id: int, *, for_update: bool = False
    ) -> Application | None:
        stmt = select(Application).where(
            Application.id == application_id, Application.user_id == user_id
        )
        if for_update:
            # Смена статуса пишет историю «из → в»: параллельная кнопка бота должна подождать.
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self._session.scalar(stmt)

    async def get_by_id(
        self, application_id: int, *, for_update: bool = False
    ) -> Application | None:
        """Отклик без проверки владельца — для фоновых задач, которые получают id из API."""
        stmt = select(Application).where(Application.id == application_id)
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self._session.scalar(stmt)

    async def get_or_create(
        self, user_id: int, vacancy_id: int, status: str
    ) -> tuple[Application, bool]:
        """Отклик пользователя на вакансию, заблокированный до конца транзакции.

        Второй элемент — создан ли отклик сейчас. Вставка через ON CONFLICT: две
        параллельные кнопки не создадут двух откликов и не уронят друг друга.
        """
        created_id = await self._session.scalar(
            insert(Application)
            .values(user_id=user_id, vacancy_id=vacancy_id, status=status)
            .on_conflict_do_nothing()
            .returning(Application.id)
        )
        application = await self._session.scalar(
            select(Application)
            .where(Application.user_id == user_id, Application.vacancy_id == vacancy_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert application is not None  # строка только что вставлена или уже была
        return application, created_id is not None

    async def add_history(
        self, application_id: int, from_status: str | None, to_status: str
    ) -> None:
        self._session.add(
            StatusHistory(
                application_id=application_id, from_status=from_status, to_status=to_status
            )
        )
        await self._session.flush()

    async def history(self, application_id: int) -> Sequence[StatusHistory]:
        stmt = (
            select(StatusHistory)
            .where(StatusHistory.application_id == application_id)
            .order_by(StatusHistory.changed_at, StatusHistory.id)
        )
        return (await self._session.scalars(stmt)).all()

    async def list_for_user(
        self, user_id: int, status: str | None, limit: int, offset: int
    ) -> tuple[list[tuple[Application, Vacancy]], int]:
        stmt = (
            select(Application, Vacancy)
            .join(Vacancy, Vacancy.id == Application.vacancy_id)
            .where(Application.user_id == user_id)
        )
        if status is not None:
            stmt = stmt.where(Application.status == status)
        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.execute(
            stmt.order_by(Application.updated_at.desc(), Application.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(row[0], row[1]) for row in rows], total or 0

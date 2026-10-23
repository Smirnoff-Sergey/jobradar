from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Application, Letter
from app.domain.evaluation import FAILED, PENDING


class LetterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, letter_id: int) -> Letter | None:
        return await self._session.get(Letter, letter_id)

    async def create_pending(
        self,
        application_id: int,
        resume_id: int,
        prompt_version: str,
        *,
        stale_before: datetime,
        stuck_message: str,
    ) -> Letter | None:
        """Новый черновик в статусе pending. None — для отклика уже пишется письмо.

        Зависшая генерация (старше stale_before) помечается неудавшейся и не мешает новой.
        """
        await self._session.execute(
            update(Letter)
            .where(
                Letter.application_id == application_id,
                Letter.status == PENDING,
                Letter.updated_at < stale_before,
            )
            .values(status=FAILED, error=stuck_message)
        )
        created = await self._session.scalar(
            insert(Letter)
            .values(
                application_id=application_id,
                resume_id=resume_id,
                prompt_version=prompt_version,
                status=PENDING,
            )
            # Частичный уникальный индекс: одна генерация на отклик одновременно.
            .on_conflict_do_nothing()
            .returning(Letter.id)
        )
        return None if created is None else await self.get(created)

    async def claim(self, letter_id: int, *, stale_before: datetime) -> Letter | None:
        """Захват черновика задачей перед запросом к модели. None — черновик готов,
        отменён или его прямо сейчас пишет другая задача."""
        claimed = await self._session.scalar(
            update(Letter)
            .where(
                Letter.id == letter_id,
                Letter.status == PENDING,
                or_(Letter.started_at.is_(None), Letter.started_at < stale_before),
            )
            .values(started_at=datetime.now(UTC))
            .returning(Letter.id)
        )
        if claimed is None:
            return None
        return await self._session.scalar(
            select(Letter).where(Letter.id == claimed).execution_options(populate_existing=True)
        )

    async def list_for_vacancy(self, user_id: int, vacancy_id: int) -> Sequence[Letter]:
        stmt = (
            select(Letter)
            .join(Application, Application.id == Letter.application_id)
            .where(Application.user_id == user_id, Application.vacancy_id == vacancy_id)
            .order_by(Letter.created_at.desc(), Letter.id.desc())
        )
        return (await self._session.scalars(stmt)).all()

from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Resume


class ResumeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, resume_id: int) -> Resume | None:
        return await self._session.get(Resume, resume_id)

    async def get_active(self, user_id: int) -> Resume | None:
        return await self._session.scalar(
            select(Resume).where(Resume.user_id == user_id, Resume.is_active)
        )

    async def list_by_user(self, user_id: int) -> Sequence[Resume]:
        stmt = select(Resume).where(Resume.user_id == user_id).order_by(Resume.id)
        return (await self._session.scalars(stmt)).all()

    async def add(self, resume: Resume) -> Resume:
        self._session.add(resume)
        await self._session.flush()
        return resume

    async def deactivate_all(self, user_id: int) -> None:
        """Снимает активность со всех резюме пользователя — перед активацией другого:
        уникальный индекс не допускает двух активных одновременно."""
        await self._session.execute(
            update(Resume)
            .where(Resume.user_id == user_id, Resume.is_active)
            .values(is_active=False)
            .execution_options(synchronize_session="fetch")
        )

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import Resume
from app.repositories.evaluations import EvaluationRepository
from app.repositories.resumes import ResumeRepository
from app.repositories.users import UserRepository
from app.services.auth import normalize_email


class ResumeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._resumes = ResumeRepository(session)
        self._evaluations = EvaluationRepository(session)

    async def list_for_user(self, user_id: int) -> Sequence[Resume]:
        return await self._resumes.list_by_user(user_id)

    async def get(self, user_id: int, resume_id: int) -> Resume:
        resume = await self._resumes.get(resume_id)
        # Чужое резюме неотличимо от несуществующего.
        if resume is None or resume.user_id != user_id:
            raise NotFoundError("Резюме не найдено")
        return resume

    async def create(self, user_id: int, title: str, text: str, *, make_active: bool) -> Resume:
        if make_active:
            await self._resumes.deactivate_all(user_id)
        resume = await self._resumes.add(
            Resume(user_id=user_id, title=title, text=text, is_active=make_active)
        )
        await self._session.commit()
        await self._session.refresh(resume)
        return resume

    async def create_for_email(self, email: str, title: str, text: str) -> Resume:
        """Для CLI: новое активное резюме пользователя по email."""
        user = await UserRepository(self._session).get_by_email(normalize_email(email))
        if user is None:
            raise NotFoundError(f"Пользователь {email} не найден")
        return await self.create(user.id, title, text, make_active=True)

    async def update(
        self,
        user_id: int,
        resume_id: int,
        *,
        title: str | None = None,
        text: str | None = None,
        is_active: bool | None = None,
    ) -> Resume:
        """Частичное обновление. Новый текст сбрасывает оценки этого резюме: они устарели,
        и фоновая задача переоценит вакансии в пределах дневного лимита."""
        resume = await self.get(user_id, resume_id)
        if is_active and not resume.is_active:
            await self._resumes.deactivate_all(user_id)
        if is_active is not None:
            resume.is_active = is_active
        if title is not None:
            resume.title = title
        if text is not None and text != resume.text:
            resume.text = text
            await self._evaluations.delete_for_resume(resume.id)
        await self._session.commit()
        await self._session.refresh(resume)
        return resume

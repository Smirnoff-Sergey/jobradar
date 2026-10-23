from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import BigInteger, and_, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Evaluation, Resume, Vacancy, VacancyFilterResult
from app.domain.evaluation import PENDING
from app.repositories.arrays import in_array
from app.repositories.claims import settled_or_fresh


@dataclass(slots=True)
class Claim:
    """Захваченная для оценки пара. previous_status — состояние до захвата при
    переоценке: если новая оценка не получится, прежняя восстанавливается."""

    evaluation: Evaluation
    previous_status: str | None = None


class EvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self,
        vacancy_id: int,
        resume_id: int,
        prompt_version: str,
        *,
        stale_before: datetime,
        force: bool = False,
    ) -> Claim | None:
        """Захватывает пару для оценки. None — пару уже оценивает другая задача
        или оценка готова, а переоценка не запрошена."""
        existing = await self._session.scalar(
            select(Evaluation)
            .where(
                Evaluation.vacancy_id == vacancy_id,
                Evaluation.resume_id == resume_id,
                Evaluation.prompt_version == prompt_version,
            )
            .with_for_update()
        )
        if existing is None:
            created = await self._session.scalar(
                insert(Evaluation)
                .values(
                    vacancy_id=vacancy_id,
                    resume_id=resume_id,
                    prompt_version=prompt_version,
                    status=PENDING,
                )
                .on_conflict_do_nothing()  # параллельная задача успела раньше
                .returning(Evaluation.id)
            )
            return None if created is None else Claim(await self._get(created))

        if existing.status == PENDING:
            # Задача, захватившая пару, могла упасть вместе с воркером — перехватываем.
            if existing.updated_at >= stale_before:
                return None
            previous = None
        elif force:
            previous = existing.status
        else:
            return None
        existing.status = PENDING
        # Явно: при перехвате статус не меняется, и без этого UPDATE не освежил бы время.
        existing.updated_at = datetime.now(UTC)
        await self._session.flush()
        return Claim(existing, previous)

    async def release(self, claim: Claim) -> None:
        """Снимает захват: новая пара удаляется, при переоценке возвращается прежняя оценка."""
        if claim.previous_status is None:
            await self._session.delete(claim.evaluation)
        else:
            claim.evaluation.status = claim.previous_status
        await self._session.flush()

    async def delete_for_resume(self, resume_id: int) -> None:
        await self._session.execute(delete(Evaluation).where(Evaluation.resume_id == resume_id))

    async def delete_for_vacancies(self, vacancy_ids: Sequence[int]) -> None:
        if vacancy_ids:
            await self._session.execute(
                delete(Evaluation).where(in_array(Evaluation.vacancy_id, vacancy_ids, BigInteger()))
            )

    async def pending_pairs(
        self,
        prompt_version: str,
        *,
        stale_before: datetime,
        limit: int,
        vacancy_id: int | None = None,
    ) -> list[tuple[int, int]]:
        """Пары (вакансия, активное резюме), которые пора оценить.

        Вакансия активна, прошла фильтр у владельца резюме, описание уже загружалось,
        а оценки этой версии промпта нет (или она зависла в pending).
        """
        evaluated = (
            select(Evaluation.id)
            .where(
                Evaluation.vacancy_id == Vacancy.id,
                Evaluation.resume_id == Resume.id,
                Evaluation.prompt_version == prompt_version,
                settled_or_fresh(
                    Evaluation.status,
                    Evaluation.updated_at,
                    pending=PENDING,
                    stale_before=stale_before,
                ),
            )
            .exists()
        )
        stmt = (
            select(Vacancy.id, Resume.id)
            .join(
                VacancyFilterResult,
                and_(VacancyFilterResult.vacancy_id == Vacancy.id, VacancyFilterResult.passed),
            )
            .join(Resume, and_(Resume.user_id == VacancyFilterResult.user_id, Resume.is_active))
            .where(Vacancy.is_active, Vacancy.description_fetched_at.is_not(None), ~evaluated)
            .order_by(Vacancy.published_at.desc().nulls_last(), Vacancy.id)
            .limit(limit)
        )
        if vacancy_id is not None:
            stmt = stmt.where(Vacancy.id == vacancy_id)
        return [(row[0], row[1]) for row in await self._session.execute(stmt)]

    async def _get(self, evaluation_id: int) -> Evaluation:
        evaluation = await self._session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        return evaluation

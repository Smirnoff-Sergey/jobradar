from collections.abc import Mapping

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Vacancy, VacancyFilterResult
from app.domain.filtering import FilterDecision
from app.repositories.vacancies import UPSERT_CHUNK


class FilterResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, user_id: int, decisions: Mapping[int, FilterDecision]) -> None:
        rows = [
            {
                "vacancy_id": vacancy_id,
                "user_id": user_id,
                "passed": decision.passed,
                "reasons": list(decision.reasons),
                "salary_unknown": decision.salary_unknown,
            }
            for vacancy_id, decision in decisions.items()
        ]
        for start in range(0, len(rows), UPSERT_CHUNK):
            stmt = insert(VacancyFilterResult).values(rows[start : start + UPSERT_CHUNK])
            stmt = stmt.on_conflict_do_update(
                index_elements=[VacancyFilterResult.vacancy_id, VacancyFilterResult.user_id],
                set_={
                    "passed": stmt.excluded.passed,
                    "reasons": stmt.excluded.reasons,
                    "salary_unknown": stmt.excluded.salary_unknown,
                    "filtered_at": func.now(),
                },
            )
            await self._session.execute(stmt)

    async def pending_descriptions(self, source_code: str | None = None) -> list[int]:
        """Активные вакансии, прошедшие фильтр хотя бы у одного пользователя, без описания.

        Берутся все такие вакансии, а не только изменившиеся: если постановка задачи
        потерялась или задача упала, описание дозапросится при следующем запуске.
        """
        passed_somewhere = (
            select(VacancyFilterResult.vacancy_id)
            .where(VacancyFilterResult.vacancy_id == Vacancy.id, VacancyFilterResult.passed)
            .exists()
        )
        stmt = (
            select(Vacancy.id)
            .where(Vacancy.is_active, Vacancy.description_fetched_at.is_(None), passed_somewhere)
            .order_by(Vacancy.id)
        )
        if source_code is not None:
            stmt = stmt.where(Vacancy.source_code == source_code)
        return list(await self._session.scalars(stmt))

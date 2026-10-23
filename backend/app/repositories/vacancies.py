from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    BigInteger,
    ColumnElement,
    Select,
    String,
    and_,
    case,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Application, Evaluation, Resume, Vacancy, VacancyFilterResult
from app.domain.vacancies import VacancyListQuery
from app.repositories.arrays import in_array, not_in_array
from app.sources.base import VacancyData


@dataclass(frozen=True, slots=True)
class VacancyRow:
    """Вакансия с решением фильтра, оценкой по активному резюме и откликом пользователя."""

    vacancy: Vacancy
    decision: VacancyFilterResult | None
    evaluation: Evaluation | None
    application: Application | None


# asyncpg ограничивает число параметров запроса (32767); пачки по 500 строк с запасом влезают.
UPSERT_CHUNK = 500
_KEY_COLUMNS = frozenset({"source_code", "external_id"})


def _row(source_code: str, item: VacancyData) -> dict[str, object]:
    return {
        "source_code": source_code,
        "external_id": item.external_id,
        "url": item.url,
        "title": item.title,
        "company": item.company,
        "salary_from": item.salary_from,
        "salary_to": item.salary_to,
        "salary_currency": item.salary_currency,
        "salary_gross": item.salary_gross,
        "work_formats": list(item.work_formats),
        "contract_types": list(item.contract_types),
        "short_description": item.short_description,
        "published_at": item.published_at,
        "raw": item.raw,
        "content_hash": item.content_hash(),
    }


def _for_user(
    user_id: int, prompt_version: str
) -> Select[Vacancy, VacancyFilterResult, Evaluation, Application]:
    active_resume = (
        select(Resume.id).where(Resume.user_id == user_id, Resume.is_active).scalar_subquery()
    )
    return (
        select(Vacancy, VacancyFilterResult, Evaluation, Application)
        .outerjoin(
            VacancyFilterResult,
            and_(
                VacancyFilterResult.vacancy_id == Vacancy.id, VacancyFilterResult.user_id == user_id
            ),
        )
        .outerjoin(
            Evaluation,
            and_(
                Evaluation.vacancy_id == Vacancy.id,
                Evaluation.resume_id == active_resume,
                Evaluation.prompt_version == prompt_version,
            ),
        )
        .outerjoin(
            Application,
            and_(Application.vacancy_id == Vacancy.id, Application.user_id == user_id),
        )
    )


class VacancyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, source_code: str, items: Sequence[VacancyData]) -> list[int]:
        """Вставляет новые и обновляет изменившиеся вакансии. Возвращает id затронутых строк.

        Неизменившаяся активная вакансия не трогается вовсе: повторный сбор не плодит записи
        и не сбрасывает уже загруженное описание.
        """
        changed: list[int] = []
        for start in range(0, len(items), UPSERT_CHUNK):
            rows = [_row(source_code, item) for item in items[start : start + UPSERT_CHUNK]]
            insert_stmt = insert(Vacancy).values(rows)
            excluded = insert_stmt.excluded
            content_changed = Vacancy.content_hash.is_distinct_from(excluded.content_hash)
            update_columns = {key: excluded[key] for key in rows[0] if key not in _KEY_COLUMNS}
            stmt = insert_stmt.on_conflict_do_update(
                index_elements=[Vacancy.source_code, Vacancy.external_id],
                set_={
                    **update_columns,
                    "is_active": True,
                    "updated_at": func.now(),
                    # Текст вакансии поменялся — старое полное описание больше не годится.
                    "description": case((content_changed, None), else_=Vacancy.description),
                    "description_fetched_at": case(
                        (content_changed, None), else_=Vacancy.description_fetched_at
                    ),
                },
                where=or_(content_changed, Vacancy.is_active.is_(False)),
            ).returning(Vacancy.id)
            changed.extend(await self._session.scalars(stmt))
        return changed

    async def count_active(self, source_code: str) -> int:
        stmt = select(func.count()).where(Vacancy.source_code == source_code, Vacancy.is_active)
        return await self._session.scalar(stmt) or 0

    async def deactivate_missing(self, source_code: str, seen_external_ids: Sequence[str]) -> int:
        """Помечает неактивными вакансии источника, которых не было в полном обходе."""
        stmt = (
            update(Vacancy)
            .where(
                Vacancy.source_code == source_code,
                Vacancy.is_active,
                not_in_array(Vacancy.external_id, seen_external_ids, String()),
            )
            .values(is_active=False, updated_at=func.now())
            .returning(Vacancy.id)
            .execution_options(synchronize_session=False)
        )
        return len((await self._session.scalars(stmt)).all())

    async def get_by_external(self, source_code: str, external_id: str) -> Vacancy | None:
        stmt = select(Vacancy).where(
            Vacancy.source_code == source_code, Vacancy.external_id == external_id
        )
        return await self._session.scalar(stmt.execution_options(populate_existing=True))

    async def get(self, vacancy_id: int) -> Vacancy | None:
        return await self._session.get(Vacancy, vacancy_id)

    async def list_active(self, ids: Sequence[int] | None = None) -> Sequence[Vacancy]:
        stmt = select(Vacancy).where(Vacancy.is_active)
        if ids is not None:
            stmt = stmt.where(in_array(Vacancy.id, ids, BigInteger()))
        return (await self._session.scalars(stmt)).all()

    async def list_passed_with_description(self, limit: int) -> Sequence[Vacancy]:
        """Активные вакансии с загруженным описанием, прошедшие фильтр хотя бы у кого-то."""
        passed = (
            select(VacancyFilterResult.vacancy_id)
            .where(VacancyFilterResult.vacancy_id == Vacancy.id, VacancyFilterResult.passed)
            .exists()
        )
        stmt = (
            select(Vacancy)
            .where(Vacancy.is_active, Vacancy.description.is_not(None), passed)
            .order_by(Vacancy.published_at.desc().nulls_last(), Vacancy.id)
            .limit(limit)
        )
        return (await self._session.scalars(stmt)).all()

    async def get_for_user(
        self, vacancy_id: int, user_id: int, prompt_version: str
    ) -> VacancyRow | None:
        stmt = _for_user(user_id, prompt_version).where(Vacancy.id == vacancy_id)
        row = (await self._session.execute(stmt)).first()
        return None if row is None else VacancyRow(*row)

    async def list_for_user(
        self, query: VacancyListQuery, prompt_version: str
    ) -> tuple[list[VacancyRow], int]:
        """Вакансии с решением фильтра и оценкой для пользователя и общее число строк."""
        stmt = _for_user(query.user_id, prompt_version)
        if query.status != "all":
            stmt = stmt.where(VacancyFilterResult.passed.is_(query.status == "passed"))
        if query.source_code is not None:
            stmt = stmt.where(Vacancy.source_code == query.source_code)
        if query.active_only:
            stmt = stmt.where(Vacancy.is_active)
        if query.verdict is not None:
            stmt = stmt.where(Evaluation.verdict == query.verdict)
        if query.score_min is not None:
            stmt = stmt.where(Evaluation.score >= query.score_min)
        if query.application_status is not None:
            stmt = stmt.where(Application.status == query.application_status)

        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        order: list[ColumnElement[Any]] = [
            Vacancy.published_at.desc().nulls_last(),
            Vacancy.id.desc(),
        ]
        if query.sort == "score":
            order.insert(0, Evaluation.score.desc().nulls_last())
        rows = await self._session.execute(
            stmt.order_by(*order).limit(query.limit).offset(query.offset)
        )
        return [VacancyRow(*row) for row in rows], total or 0

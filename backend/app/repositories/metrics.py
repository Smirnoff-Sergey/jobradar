from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Application, Evaluation, Letter, LLMDailyUsage, Source, Vacancy


@dataclass(frozen=True, slots=True)
class LLMWork:
    """Итог вызовов модели одного вида (оценки или письма) по статусу и модели."""

    kind: str
    status: str
    model: str
    count: int
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    vacancies: Sequence[tuple[str, bool, int]]  # источник, активна, число
    sources: Sequence[Source]
    llm_requests_total: int
    llm_requests_today: int
    llm_work: Sequence[LLMWork]
    applications: Sequence[tuple[str, int]]  # статус, число


class MetricsRepository:
    """Агрегаты для /metrics: несколько запросов с GROUP BY, без чтения строк целиком."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def snapshot(self, today: date) -> MetricsSnapshot:
        vacancies = await self._session.execute(
            select(Vacancy.source_code, Vacancy.is_active, func.count()).group_by(
                Vacancy.source_code, Vacancy.is_active
            )
        )
        sources = (await self._session.scalars(select(Source).order_by(Source.code))).all()
        requests_total = await self._session.scalar(
            select(func.coalesce(func.sum(LLMDailyUsage.requests), 0))
        )
        requests_today = await self._session.scalar(
            select(LLMDailyUsage.requests).where(LLMDailyUsage.day == today)
        )
        applications = await self._session.execute(
            select(Application.status, func.count()).group_by(Application.status)
        )
        return MetricsSnapshot(
            vacancies=[(code, active, count) for code, active, count in vacancies],
            sources=sources,
            llm_requests_total=int(requests_total or 0),
            llm_requests_today=int(requests_today or 0),
            llm_work=[
                *await self._llm_work("evaluation", Evaluation),
                *await self._llm_work("letter", Letter),
            ],
            applications=[(status, count) for status, count in applications],
        )

    async def _llm_work(self, kind: str, model: type[Evaluation] | type[Letter]) -> list[LLMWork]:
        rows = await self._session.execute(
            select(
                model.status,
                model.model,
                func.count(),
                func.coalesce(func.sum(model.tokens_in), 0),
                func.coalesce(func.sum(model.tokens_out), 0),
                func.coalesce(func.sum(model.cost_usd), 0),
            ).group_by(model.status, model.model)
        )
        return [
            LLMWork(
                kind,
                status,
                name or "none",
                count,
                int(tokens_in or 0),
                int(tokens_out or 0),
                Decimal(cost or 0),
            )
            for status, name, count, tokens_in, tokens_out, cost in rows
        ]

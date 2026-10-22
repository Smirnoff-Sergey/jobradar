import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ExternalServiceError
from app.db.models import Source
from app.services.collector import CollectorService
from app.services.queue import TaskStatus
from app.sources.base import VacancyData

GETMATCH_FIXTURE = Path(__file__).parent / "fixtures" / "getmatch_offers.json"


def load_getmatch_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(GETMATCH_FIXTURE.read_text(encoding="utf-8"))
    return data


@dataclass
class FakeTaskQueue:
    """Запоминает поставленные задачи вместо отправки в Celery."""

    collected: list[str] = field(default_factory=list)
    details: list[int] = field(default_factory=list)
    refiltered: list[int] = field(default_factory=list)
    statuses: dict[str, TaskStatus] = field(default_factory=dict)

    async def collect_source(self, source_code: str) -> str:
        self.collected.append(source_code)
        return f"collect-{len(self.collected)}"

    async def fetch_details(self, vacancy_ids: Sequence[int]) -> None:
        self.details.extend(vacancy_ids)

    async def refilter_user(self, user_id: int) -> str:
        self.refiltered.append(user_id)
        return f"refilter-{len(self.refiltered)}"

    async def status(self, task_id: str) -> TaskStatus:
        return self.statuses.get(task_id, TaskStatus(task_id, "PENDING"))


@dataclass
class FakeAdapter:
    pages: list[list[VacancyData]] = field(default_factory=list)
    descriptions: dict[str, str] = field(default_factory=dict)
    error: ExternalServiceError | None = None
    code: str = "getmatch"
    description_requests: list[str] = field(default_factory=list)

    async def iter_pages(self) -> AsyncIterator[list[VacancyData]]:
        for page in self.pages:
            yield page
        if self.error is not None:
            raise self.error

    async def fetch_description(self, external_id: str) -> str | None:
        self.description_requests.append(external_id)
        if self.error is not None:
            raise self.error
        return self.descriptions.get(external_id)


def vacancy(external_id: str, **overrides: object) -> VacancyData:
    """Вакансия, которая по умолчанию проходит типичный фильтр: удалёнка, Python, 250 000 net."""
    values: dict[str, object] = {
        "external_id": external_id,
        "url": f"https://example.com/vacancies/{external_id}",
        "title": f"Python Backend Developer {external_id}",
        "company": "Example",
        "salary_from": 200_000,
        "salary_to": 250_000,
        "salary_currency": "RUB",
        "salary_gross": False,
        "work_formats": ("remote",),
        "short_description": "FastAPI, PostgreSQL",
    }
    values.update(overrides)
    return VacancyData(**values)  # type: ignore[arg-type]


def collector(
    session: AsyncSession, adapter: FakeAdapter, queue: FakeTaskQueue | None = None
) -> CollectorService:
    return CollectorService(session, adapter, queue or FakeTaskQueue())


async def get_source(session: AsyncSession, code: str = "getmatch") -> Source:
    """Свежее состояние источника из БД (после commit в тестируемом коде)."""
    source = await session.get(Source, code)
    assert source is not None
    await session.refresh(source)
    return source

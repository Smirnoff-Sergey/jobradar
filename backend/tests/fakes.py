import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ExternalServiceError
from app.db.models import Evaluation, Resume, SearchProfile, Source, User, Vacancy
from app.llm.base import LLMResponse
from app.llm.prompts import PROMPT_VERSION
from app.repositories.vacancies import VacancyRepository
from app.services.collector import CollectorService
from app.services.filtering import VacancyFilterService
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
    evaluations: list[tuple[int, int, bool]] = field(default_factory=list)
    statuses: dict[str, TaskStatus] = field(default_factory=dict)

    async def collect_source(self, source_code: str) -> str:
        self.collected.append(source_code)
        return f"collect-{len(self.collected)}"

    async def fetch_details(self, vacancy_ids: Sequence[int]) -> None:
        self.details.extend(vacancy_ids)

    async def refilter_user(self, user_id: int) -> str:
        self.refiltered.append(user_id)
        return f"refilter-{len(self.refiltered)}"

    async def evaluate_vacancy(
        self, vacancy_id: int, resume_id: int, *, force: bool = False
    ) -> str:
        self.evaluations.append((vacancy_id, resume_id, force))
        return f"evaluate-{len(self.evaluations)}"

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


def llm_answer(score: int = 85, verdict: str = "apply", **overrides: object) -> dict[str, object]:
    """Ответ модели по схеме EvaluationResult."""
    answer: dict[str, object] = {
        "score": score,
        "verdict": verdict,
        "matches": [{"requirement": "Python", "evidence": "4 года Python"}],
        "gaps": [{"requirement": "Kafka", "severity": "minor"}],
        "dealbreakers": [],
    }
    answer.update(overrides)
    return answer


def completion_body(
    content: object, *, model: str = "m:free", cost: float | None = 0
) -> dict[str, Any]:
    """Тело ответа OpenRouter chat completions."""
    usage: dict[str, Any] = {"prompt_tokens": 120, "completion_tokens": 40}
    if cost is not None:
        usage["cost"] = cost
    return {
        "model": model,
        "choices": [{"message": {"content": json.dumps(content)}}],
        "usage": usage,
    }


@dataclass
class FakeLLM:
    """Отдаёт заранее заданные ответы по очереди; исключение в списке — бросает его.

    on_call выполняется перед ответом — чтобы смоделировать изменения «во время запроса».
    """

    answers: list[dict[str, object] | Exception] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    on_call: Callable[[], Awaitable[None]] | None = None

    async def complete_json(
        self, *, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> LLMResponse:
        self.prompts.append(user)
        if self.on_call is not None:
            await self.on_call()
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return LLMResponse(
            content=answer,
            model="fake/model:free",
            tokens_in=100,
            tokens_out=50,
            cost_usd=Decimal(0),
        )


async def ready_vacancy(session: AsyncSession, user: User, external_id: str = "1") -> Vacancy:
    """Вакансия, готовая к оценке: прошла фильтр, описание загружено, у пользователя есть
    активное резюме. Без полного сбора — иначе коллектор погасил бы прежние вакансии."""
    profile = await session.scalar(select(SearchProfile).where(SearchProfile.user_id == user.id))
    if profile is None:
        profile = SearchProfile(user_id=user.id)
        session.add(profile)
    if await session.scalar(select(Resume).where(Resume.user_id == user.id)) is None:
        session.add(Resume(user_id=user.id, title="Резюме", text="Python-разработчик, 4 года"))
    [vacancy_id] = await VacancyRepository(session).upsert_many("getmatch", [vacancy(external_id)])
    await VacancyFilterService(session).apply(profile, [vacancy_id])
    found = await session.get(Vacancy, vacancy_id)
    assert found is not None
    found.description = "<p>Нужен Python и PostgreSQL</p>"
    found.description_fetched_at = datetime.now(UTC)
    await session.commit()
    return found


async def active_resume(session: AsyncSession, user: User) -> Resume:
    resume = await session.scalar(select(Resume).where(Resume.user_id == user.id, Resume.is_active))
    assert resume is not None
    return resume


async def add_evaluation(
    session: AsyncSession, vacancy_id: int, resume_id: int, **fields: object
) -> Evaluation:
    """Готовая оценка текущей версии промпта (по умолчанию — apply, 85 баллов)."""
    values: dict[str, object] = {
        "status": "done",
        "score": 85,
        "verdict": "apply",
        "matches": [{"requirement": "Python", "evidence": "4 года"}],
        "gaps": [],
        "dealbreakers": [],
    }
    values.update(fields)
    evaluation = Evaluation(
        vacancy_id=vacancy_id, resume_id=resume_id, prompt_version=PROMPT_VERSION, **values
    )
    session.add(evaluation)
    await session.commit()
    return evaluation

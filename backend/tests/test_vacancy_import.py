from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LLMSettings
from app.core.errors import (
    ConflictError,
    InvalidUrlError,
    NotFoundError,
    PermanentExternalError,
)
from app.core.http import RetryPolicy
from app.db.models import SearchProfile, Source, User, Vacancy, VacancyFilterResult
from app.services.vacancy_import import VacancyImportService
from app.sources.base import ImportedVacancy, SourceAdapter
from app.sources.getmatch import OFFERS_URL, GetmatchAdapter
from app.sources.registry import parse_vacancy_url
from tests.fakes import FakeTaskQueue, load_getmatch_fixture, ready_vacancy, vacancy

LLM = LLMSettings(api_key="test-key", daily_request_limit=10)
URL = "https://getmatch.ru/vacancies/7-python-developer"


@dataclass
class FakeImporter:
    """Адаптер с загрузкой одной вакансии; запоминает запрошенные id."""

    result: ImportedVacancy | Exception
    code: str = "getmatch"
    requested: list[str] = field(default_factory=list)

    async def fetch_vacancy(self, external_id: str) -> ImportedVacancy:
        self.requested.append(external_id)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def imported(
    description: str | None = "<p>Полное описание</p>", **overrides: Any
) -> ImportedVacancy:
    return ImportedVacancy(data=vacancy("7", **overrides), description=description)


def service(
    session: AsyncSession, adapter: object, queue: FakeTaskQueue | None = None
) -> VacancyImportService:
    def factory(code: str) -> SourceAdapter:
        return adapter  # type: ignore[return-value]

    return VacancyImportService(session, factory, queue or FakeTaskQueue(), LLM)


async def seed_profile_and_resume(session: AsyncSession, user: User) -> None:
    """Профиль поиска и активное резюме — через ready_vacancy (её вакансия тесту не мешает)."""
    await ready_vacancy(session, user, external_id="other")


# --- ссылки ---


@pytest.mark.parametrize(
    "url",
    [
        "https://getmatch.ru/vacancies/36738-data-scientist-fast-track",
        "http://www.getmatch.ru/vacancies/36738",
        " https://getmatch.ru/vacancies/36738-x/?utm_source=tg ",
        "https://getmatch.ru/vacancies/36738#apply",
    ],
)
def test_parse_getmatch_url(url: str) -> None:
    assert parse_vacancy_url(url) == ("getmatch", "36738")


@pytest.mark.parametrize(
    "url",
    [
        "https://hh.ru/vacancy/123",
        "https://getmatch.ru/companies/36738",
        "https://getmatch.ru.evil.com/vacancies/1",
        "getmatch.ru/vacancies/1",
        "https://getmatch.ru/vacancies/١٢٣",  # не ASCII-цифры
    ],
)
def test_unsupported_url(url: str) -> None:
    with pytest.raises(InvalidUrlError):
        parse_vacancy_url(url)


# --- карточка getmatch ---


@respx.mock
async def test_getmatch_fetch_vacancy() -> None:
    card = {**load_getmatch_fixture()["offers"][0], "description": "<p>Полное</p>"}
    respx.get(f"{OFFERS_URL}/101").mock(return_value=httpx.Response(200, json=card))

    async with httpx.AsyncClient() as client:
        result = await GetmatchAdapter(client, RetryPolicy(max_attempts=1)).fetch_vacancy("101")

    assert result.data.external_id == "101"
    assert result.data.title == "Python Backend Developer"
    assert result.description == "<p>Полное</p>"
    assert result.is_active


@respx.mock
async def test_getmatch_fetch_closed_and_broken_cards() -> None:
    offer = load_getmatch_fixture()["offers"][0]
    respx.get(f"{OFFERS_URL}/1").mock(
        return_value=httpx.Response(200, json={**offer, "is_active": False})
    )
    respx.get(f"{OFFERS_URL}/2").mock(return_value=httpx.Response(200, json={"id": 2}))
    respx.get(f"{OFFERS_URL}/3").mock(return_value=httpx.Response(200, json=[1, 2]))

    async with httpx.AsyncClient() as client:
        adapter = GetmatchAdapter(client, RetryPolicy(max_attempts=1))
        assert not (await adapter.fetch_vacancy("1")).is_active
        with pytest.raises(PermanentExternalError):
            await adapter.fetch_vacancy("2")
        with pytest.raises(PermanentExternalError):
            await adapter.fetch_vacancy("3")


# --- сервис ---


async def test_import_saves_filters_and_queues_evaluation(
    db_session: AsyncSession, user: User
) -> None:
    await seed_profile_and_resume(db_session, user)
    queue = FakeTaskQueue()
    adapter = FakeImporter(imported())

    vacancy_id = await service(db_session, adapter, queue).import_url(user.id, URL)

    saved = await db_session.get(Vacancy, vacancy_id)
    assert saved is not None
    assert (saved.external_id, saved.description) == ("7", "<p>Полное описание</p>")
    assert saved.description_fetched_at is not None
    decision = await db_session.get(VacancyFilterResult, (vacancy_id, user.id))
    assert decision is not None and decision.passed
    assert [pair[0] for pair in queue.evaluations] == [vacancy_id]
    assert queue.details == []
    assert adapter.requested == ["7"]


async def test_repeat_import_does_not_duplicate(db_session: AsyncSession, user: User) -> None:
    await seed_profile_and_resume(db_session, user)
    adapter = FakeImporter(imported())

    first = await service(db_session, adapter).import_url(user.id, URL)
    second = await service(db_session, adapter).import_url(user.id, URL)

    assert first == second
    count = await db_session.scalar(
        select(func.count()).select_from(Vacancy).where(Vacancy.external_id == "7")
    )
    assert count == 1


async def test_rejected_vacancy_is_imported_but_not_evaluated(
    db_session: AsyncSession, user: User
) -> None:
    await seed_profile_and_resume(db_session, user)
    await db_session.execute(
        update(SearchProfile).where(SearchProfile.user_id == user.id).values(remote_only=True)
    )
    queue = FakeTaskQueue()

    vacancy_id = await service(
        db_session, FakeImporter(imported(work_formats=("office",))), queue
    ).import_url(user.id, URL)

    decision = await db_session.get(VacancyFilterResult, (vacancy_id, user.id))
    assert decision is not None and not decision.passed
    assert queue.evaluations == []


async def test_card_without_description_queues_details(
    db_session: AsyncSession, user: User
) -> None:
    queue = FakeTaskQueue()

    vacancy_id = await service(db_session, FakeImporter(imported(None)), queue).import_url(
        user.id, URL
    )

    assert queue.details == [vacancy_id]


@pytest.mark.parametrize(
    ("adapter", "error", "message"),
    [
        (FakeImporter(PermanentExternalError("404")), NotFoundError, "Не удалось загрузить"),
        (
            FakeImporter(ImportedVacancy(data=vacancy("7"), description=None, is_active=False)),
            ConflictError,
            "снята",
        ),
        (object(), InvalidUrlError, "не умеет"),
    ],
)
async def test_import_errors(
    db_session: AsyncSession, user: User, adapter: object, error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        await service(db_session, adapter).import_url(user.id, URL)


async def test_import_from_disabled_source(db_session: AsyncSession, user: User) -> None:
    await db_session.execute(update(Source).values(is_enabled=False))

    with pytest.raises(ConflictError, match="выключен"):
        await service(db_session, FakeImporter(imported())).import_url(user.id, URL)


async def test_id_is_taken_from_card(db_session: AsyncSession, user: User) -> None:
    # В ссылке id с ведущими нулями, в карточке — каноничный.
    vacancy_id = await service(db_session, FakeImporter(imported())).import_url(
        user.id, "https://getmatch.ru/vacancies/0007-python"
    )

    saved = await db_session.get(Vacancy, vacancy_id)
    assert saved is not None and saved.external_id == "7"


# --- API ---


@respx.mock
async def test_import_api(
    client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    card = {**load_getmatch_fixture()["offers"][0], "description": "<p>Полное</p>"}
    respx.get(f"{OFFERS_URL}/101").mock(return_value=httpx.Response(200, json=card))

    response = await client.post(
        "/api/v1/vacancies/import",
        json={"url": "https://getmatch.ru/vacancies/101-python-backend-developer"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Python Backend Developer"
    assert body["description"] == "<p>Полное</p>"


async def test_import_api_rejects_foreign_url(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/vacancies/import", json={"url": "https://hh.ru/vacancy/1"}, headers=auth_headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_url"

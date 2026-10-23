import json
import logging

import pytest
import structlog
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LLMSettings
from app.core.logging import configure_logging
from app.db.models import Source, User
from app.repositories.sources import SourceRepository
from app.services.applications import ApplicationService
from app.services.letters import LetterScheduler, LetterService
from app.services.metrics import render_metrics
from tests.fakes import FakeLLM, FakeTaskQueue, active_resume, add_evaluation, ready_vacancy

LLM = LLMSettings(api_key="test-key", daily_request_limit=10)


def sample(text: str, name: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(name)]


async def test_metrics_show_service_state(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    target = await ready_vacancy(db_session, user)
    await add_evaluation(db_session, target.id, (await active_resume(db_session, user)).id)
    await ApplicationService(db_session).set_status(user.id, target.id, "applied")
    source = await db_session.get(Source, "getmatch")
    assert source is not None
    source.finish_run("failed", error="сбой")
    await SourceRepository(db_session).count_failure("getmatch")
    await db_session.commit()

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    text = response.text
    assert 'jobradar_vacancies{active="true",source="getmatch"} 1.0' in text
    assert 'jobradar_source_failed_runs_total{source="getmatch"} 1.0' in text
    assert 'jobradar_source_last_run_success{source="getmatch"} 0.0' in text
    assert 'jobradar_applications{status="applied"} 1.0' in text
    assert sample(text, 'jobradar_llm_results{kind="evaluation",model="none",status="done"}')
    assert "jobradar_llm_daily_limit" in text


async def test_metrics_count_letters(db_session: AsyncSession, user: User) -> None:
    target = await ready_vacancy(db_session, user)
    letter, _ = await LetterScheduler(db_session, FakeTaskQueue(), LLM).request_letter(
        user.id, target.id
    )
    answer: dict[str, object] = {
        "text": "Здравствуйте!",
        "facts": [{"claim": "Python", "resume_fragment": 1}],
    }
    await LetterService(db_session, LLM, FakeLLM([answer])).generate(letter.id)

    text = (await render_metrics(db_session, LLM)).decode()

    assert 'jobradar_llm_results{kind="letter",model="fake/model:free",status="done"} 1.0' in text
    assert (
        'jobradar_llm_tokens{direction="in",kind="letter",model="fake/model:free",status="done"}'
        " 100.0" in text
    )


async def test_api_latency_is_measured_by_route_template(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await client.get("/api/v1/vacancies/12345", headers=auth_headers)
    await client.get("/no-such-path")

    text = (await client.get("/metrics")).text

    assert sample(
        text,
        'jobradar_http_request_duration_seconds_count{method="GET",'
        'route="/api/v1/vacancies/{vacancy_id}",status="404"}',
    )
    assert sample(
        text, 'jobradar_http_request_duration_seconds_count{method="GET",route="unmatched"'
    )
    assert "12345" not in text  # путь с id в метки не попадает


async def test_metrics_without_runs(client: AsyncClient, db_session: AsyncSession) -> None:
    await db_session.execute(update(Source).values(last_run_status=None))

    text = (await client.get("/metrics")).text

    assert 'jobradar_source_failed_runs_total{source="getmatch"} 0.0' in text
    assert not sample(text, "jobradar_source_last_run_success{")


async def test_request_id_is_returned_and_validated(client: AsyncClient) -> None:
    own = await client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    forged = await client.get("/api/v1/health", headers={"X-Request-ID": "bad id\n"})

    assert own.headers["X-Request-ID"] == "abc-123"
    assert forged.headers["X-Request-ID"] != "bad id\n"
    assert len(forged.headers["X-Request-ID"]) == 32


def test_json_logs_carry_context(capsys: pytest.CaptureFixture[str]) -> None:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        configure_logging("INFO", "json")
        structlog.contextvars.bind_contextvars(task_id="t-1")
        logging.getLogger("app.test").info("Собрано %d вакансий", 3)
    finally:
        structlog.contextvars.clear_contextvars()
        root.handlers, root.level = handlers, level

    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["event"] == "Собрано 3 вакансий"
    assert record["task_id"] == "t-1"
    assert record["level"] == "info"
    assert record["logger"] == "app.test"

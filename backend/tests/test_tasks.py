"""Задачи Celery целиком: настоящий asyncio.run, своя сессия БД, замоканный getmatch.

Задачи сами делают commit, поэтому здесь нет отката транзакции — после теста таблицы чистятся.
"""

import asyncio
import json
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import respx
from aiogram import Bot
from aiogram.methods import DeleteWebhook, SetWebhook
from celery import Celery
from celery.schedules import crontab
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app import cli
from app.core.config import CollectorSettings, get_settings
from app.core.errors import NotFoundError
from app.services.queue import TaskStatus
from app.sources.getmatch import OFFERS_URL, GetmatchAdapter
from app.sources.registry import create_adapter
from app.tasks import jobs
from app.tasks.celery_app import celery_app, cron_schedule
from app.tasks.names import COLLECT_SOURCE, DETAILS_QUEUE, FETCH_DETAILS, REFILTER_USER
from app.tasks.queue import CeleryTaskQueue
from app.telegram.client import AiogramTelegramClient
from tests.conftest import TEST_DATABASE_URL_ENV
from tests.fakes import (
    BOT_USERNAME,
    CHAT_ID,
    TEST_BOT_TOKEN,
    FakeTaskQueue,
    FakeTelegram,
    RecordingSession,
    completion_body,
    llm_answer,
    load_getmatch_fixture,
    recording_bot,
)

TASK_USER = "tasks@example.com"


def run_sql(statement: str) -> Any:
    """Выполнить SQL в тестовой БД вне транзакции теста; вернуть первое значение."""

    async def main() -> Any:
        engine = create_async_engine(os.environ[TEST_DATABASE_URL_ENV], poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(text(statement))
                return result.scalar() if result.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(main())


@pytest.fixture
def worker_queue(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeTaskQueue]:
    monkeypatch.setenv("JOBRADAR_DATABASE_URL", os.environ[TEST_DATABASE_URL_ENV])
    get_settings.cache_clear()
    queue = FakeTaskQueue()
    monkeypatch.setattr(jobs, "CeleryTaskQueue", lambda: queue)
    try:
        yield queue
    finally:
        get_settings.cache_clear()
        run_sql("DELETE FROM vacancies")
        run_sql(f"DELETE FROM users WHERE email = '{TASK_USER}'")
        run_sql("DELETE FROM llm_daily_usage")
        run_sql(
            "UPDATE sources SET last_run_status = NULL, last_run_finished_at = NULL,"
            " last_run_stats = NULL, last_error = NULL"
        )


@respx.mock
def test_collect_source_task(worker_queue: FakeTaskQueue) -> None:
    respx.get(OFFERS_URL).respond(json=load_getmatch_fixture())

    stats = jobs.collect_source.run("getmatch")

    assert stats == {
        "status": "success",
        "received": 2,
        "changed": 2,
        "deactivated": 0,
        "deactivation_skipped": False,
        "details_queued": 0,  # профилей поиска нет — фильтровать не для кого
    }
    assert run_sql("SELECT last_run_status FROM sources WHERE code = 'getmatch'") == "success"


@respx.mock
def test_fetch_details_task(worker_queue: FakeTaskQueue) -> None:
    respx.get(OFFERS_URL).respond(json=load_getmatch_fixture())
    respx.get(f"{OFFERS_URL}/101").respond(json={"description": "<p>Полный текст</p>"})
    jobs.collect_source.run("getmatch")
    vacancy_id = run_sql("SELECT id FROM vacancies WHERE external_id = '101'")

    assert jobs.fetch_details.run(vacancy_id) is True
    assert jobs.fetch_details.run(vacancy_id) is False
    assert run_sql(f"SELECT description FROM vacancies WHERE id = {vacancy_id}") == (
        "<p>Полный текст</p>"
    )


def test_refilter_task_without_profile(worker_queue: FakeTaskQueue) -> None:
    assert jobs.refilter_user.run(999_999) == 0


def test_beat_schedules_every_source() -> None:
    entry = celery_app.conf.beat_schedule["collect-getmatch"]

    assert entry["task"] == COLLECT_SOURCE
    assert entry["args"] == ("getmatch",)
    assert entry["schedule"] == cron_schedule(CollectorSettings().schedule_cron)


def test_cron_schedule() -> None:
    assert cron_schedule("*/15 9-18 * * 1-5") == crontab(
        minute="*/15", hour="9-18", day_of_week="1-5"
    )


def test_details_go_to_own_queue() -> None:
    assert celery_app.conf.task_routes[FETCH_DETAILS] == {"queue": DETAILS_QUEUE}


def test_invalid_cron_is_rejected() -> None:
    with pytest.raises(ValueError, match="полей"):
        CollectorSettings(schedule_cron="0 * *")


def test_create_adapter() -> None:
    settings = CollectorSettings()

    assert isinstance(create_adapter("getmatch", None, settings), GetmatchAdapter)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        create_adapter("unknown", None, settings)  # type: ignore[arg-type]


class RecordingCelery:
    def __init__(self) -> None:
        self.sent: list[tuple[str, list[object]]] = []

    def send_task(self, name: str, args: list[object]) -> SimpleNamespace:
        self.sent.append((name, args))
        return SimpleNamespace(id=f"task-{len(self.sent)}")


async def test_celery_queue_sends_tasks_by_name() -> None:
    app = RecordingCelery()
    queue = CeleryTaskQueue(app)  # type: ignore[arg-type]

    assert await queue.collect_source("getmatch") == "task-1"
    await queue.fetch_details([10, 11])
    assert await queue.refilter_user(5) == "task-4"

    assert app.sent == [
        (COLLECT_SOURCE, ["getmatch"]),
        (FETCH_DETAILS, [10]),
        (FETCH_DETAILS, [11]),
        (REFILTER_USER, [5]),
    ]


async def test_celery_queue_reads_status() -> None:
    app = Celery("test", backend="cache+memory://")
    app.backend.store_result("ok", {"status": "success"}, "SUCCESS")
    app.backend.store_result("bad", ValueError("сбой"), "FAILURE")
    queue = CeleryTaskQueue(app)

    assert await queue.status("ok") == TaskStatus("ok", "SUCCESS", result={"status": "success"})
    assert await queue.status("waiting") == TaskStatus("waiting", "PENDING")
    failed = await queue.status("bad")
    assert failed.state == "FAILURE"
    assert failed.error is not None
    assert "сбой" in failed.error


@respx.mock
def test_evaluation_pipeline(
    worker_queue: FakeTaskQueue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Сбор → описание → постановка оценки → оценка через (замоканный) OpenRouter."""
    monkeypatch.setenv("JOBRADAR_LLM__API_KEY", "test-key")
    get_settings.cache_clear()
    user_id = run_sql(
        f"INSERT INTO users (email, password_hash) VALUES ('{TASK_USER}', 'x') RETURNING id"
    )
    run_sql(f"INSERT INTO search_profiles (user_id) VALUES ({user_id})")
    resume_file = tmp_path / "resume.txt"
    resume_file.write_text("Python-разработчик, 4 года, Django, PostgreSQL", encoding="utf-8")
    assert cli.main(["load-resume", "--email", TASK_USER, "--file", str(resume_file)]) == 0
    resume_id = run_sql(f"SELECT id FROM resumes WHERE user_id = {user_id}")

    respx.get(OFFERS_URL).respond(json=load_getmatch_fixture())
    respx.get(f"{OFFERS_URL}/101").respond(json={"description": "<p>Python, PostgreSQL</p>"})
    llm_route = respx.post(f"{get_settings().llm.base_url}/chat/completions").respond(
        json=completion_body(llm_answer())
    )
    jobs.collect_source.run("getmatch")
    vacancy_id = run_sql("SELECT id FROM vacancies WHERE external_id = '101'")

    assert jobs.fetch_details.run(vacancy_id) is True
    assert worker_queue.evaluations == [(vacancy_id, resume_id, False)]
    assert jobs.evaluate_pair.run(vacancy_id, resume_id) == "done"
    assert run_sql(f"SELECT verdict FROM evaluations WHERE vacancy_id = {vacancy_id}") == "apply"
    assert run_sql("SELECT requests FROM llm_daily_usage") == 1

    worker_queue.evaluations.clear()
    jobs.evaluate_pending.run()
    assert (vacancy_id, resume_id, False) not in worker_queue.evaluations

    out = tmp_path / "eval.jsonl"
    assert cli.main(["export-eval-set", "--out", str(out), "--limit", "5"]) == 0
    exported = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert exported[0]["id"] == "getmatch:101"
    assert exported[0]["label"] == ""

    # Невалидный JSON от модели при переоценке: воркер не падает, оценка — failed.
    llm_route.respond(json=completion_body("не JSON-объект"))
    assert jobs.evaluate_pair.run(vacancy_id, resume_id, True) == "failed"


def test_evaluate_task_disabled_without_key() -> None:
    assert jobs.evaluate_pair.run(1, 1) == "disabled"


def test_notify_task_disabled_without_token() -> None:
    assert jobs.notify_vacancy.run(1, 1) == "disabled"


@respx.mock
def test_notification_pipeline(
    worker_queue: FakeTaskQueue, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Оценка «apply» → постановка уведомления → отправка ровно один раз."""
    monkeypatch.setenv("JOBRADAR_LLM__API_KEY", "test-key")
    monkeypatch.setenv("JOBRADAR_TELEGRAM__BOT_TOKEN", TEST_BOT_TOKEN)
    get_settings.cache_clear()
    telegram = FakeTelegram()

    @asynccontextmanager
    async def fake_client() -> AsyncIterator[FakeTelegram]:
        yield telegram

    monkeypatch.setattr(jobs, "telegram_client", fake_client)
    user_id = run_sql(
        "INSERT INTO users (email, password_hash, telegram_chat_id, telegram_linked_at)"
        f" VALUES ('{TASK_USER}', 'x', {CHAT_ID}, now() - interval '1 day') RETURNING id"
    )
    run_sql(f"INSERT INTO search_profiles (user_id) VALUES ({user_id})")
    resume_file = tmp_path / "resume.txt"
    resume_file.write_text("Python-разработчик, 4 года, Django, PostgreSQL", encoding="utf-8")
    assert cli.main(["load-resume", "--email", TASK_USER, "--file", str(resume_file)]) == 0
    resume_id = run_sql(f"SELECT id FROM resumes WHERE user_id = {user_id}")
    respx.get(OFFERS_URL).respond(json=load_getmatch_fixture())
    respx.get(f"{OFFERS_URL}/101").respond(json={"description": "<p>Python, PostgreSQL</p>"})
    respx.post(f"{get_settings().llm.base_url}/chat/completions").respond(
        json=completion_body(llm_answer())
    )
    jobs.collect_source.run("getmatch")
    vacancy_id = run_sql("SELECT id FROM vacancies WHERE external_id = '101'")
    jobs.fetch_details.run(vacancy_id)

    assert jobs.evaluate_pair.run(vacancy_id, resume_id) == "done"
    assert worker_queue.notifications == [(user_id, vacancy_id)]
    assert jobs.notify_vacancy.run(user_id, vacancy_id) == "sent"
    assert jobs.notify_vacancy.run(user_id, vacancy_id) == "skipped"
    assert jobs.notify_pending.run() == 0
    [(chat_id, message)] = telegram.sent
    assert chat_id == CHAT_ID
    assert "Оценка: <b>85</b>/100" in message.text


def test_telegram_cli(
    worker_queue: FakeTaskQueue, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("JOBRADAR_TELEGRAM__BOT_TOKEN", TEST_BOT_TOKEN)
    monkeypatch.setenv("JOBRADAR_TELEGRAM__WEBHOOK_SECRET", "cli-secret")
    get_settings.cache_clear()
    session = RecordingSession()

    @asynccontextmanager
    async def fake_bot(_: object) -> AsyncIterator[Bot]:
        yield recording_bot(session)

    @asynccontextmanager
    async def fake_client(_: object) -> AsyncIterator[AiogramTelegramClient]:
        yield AiogramTelegramClient(recording_bot(session))

    monkeypatch.setattr(cli, "open_bot", fake_bot)
    monkeypatch.setattr(cli, "open_telegram_client", fake_client)
    run_sql(f"INSERT INTO users (email, password_hash) VALUES ('{TASK_USER}', 'x')")

    assert cli.main(["telegram-link", "--email", TASK_USER]) == 0
    assert f"https://t.me/{BOT_USERNAME}?start=" in capsys.readouterr().out
    assert run_sql(
        f"SELECT telegram_link_code_hash IS NOT NULL FROM users WHERE email = '{TASK_USER}'"
    )
    assert cli.main(["telegram-link", "--email", "nobody@example.com"]) == 1

    assert cli.main(["telegram-webhook", "--url", "https://example.com/hook"]) == 0
    [webhook] = session.calls(SetWebhook)
    assert (webhook.url, webhook.secret_token) == ("https://example.com/hook", "cli-secret")
    assert cli.main(["telegram-webhook", "--delete"]) == 0
    assert len(session.calls(DeleteWebhook)) == 1

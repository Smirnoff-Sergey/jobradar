"""Привязка чата, обработчики бота (через диспетчер aiogram без сети) и вебхук API."""

from collections.abc import Iterator
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, DeleteWebhook, EditMessageReplyMarkup, SendMessage
from aiogram.types import Update
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import bot as bot_main
from app.api.deps import get_telegram_client
from app.core.config import TelegramSettings, get_settings
from app.db.models import Application, User
from app.services.applications import ApplicationService
from app.services.auth import AuthService
from app.services.telegram_link import TelegramLinkService
from app.telegram.handlers import BAD_CODE, CHAT_NOT_LINKED, LINKED, create_dispatcher
from app.telegram.messages import vacancy_keyboard
from tests.conftest import WEBHOOK_SECRET
from tests.fakes import (
    BOT_USERNAME,
    CHAT_ID,
    FakeTelegram,
    RecordingSession,
    link_chat,
    ready_vacancy,
    recording_bot,
)

SETTINGS = TelegramSettings(bot_token="42:test-token")


def link_service(session: AsyncSession, **overrides: object) -> TelegramLinkService:
    return TelegramLinkService(session, SETTINGS.model_copy(update=overrides))


def code_from(url: str) -> str:
    return parse_qs(urlparse(url).query)["start"][0]


async def issue_code(session: AsyncSession, user: User, **overrides: object) -> str:
    link = await link_service(session, **overrides).issue_link(user.id, FakeTelegram())
    assert link.url.startswith(f"https://t.me/{BOT_USERNAME}?start=")
    return code_from(link.url)


# --- привязка чата


async def test_code_links_chat_once(db_session: AsyncSession, user: User) -> None:
    code = await issue_code(db_session, user)

    linked = await link_service(db_session).link(code, CHAT_ID)

    assert linked is not None
    assert (linked.id, linked.telegram_chat_id) == (user.id, CHAT_ID)
    assert linked.telegram_linked_at is not None
    assert linked.telegram_link_code_hash is None  # код не хранится открытым и гасится
    assert await link_service(db_session).link(code, CHAT_ID) is None


async def test_wrong_or_expired_code(db_session: AsyncSession, user: User) -> None:
    code = await issue_code(db_session, user, link_code_ttl_minutes=-1)

    assert await link_service(db_session).link(code, CHAT_ID) is None
    assert await link_service(db_session).link("no-such-code", CHAT_ID) is None


async def test_new_code_replaces_old(db_session: AsyncSession, user: User) -> None:
    old = await issue_code(db_session, user)
    new = await issue_code(db_session, user)

    assert await link_service(db_session).link(old, CHAT_ID) is None
    assert await link_service(db_session).link(new, CHAT_ID) is not None


async def test_chat_moves_to_another_user(
    db_session: AsyncSession, user: User, auth_service: AuthService
) -> None:
    await link_chat(db_session, user)
    other = await auth_service.create_user("other@example.com", "other-password")

    await link_service(db_session).link(await issue_code(db_session, other), CHAT_ID)

    await db_session.refresh(user)
    assert user.telegram_chat_id is None
    assert other.telegram_chat_id == CHAT_ID


async def test_unlink(db_session: AsyncSession, user: User) -> None:
    await link_chat(db_session, user)

    assert await link_service(db_session).unlink_chat(CHAT_ID) is True
    assert await link_service(db_session).unlink_chat(CHAT_ID) is False
    await db_session.refresh(user)
    assert (user.telegram_chat_id, user.telegram_linked_at) == (None, None)


# --- обработчики


@pytest.fixture
def telegram_session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
def bot(telegram_session: RecordingSession) -> Bot:
    return recording_bot(telegram_session)


@pytest.fixture
def dispatcher(db_session: AsyncSession) -> Dispatcher:
    return create_dispatcher(lambda: nullcontext(db_session), SETTINGS)


def message_update(text: str, chat_id: int = CHAT_ID) -> dict[str, Any]:
    command = text.split()[0]
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False, "first_name": "Тест"},
            "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": len(command)}],
        },
    }


def button_update(vacancy_id: int, status: str, chat_id: int = CHAT_ID) -> dict[str, Any]:
    keyboard = vacancy_keyboard(vacancy_id, "https://example.com/v", None)
    return {
        "update_id": 2,
        "callback_query": {
            "id": "query-1",
            "from": {"id": chat_id, "is_bot": False, "first_name": "Тест"},
            "chat_instance": "instance",
            "data": f"app:{vacancy_id}:{status}",
            "message": {
                "message_id": 11,
                "date": 0,
                "chat": {"id": chat_id, "type": "private"},
                "text": "Вакансия",
                "reply_markup": keyboard.model_dump(exclude_none=True),
            },
        },
    }


async def feed(dispatcher: Dispatcher, bot: Bot, data: dict[str, Any]) -> None:
    await dispatcher.feed_update(bot, Update.model_validate(data, context={"bot": bot}))


def answers(session: RecordingSession) -> list[str]:
    return [call.text for call in session.calls(SendMessage)]


async def test_start_with_code_links_chat(
    db_session: AsyncSession,
    user: User,
    bot: Bot,
    dispatcher: Dispatcher,
    telegram_session: RecordingSession,
) -> None:
    code = await issue_code(db_session, user)

    await feed(dispatcher, bot, message_update(f"/start {code}"))
    await feed(dispatcher, bot, message_update(f"/start {code}"))
    await feed(dispatcher, bot, message_update("/start"))

    await db_session.refresh(user)
    assert user.telegram_chat_id == CHAT_ID
    assert answers(telegram_session)[:2] == [LINKED, BAD_CODE]
    assert "ссылку привязки" in answers(telegram_session)[2]


async def test_stop_unlinks(
    db_session: AsyncSession,
    user: User,
    bot: Bot,
    dispatcher: Dispatcher,
    telegram_session: RecordingSession,
) -> None:
    await link_chat(db_session, user)

    await feed(dispatcher, bot, message_update("/stop"))
    await feed(dispatcher, bot, message_update("/stop"))

    await db_session.refresh(user)
    assert user.telegram_chat_id is None
    assert answers(telegram_session)[1] == CHAT_NOT_LINKED


async def test_button_sets_status_and_marks_it(
    db_session: AsyncSession,
    user: User,
    bot: Bot,
    dispatcher: Dispatcher,
    telegram_session: RecordingSession,
) -> None:
    await link_chat(db_session, user)
    target = await ready_vacancy(db_session, user)

    await feed(dispatcher, bot, button_update(target.id, "applied"))

    application = await db_session.scalar(select(Application))
    assert application is not None
    assert (application.user_id, application.status) == (user.id, "applied")
    [edit] = telegram_session.calls(EditMessageReplyMarkup)
    assert edit.reply_markup.inline_keyboard[0][0].text == "✓ Откликнусь"
    [answer] = telegram_session.calls(AnswerCallbackQuery)
    assert answer.text == "Статус: откликнулся"


async def test_same_button_twice_is_not_an_error(
    db_session: AsyncSession, user: User, dispatcher: Dispatcher
) -> None:
    await link_chat(db_session, user)
    target = await ready_vacancy(db_session, user)
    session = RecordingSession(
        errors={
            EditMessageReplyMarkup: TelegramBadRequest(
                EditMessageReplyMarkup(), "Bad Request: message is not modified"
            )
        }
    )

    await feed(dispatcher, recording_bot(session), button_update(target.id, "declined"))

    assert [call.text for call in session.calls(AnswerCallbackQuery)] == ["Статус: не подходит"]


async def test_button_does_not_override_later_status(
    db_session: AsyncSession,
    user: User,
    bot: Bot,
    dispatcher: Dispatcher,
    telegram_session: RecordingSession,
) -> None:
    """Кнопка в старом сообщении не откатывает «пригласили», выставленное через API."""
    await link_chat(db_session, user)
    target = await ready_vacancy(db_session, user)
    await ApplicationService(db_session).set_status(user.id, target.id, "invited")

    await feed(dispatcher, bot, button_update(target.id, "declined"))

    application = await db_session.scalar(select(Application))
    assert application is not None
    await db_session.refresh(application)
    assert application.status == "invited"
    [answer] = telegram_session.calls(AnswerCallbackQuery)
    assert answer.text == "Статус уже «пригласили», меняйте его в JobRadar"
    assert telegram_session.calls(EditMessageReplyMarkup) == []


async def test_failed_mark_still_answers(
    db_session: AsyncSession, user: User, dispatcher: Dispatcher
) -> None:
    """Статус сохранён, а отметить кнопку не вышло — пользователь всё равно получает ответ."""
    await link_chat(db_session, user)
    target = await ready_vacancy(db_session, user)
    session = RecordingSession(
        errors={
            EditMessageReplyMarkup: TelegramBadRequest(
                EditMessageReplyMarkup(), "Bad Request: message to edit not found"
            )
        }
    )

    await feed(dispatcher, recording_bot(session), button_update(target.id, "applied"))

    assert [call.text for call in session.calls(AnswerCallbackQuery)] == ["Статус: откликнулся"]
    assert await db_session.scalar(select(Application.status)) == "applied"


async def test_button_from_unknown_chat(
    db_session: AsyncSession,
    user: User,
    bot: Bot,
    dispatcher: Dispatcher,
    telegram_session: RecordingSession,
) -> None:
    target = await ready_vacancy(db_session, user)

    await feed(dispatcher, bot, button_update(target.id, "applied", chat_id=1))
    await link_chat(db_session, user)
    await feed(dispatcher, bot, button_update(999_999, "applied"))

    assert await db_session.scalar(select(Application)) is None
    assert [call.text for call in telegram_session.calls(AnswerCallbackQuery)] == [
        CHAT_NOT_LINKED,
        "Вакансия не найдена",
    ]


# --- API


@pytest.fixture
def webhook_app(
    app: FastAPI, db_session: AsyncSession, telegram_enabled: None, bot: Bot
) -> Iterator[FastAPI]:
    app.state.telegram_bot = bot
    app.state.telegram_dispatcher = create_dispatcher(
        lambda: nullcontext(db_session), get_settings().telegram
    )
    yield app


async def test_webhook_checks_secret(
    client: AsyncClient,
    webhook_app: FastAPI,
    db_session: AsyncSession,
    user: User,
    telegram_session: RecordingSession,
) -> None:
    url = "/api/v1/telegram/webhook"
    code = await issue_code(db_session, user)
    update = message_update(f"/start {code}")

    assert (await client.post(url, json=update)).status_code == 401
    wrong = {"X-Telegram-Bot-Api-Secret-Token": "wrong"}
    assert (await client.post(url, json=update, headers=wrong)).status_code == 401
    assert answers(telegram_session) == []

    good = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}
    assert (await client.post(url, json={"bad": 1}, headers=good)).status_code == 400
    response = await client.post(url, json=update, headers=good)
    assert response.json() == {"ok": True}
    assert answers(telegram_session) == [LINKED]


async def test_webhook_handler_error_still_ok(
    client: AsyncClient, webhook_app: FastAPI, db_session: AsyncSession, user: User
) -> None:
    """Сбой обработчика не возвращается Telegram — иначе он повторял бы доставку."""
    await link_chat(db_session, user)
    target = await ready_vacancy(db_session, user)
    webhook_app.state.telegram_bot = recording_bot(
        RecordingSession(errors={AnswerCallbackQuery: RuntimeError("сбой")})
    )

    response = await client.post(
        "/api/v1/telegram/webhook",
        json=button_update(target.id, "applied"),
        headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
    )

    assert response.status_code == 200


async def test_webhook_disabled(client: AsyncClient) -> None:
    response = await client.post("/api/v1/telegram/webhook", json=message_update("/start"))

    assert response.status_code == 404


async def test_link_api(
    client: AsyncClient,
    app: FastAPI,
    db_session: AsyncSession,
    user: User,
    auth_headers: dict[str, str],
    telegram_enabled: None,
) -> None:
    app.dependency_overrides[get_telegram_client] = lambda: FakeTelegram()

    response = await client.post("/api/v1/telegram/link", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert timedelta(minutes=14) < expires_at - datetime.now(UTC) <= timedelta(minutes=15)
    assert await link_service(db_session).link(code_from(body["url"]), CHAT_ID) is not None

    assert (await client.delete("/api/v1/telegram/link", headers=auth_headers)).status_code == 204
    await db_session.refresh(user)
    assert user.telegram_chat_id is None


async def test_link_api_without_token(
    client: AsyncClient, app: FastAPI, auth_headers: dict[str, str]
) -> None:
    app.dependency_overrides[get_telegram_client] = lambda: FakeTelegram()

    response = await client.post("/api/v1/telegram/link", headers=auth_headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "telegram_disabled"


def test_webhook_mode_needs_secret() -> None:
    with pytest.raises(ValueError, match="WEBHOOK_SECRET"):
        TelegramSettings(bot_token="42:x", mode="webhook", webhook_secret="  ")


# --- запуск бота (python -m app.bot)


@pytest.fixture
def no_idle(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    async def idle() -> None:
        calls.append("idle")

    monkeypatch.setattr(bot_main, "idle", idle)
    return calls


def test_bot_without_token_idles(no_idle: list[str]) -> None:
    assert bot_main.main() == 0
    assert no_idle == ["idle"]


def test_bot_in_webhook_mode_idles(no_idle: list[str], telegram_enabled: None) -> None:
    assert bot_main.main() == 0
    assert no_idle == ["idle"]


def test_bot_polls(monkeypatch: pytest.MonkeyPatch, no_idle: list[str]) -> None:
    monkeypatch.setenv("JOBRADAR_TELEGRAM__BOT_TOKEN", "42:test-token")
    get_settings.cache_clear()
    session = RecordingSession()
    polled: list[Bot] = []

    class FakeDispatcher:
        async def start_polling(self, bot: Bot) -> None:
            polled.append(bot)

    monkeypatch.setattr(bot_main, "create_bot", lambda _: recording_bot(session))
    monkeypatch.setattr(bot_main, "create_dispatcher", lambda *_: FakeDispatcher())
    try:
        assert bot_main.main() == 0
    finally:
        get_settings.cache_clear()

    assert len(polled) == 1
    assert len(session.calls(DeleteWebhook)) == 1  # иначе getUpdates не отдаст обновления
    assert no_idle == []

"""Исходящие вызовы Bot API: интерфейс для сервисов и реализация на aiogram.

Сервисы видят только протокол TelegramClient и ошибки проекта — исключения aiogram
переводятся здесь, как ответы HTTP переводятся в core/http.py.
"""

from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import Protocol

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)

from app.core.config import TelegramSettings
from app.core.errors import (
    ChatUnavailableError,
    ExternalAccessError,
    PermanentExternalError,
    TelegramDisabledError,
    TransientExternalError,
)
from app.telegram.messages import OutgoingMessage


class TelegramClient(Protocol):
    async def bot_username(self) -> str: ...

    async def send_message(self, chat_id: int, message: OutgoingMessage) -> int:
        """Отправляет сообщение, возвращает его id."""
        ...


def create_bot(settings: TelegramSettings) -> Bot:
    if settings.bot_token is None:
        raise TelegramDisabledError
    return Bot(
        settings.bot_token.get_secret_value(),
        session=AiohttpSession(timeout=settings.request_timeout_seconds),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


@asynccontextmanager
async def open_bot(settings: TelegramSettings) -> AsyncIterator[Bot]:
    bot = create_bot(settings)
    try:
        yield bot
    finally:
        await bot.session.close()


@asynccontextmanager
async def open_telegram_client(settings: TelegramSettings) -> AsyncIterator[TelegramClient]:
    async with open_bot(settings) as bot:
        yield AiogramTelegramClient(bot)


class AiogramTelegramClient:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def bot_username(self) -> str:
        me = await call(self._bot.get_me())
        if not me.username:
            raise PermanentExternalError("У бота нет username")
        return me.username

    async def send_message(self, chat_id: int, message: OutgoingMessage) -> int:
        sent = await call(
            self._bot.send_message(chat_id, message.text, reply_markup=message.keyboard)
        )
        return sent.message_id


async def call[T](request: Awaitable[T]) -> T:
    """Выполняет запрос к Bot API, переводя исключения aiogram в ошибки проекта.

    В тексте ошибок aiogram нет токена (только имя метода и ответ Telegram).
    """
    try:
        return await request
    except TelegramRetryAfter as exc:
        raise TransientExternalError(exc.message, retry_after=exc.retry_after) from exc
    except (TelegramNetworkError, TelegramServerError) as exc:
        raise TransientExternalError(f"Telegram: {exc.message}") from exc
    except TelegramForbiddenError as exc:
        # 403 у Telegram — про конкретный чат (бот заблокирован), а не про весь сервис.
        raise ChatUnavailableError(f"Telegram: {exc.message}") from exc
    except TelegramUnauthorizedError as exc:
        raise ExternalAccessError("Telegram отклонил токен бота") from exc
    except TelegramAPIError as exc:
        raise PermanentExternalError(f"Telegram: {exc.message}") from exc

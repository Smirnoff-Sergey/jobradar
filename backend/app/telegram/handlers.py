"""Обработчики бота: привязка чата и кнопки статуса отклика.

Обработчики тонкие — логика в сервисах. Одинаково работают в polling (`python -m app.bot`)
и через вебхук API: диспетчер получает фабрику сессий БД и настройки как workflow data.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from aiogram import Dispatcher, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TelegramSettings
from app.core.errors import InvalidStatusError, NotFoundError, StatusLockedError
from app.services.applications import ApplicationService
from app.services.telegram_link import TelegramLinkService
from app.telegram.messages import STATUS_LABELS, ApplicationCallback, vacancy_keyboard

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

LINKED = "Готово: подходящие вакансии будут приходить сюда. Отключить — /stop"
BAD_CODE = "Ссылка привязки неверна или устарела — получите новую в JobRadar"
NOT_LINKED = (
    "Это бот JobRadar. Чтобы получать вакансии, откройте ссылку привязки: "
    "её выдаёт `python -m app.cli telegram-link` или POST /api/v1/telegram/link"
)
UNLINKED = "Чат отвязан, уведомлений больше не будет"
CHAT_NOT_LINKED = "Чат не привязан к JobRadar"


def create_dispatcher(session_factory: SessionFactory, settings: TelegramSettings) -> Dispatcher:
    dispatcher = Dispatcher(session_factory=session_factory, telegram_settings=settings)
    dispatcher.include_router(build_router())
    return dispatcher


def build_router() -> Router:
    # Роутер создаётся на каждый диспетчер: aiogram не даёт подключить один роутер дважды.
    router = Router(name="jobradar")
    router.message.register(start_with_code, CommandStart(deep_link=True))
    router.message.register(start, CommandStart())
    router.message.register(stop, Command("stop"))
    router.callback_query.register(set_status, ApplicationCallback.filter())
    return router


async def start_with_code(
    message: Message,
    command: CommandObject,
    session_factory: SessionFactory,
    telegram_settings: TelegramSettings,
) -> None:
    async with session_factory() as session:
        user = await TelegramLinkService(session, telegram_settings).link(
            command.args or "", message.chat.id
        )
    await message.answer(LINKED if user is not None else BAD_CODE)


async def start(message: Message) -> None:
    await message.answer(NOT_LINKED, parse_mode=None)


async def stop(
    message: Message, session_factory: SessionFactory, telegram_settings: TelegramSettings
) -> None:
    async with session_factory() as session:
        unlinked = await TelegramLinkService(session, telegram_settings).unlink_chat(
            message.chat.id
        )
    await message.answer(UNLINKED if unlinked else CHAT_NOT_LINKED)


async def set_status(
    query: CallbackQuery,
    callback_data: ApplicationCallback,
    session_factory: SessionFactory,
    telegram_settings: TelegramSettings,
) -> None:
    message = query.message if isinstance(query.message, Message) else None
    chat_id = message.chat.id if message is not None else query.from_user.id
    # Сначала БД (сессия закрывается до сетевых вызовов), потом ответ Telegram.
    error = await _save_status(chat_id, callback_data, session_factory, telegram_settings)
    if error is not None:
        await query.answer(error, show_alert=True)
        return
    # Ответ на нажатие — первым: иначе у пользователя крутится индикатор кнопки.
    await query.answer(f"Статус: {STATUS_LABELS[callback_data.status]}")
    if message is not None and message.reply_markup is not None:
        await _mark_selected(message, message.reply_markup, callback_data)


async def _save_status(
    chat_id: int,
    callback_data: ApplicationCallback,
    session_factory: SessionFactory,
    telegram_settings: TelegramSettings,
) -> str | None:
    """Меняет статус отклика. Возвращает текст ошибки для пользователя или None."""
    async with session_factory() as session:
        user = await TelegramLinkService(session, telegram_settings).user_for_chat(chat_id)
        if user is None:
            return CHAT_NOT_LINKED
        try:
            await ApplicationService(session).set_status(
                user.id, callback_data.vacancy_id, callback_data.status, from_button=True
            )
        except StatusLockedError as exc:
            current = STATUS_LABELS.get(exc.current, exc.current)
            return f"Статус уже «{current}», меняйте его в JobRadar"
        except (NotFoundError, InvalidStatusError) as exc:
            return exc.message
    return None


async def _mark_selected(
    message: Message, markup: InlineKeyboardMarkup, callback_data: ApplicationCallback
) -> None:
    """Отмечает выбранную кнопку. URL вакансии берётся из прежней клавиатуры: в
    callback_data он не помещается (лимит 64 байта), а ходить за ним в БД незачем."""
    url = next((button.url for row in markup.inline_keyboard for button in row if button.url), None)
    if url is None:
        return
    keyboard = vacancy_keyboard(callback_data.vacancy_id, url, callback_data.status)
    try:
        await message.edit_reply_markup(reply_markup=keyboard)
    except TelegramAPIError as exc:
        # Статус уже сохранён, отметка на кнопке — косметика. «not modified» — повторное
        # нажатие той же кнопки, это и вовсе не ошибка.
        if "not modified" not in exc.message:
            logger.warning("Не удалось отметить кнопку: %s", exc.message)

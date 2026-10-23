"""Telegram-бот в режиме polling: python -m app.bot

Публичный адрес не нужен — бот сам забирает обновления у Telegram. В режиме webhook
(JOBRADAR_TELEGRAM__MODE=webhook) обновления принимает API, этот процесс не нужен.
"""

import asyncio
import logging
import sys

from app.core.config import get_settings
from app.db.session import open_session_factory
from app.telegram.client import create_bot
from app.telegram.handlers import create_dispatcher

logger = logging.getLogger("app.bot")


async def idle() -> None:
    """Ждать без дела. Завершившийся контейнер `docker compose up --wait` считает сбоем,
    а сервис без токена — штатная конфигурация."""
    await asyncio.Event().wait()


async def run() -> int:
    settings = get_settings()
    telegram = settings.telegram
    if not telegram.enabled:
        logger.warning("Бот выключен: не задан JOBRADAR_TELEGRAM__BOT_TOKEN")
        await idle()
        return 0
    if telegram.mode == "webhook":
        logger.info("Режим webhook: обновления принимает API, polling не запускается")
        await idle()
        return 0
    async with open_session_factory(settings.database_url) as session_factory:
        bot = create_bot(telegram)
        # Пока у бота зарегистрирован вебхук, Telegram не отдаёт обновления через getUpdates.
        await bot.delete_webhook()
        await create_dispatcher(session_factory, telegram).start_polling(bot)
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())

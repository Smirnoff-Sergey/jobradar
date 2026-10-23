import logging
import secrets
from typing import Annotated

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, Header, Request, status
from pydantic import ValidationError

from app.api.deps import CurrentUserDep, SessionDep, SettingsDep, TelegramClientDep
from app.core.errors import AppError, InvalidTokenError, NotFoundError
from app.schemas.common import ErrorResponse
from app.schemas.telegram import TelegramLinkRead
from app.services.telegram_link import TelegramLinkService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/link", responses={503: {"model": ErrorResponse}})
async def create_link(
    user: CurrentUserDep, session: SessionDep, settings: SettingsDep, client: TelegramClientDep
) -> TelegramLinkRead:
    """Ссылка для привязки чата: открыть в Telegram и нажать «Start». Код одноразовый."""
    link = await TelegramLinkService(session, settings.telegram).issue_link(user.id, client)
    return TelegramLinkRead(url=link.url, expires_at=link.expires_at)


@router.delete("/link", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(user: CurrentUserDep, session: SessionDep, settings: SettingsDep) -> None:
    """Отвязать чат: уведомления перестанут приходить."""
    await TelegramLinkService(session, settings.telegram).unlink_user(user.id)


@router.post(
    "/webhook",
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def webhook(
    request: Request,
    settings: SettingsDep,
    secret_token: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> dict[str, bool]:
    """Обновления от Telegram (режим webhook). Подлинность — по секрету в заголовке."""
    bot: Bot | None = getattr(request.app.state, "telegram_bot", None)
    dispatcher: Dispatcher | None = getattr(request.app.state, "telegram_dispatcher", None)
    expected = settings.telegram.webhook_secret
    if bot is None or dispatcher is None or expected is None:
        raise NotFoundError("Вебхук Telegram выключен")
    if secret_token is None or not secrets.compare_digest(
        secret_token.encode(), expected.get_secret_value().encode()
    ):
        raise InvalidTokenError("Неверный секрет вебхука")
    try:
        update = Update.model_validate(await request.json(), context={"bot": bot})
    except ValidationError as exc:
        raise AppError("Некорректное обновление Telegram") from exc
    try:
        await dispatcher.feed_update(bot, update)
    except Exception:
        # Ошибку обработчика не возвращаем Telegram: он повторял бы доставку бесконечно.
        logger.exception("Ошибка обработки обновления Telegram %d", update.update_id)
    return {"ok": True}

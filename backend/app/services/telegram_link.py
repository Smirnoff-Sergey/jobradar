import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TelegramSettings
from app.core.errors import NotFoundError, TelegramDisabledError
from app.db.models import User
from app.repositories.users import UserRepository
from app.services.auth import normalize_email
from app.telegram.client import TelegramClient

# 24 байта → 32 символа base64url: укладывается в лимит параметра /start (64 символа A-Za-z0-9_-).
LINK_CODE_BYTES = 24


@dataclass(frozen=True, slots=True)
class TelegramLink:
    url: str
    expires_at: datetime


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


class TelegramLinkService:
    """Привязка чата Telegram к пользователю по одноразовому коду из ссылки t.me/<бот>?start=."""

    def __init__(self, session: AsyncSession, settings: TelegramSettings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)

    async def issue_link(self, user_id: int, client: TelegramClient) -> TelegramLink:
        """Новая ссылка привязки; прежний код перестаёт действовать."""
        if not self._settings.enabled:
            raise TelegramDisabledError
        await self._session.commit()  # сеть — вне транзакции (её мог открыть поиск пользователя)
        username = await client.bot_username()
        user = await self._get_user(user_id)
        code = secrets.token_urlsafe(LINK_CODE_BYTES)
        user.telegram_link_code_hash = hash_code(code)
        user.telegram_link_expires_at = datetime.now(UTC) + timedelta(
            minutes=self._settings.link_code_ttl_minutes
        )
        await self._session.commit()
        return TelegramLink(f"https://t.me/{username}?start={code}", user.telegram_link_expires_at)

    async def issue_link_for_email(self, email: str, client: TelegramClient) -> TelegramLink:
        """Для CLI: ссылка привязки для пользователя по email."""
        user = await self._users.get_by_email(normalize_email(email))
        if user is None:
            raise NotFoundError(f"Пользователь {email} не найден")
        return await self.issue_link(user.id, client)

    async def link(self, code: str, chat_id: int) -> User | None:
        """Привязывает чат по коду. None — код неверный, просрочен или уже использован."""
        user = await self._users.take_by_link_code(hash_code(code), datetime.now(UTC))
        if user is None:
            return None
        if user.telegram_chat_id != chat_id:
            await self._users.release_chat(chat_id)
            user.telegram_chat_id = chat_id
            user.telegram_linked_at = datetime.now(UTC)
        user.telegram_link_code_hash = None
        user.telegram_link_expires_at = None
        await self._session.commit()
        return user

    async def user_for_chat(self, chat_id: int) -> User | None:
        return await self._users.get_by_chat_id(chat_id)

    async def unlink_chat(self, chat_id: int) -> bool:
        """Отвязывает чат (команда /stop или бот заблокирован). False — чат не был привязан."""
        user = await self._users.get_by_chat_id(chat_id)
        if user is None:
            return False
        await self._users.release_chat(chat_id)
        await self._session.commit()
        return True

    async def unlink_user(self, user_id: int) -> None:
        user = await self._get_user(user_id)
        if user.telegram_chat_id is not None:
            await self._users.release_chat(user.telegram_chat_id)
        await self._session.commit()

    async def _get_user(self, user_id: int) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Пользователь не найден")
        return user

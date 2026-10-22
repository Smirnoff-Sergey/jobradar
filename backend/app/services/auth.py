import asyncio
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    InvalidCredentialsError,
    InvalidPasswordError,
    InvalidTokenError,
)
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import User
from app.repositories.users import UserRepository


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _check_password(password: str) -> None:
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise InvalidPasswordError(
            f"Длина пароля — от {PASSWORD_MIN_LENGTH} до {PASSWORD_MAX_LENGTH} символов"
        )


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._auth_settings = settings.auth
        self._users = UserRepository(session)

    async def create_user(self, email: str, password: str) -> User:
        _check_password(password)
        password_hash = await asyncio.to_thread(hash_password, password)
        try:
            # Уникальность email проверяет БД: предварительный SELECT не защитил бы от гонки.
            user = await self._users.add(normalize_email(email), password_hash)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Пользователь с таким email уже есть") from exc
        return user

    async def authenticate(self, email: str, password: str) -> TokenPair:
        user = await self._users.get_by_email(normalize_email(email))
        password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
        password_ok = await asyncio.to_thread(verify_password, password, password_hash)
        if user is None or not password_ok or not user.is_active:
            raise InvalidCredentialsError
        return self._issue_tokens(user.id)

    async def refresh(self, refresh_token: str) -> TokenPair:
        user = await self._get_active_user(
            decode_token(refresh_token, "refresh", self._auth_settings)
        )
        return self._issue_tokens(user.id)

    async def get_user_by_access_token(self, access_token: str) -> User:
        return await self._get_active_user(
            decode_token(access_token, "access", self._auth_settings)
        )

    async def _get_active_user(self, user_id: int) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidTokenError
        return user

    def _issue_tokens(self, user_id: int) -> TokenPair:
        return TokenPair(
            access_token=create_token(user_id, "access", self._auth_settings),
            refresh_token=create_token(user_id, "refresh", self._auth_settings),
        )

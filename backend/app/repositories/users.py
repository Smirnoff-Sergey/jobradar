from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self._session.scalar(select(User).where(User.email == email))

    async def add(self, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash)
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_chat_id(self, chat_id: int) -> User | None:
        return await self._session.scalar(
            select(User).where(User.telegram_chat_id == chat_id, User.is_active)
        )

    async def take_by_link_code(self, code_hash: str, now: datetime) -> User | None:
        """Пользователь с действующим кодом привязки; строка блокируется до конца транзакции."""
        return await self._session.scalar(
            select(User)
            .where(
                User.telegram_link_code_hash == code_hash,
                User.telegram_link_expires_at > now,
                User.is_active,
            )
            .with_for_update()
        )

    async def release_chat(self, chat_id: int) -> None:
        """Отвязывает чат от всех пользователей — перед привязкой к другому."""
        await self._session.execute(
            update(User)
            .where(User.telegram_chat_id == chat_id)
            .values(telegram_chat_id=None, telegram_linked_at=None)
            .execution_options(synchronize_session="fetch")
        )
        await self._session.flush()

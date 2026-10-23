from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # Один чат — один пользователь: уведомления не должны уйти чужому человеку.
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    # С этого момента оценки уходят в Telegram; более ранние не рассылаются задним числом.
    telegram_linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Одноразовый код привязки чата: хранится только SHA-256.
    telegram_link_code_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    telegram_link_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

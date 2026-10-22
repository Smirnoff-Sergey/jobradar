from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, String, Text, func, true
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import EMPTY_ARRAY, Base


class SearchProfile(Base):
    """Критерии поиска пользователя. Пустой список означает «без ограничения»."""

    __tablename__ = "search_profiles"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
    )
    title_keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=EMPTY_ARRAY)
    stop_words: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=EMPTY_ARRAY)
    min_salary: Mapped[int | None] = mapped_column(Integer)
    min_salary_is_net: Mapped[bool] = mapped_column(server_default=true())
    remote_only: Mapped[bool] = mapped_column(server_default=true())
    contract_types: Mapped[list[str]] = mapped_column(ARRAY(String(16)), server_default=EMPTY_ARRAY)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

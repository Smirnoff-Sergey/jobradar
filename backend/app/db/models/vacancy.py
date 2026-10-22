from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import EMPTY_ARRAY, Base


class Vacancy(Base):
    __tablename__ = "vacancies"
    __table_args__ = (UniqueConstraint("source_code", "external_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_code: Mapped[str] = mapped_column(String(32), ForeignKey("sources.code"))
    external_id: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    salary_from: Mapped[int | None] = mapped_column(Integer)
    salary_to: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    # None — источник не сообщил, указана сумма до или после вычета налогов.
    salary_gross: Mapped[bool | None]
    # Пустой массив означает «неизвестно», а не «ничего не подходит».
    work_formats: Mapped[list[str]] = mapped_column(ARRAY(String(16)), server_default=EMPTY_ARRAY)
    contract_types: Mapped[list[str]] = mapped_column(ARRAY(String(16)), server_default=EMPTY_ARRAY)
    short_description: Mapped[str | None] = mapped_column(Text)
    # Полное описание загружается отдельным запросом и только для прошедших фильтр.
    description: Mapped[str | None] = mapped_column(Text)
    description_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(server_default=true())
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VacancyFilterResult(Base):
    """Решение фильтра по вакансии для конкретного пользователя."""

    __tablename__ = "vacancy_filter_results"

    vacancy_id: Mapped[int] = mapped_column(
        ForeignKey("vacancies.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    passed: Mapped[bool]
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=EMPTY_ARRAY)
    salary_unknown: Mapped[bool]
    filtered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

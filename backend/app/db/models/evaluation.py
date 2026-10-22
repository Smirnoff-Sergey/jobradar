from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Evaluation(Base):
    """LLM-оценка вакансии по резюме.

    Строка создаётся со статусом pending до запроса к модели — это «захват» пары
    (вакансия, резюме, версия промпта): уникальный индекс не даёт двум задачам оценить
    одну пару дважды и потратить лишние запросы.
    """

    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("vacancy_id", "resume_id", "prompt_version"),
        # Уникальный индекс начинается с vacancy_id; выборки и каскад по резюме — отдельно.
        Index("ix_evaluations_resume_id", "resume_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"))
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    prompt_version: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))  # EvaluationStatus
    model: Mapped[str | None] = mapped_column(String(128))
    score: Mapped[int | None] = mapped_column(SmallInteger)
    verdict: Mapped[str | None] = mapped_column(String(8))
    matches: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    gaps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    dealbreakers: Mapped[list[str] | None] = mapped_column(JSONB)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class LLMDailyUsage(Base):
    """Счётчик запросов к LLM за сутки (UTC) — свой потолок ниже лимита провайдера."""

    __tablename__ = "llm_daily_usage"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    requests: Mapped[int] = mapped_column(Integer)


class LLMGuard(Base):
    """Аварийная остановка LLM-оценки — одна строка на всё приложение.

    Ставится автоматически: после платного ответа — бессрочно (снять — командой CLI),
    после отказа в доступе (401/403) — на час, чтобы не тратить лимит на заведомо
    провальные запросы.
    """

    __tablename__ = "llm_guard"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)

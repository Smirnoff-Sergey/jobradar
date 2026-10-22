from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Source(Base):
    """Источник вакансий и итог его последнего запуска."""

    __tablename__ = "sources"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(server_default=true())
    last_run_status: Mapped[str | None] = mapped_column(String(16))
    last_run_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_error: Mapped[str | None] = mapped_column(Text)

    def finish_run(
        self,
        status: str,
        *,
        stats: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self.last_run_status = status
        self.last_run_finished_at = datetime.now(UTC)
        self.last_run_stats = stats
        self.last_error = error

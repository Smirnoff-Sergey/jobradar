"""Захват строки задачей перед внешним вызовом (оценки LLM, уведомления).

Строка создаётся со статусом pending до запроса, уникальный индекс не даёт двум задачам
взять одну работу. Захват задачи, упавшей вместе с воркером, через ttl перехватывается.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, or_
from sqlalchemy.orm import InstrumentedAttribute


def stale_cutoff(ttl: timedelta) -> datetime:
    """Захваты, обновлённые раньше этого момента, считаются зависшими."""
    return datetime.now(UTC) - ttl


def settled_or_fresh(
    status: InstrumentedAttribute[str],
    updated_at: InstrumentedAttribute[datetime],
    *,
    pending: str,
    stale_before: datetime,
) -> ColumnElement[bool]:
    """Работа завершена или её прямо сейчас делает другая задача — ставить её не нужно."""
    return or_(status != pending, updated_at >= stale_before)

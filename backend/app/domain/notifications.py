"""Уведомления о вакансиях: типы без БД и сети."""

from typing import Literal

NotificationStatus = Literal["pending", "sent", "failed"]
NOTIFICATION_PENDING: NotificationStatus = "pending"
NOTIFICATION_SENT: NotificationStatus = "sent"
NOTIFICATION_FAILED: NotificationStatus = "failed"

TELEGRAM_CHANNEL = "telegram"


def notification_key(channel: str, user_id: int, vacancy_id: int) -> str:
    """Ключ идемпотентности: одна вакансия уходит пользователю в канал один раз —
    даже если её переоценили и вердикт снова «apply»."""
    return f"{channel}:{user_id}:{vacancy_id}"

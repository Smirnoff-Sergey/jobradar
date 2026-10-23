"""Все модели импортируются здесь, чтобы Alembic видел их в Base.metadata."""

from app.db.models.application import Application, Notification, StatusHistory
from app.db.models.evaluation import Evaluation, LLMDailyUsage, LLMGuard
from app.db.models.resume import Resume
from app.db.models.search_profile import SearchProfile
from app.db.models.source import Source
from app.db.models.user import User
from app.db.models.vacancy import Vacancy, VacancyFilterResult

__all__ = [
    "Application",
    "Evaluation",
    "LLMDailyUsage",
    "LLMGuard",
    "Notification",
    "Resume",
    "SearchProfile",
    "Source",
    "StatusHistory",
    "User",
    "Vacancy",
    "VacancyFilterResult",
]

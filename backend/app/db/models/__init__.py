"""Все модели импортируются здесь, чтобы Alembic видел их в Base.metadata."""

from app.db.models.search_profile import SearchProfile
from app.db.models.source import Source
from app.db.models.user import User
from app.db.models.vacancy import Vacancy, VacancyFilterResult

__all__ = ["SearchProfile", "Source", "User", "Vacancy", "VacancyFilterResult"]

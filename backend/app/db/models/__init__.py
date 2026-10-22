"""Все модели импортируются здесь, чтобы Alembic видел их в Base.metadata."""

from app.db.models.user import User

__all__ = ["User"]

"""Типы, общие для API, сервисов и репозиториев вакансий."""

from dataclasses import dataclass
from typing import Literal

FilterStatus = Literal["passed", "rejected", "all"]


@dataclass(frozen=True, slots=True)
class VacancyListQuery:
    user_id: int
    status: FilterStatus = "passed"
    source_code: str | None = None
    active_only: bool = True
    limit: int = 20
    offset: int = 0

"""Типы, общие для API, сервисов и репозиториев вакансий."""

from dataclasses import dataclass
from typing import Literal

from app.domain.applications import ApplicationStatus
from app.domain.evaluation import Verdict

FilterStatus = Literal["passed", "rejected", "all"]
VacancySort = Literal["published", "score"]


@dataclass(frozen=True, slots=True)
class VacancyListQuery:
    user_id: int
    status: FilterStatus = "passed"
    source_code: str | None = None
    active_only: bool = True
    verdict: Verdict | None = None
    score_min: int | None = None
    application_status: ApplicationStatus | None = None
    sort: VacancySort = "published"
    limit: int = 20
    offset: int = 0

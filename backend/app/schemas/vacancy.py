from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict

from app.domain.applications import ApplicationStatus
from app.domain.evaluation import EvaluationStatus, Gap, Match, Verdict
from app.repositories.vacancies import VacancyRow


class FilterResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    passed: bool
    reasons: list[str]
    salary_unknown: bool


class EvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: EvaluationStatus
    score: int | None
    verdict: Verdict | None
    model: str | None
    prompt_version: str
    matches: list[Match] | None
    gaps: list[Gap] | None
    dealbreakers: list[str] | None
    error: str | None
    updated_at: datetime


class ApplicationBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ApplicationStatus
    updated_at: datetime


class VacancyListItem(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )

    id: int
    source_code: str
    url: str
    title: str
    company: str | None
    salary_from: int | None
    salary_to: int | None
    salary_currency: str | None
    salary_gross: bool | None
    work_formats: list[str]
    contract_types: list[str]
    published_at: datetime | None
    is_active: bool
    filter: FilterResultRead | None = None
    evaluation: EvaluationRead | None = None
    application: ApplicationBrief | None = None

    @classmethod
    def build(cls, row: VacancyRow) -> Self:
        return cls.model_validate(row.vacancy).model_copy(
            update={
                "filter": row.decision and FilterResultRead.model_validate(row.decision),
                "evaluation": row.evaluation and EvaluationRead.model_validate(row.evaluation),
                "application": row.application and ApplicationBrief.model_validate(row.application),
            }
        )


class VacancyRead(VacancyListItem):
    short_description: str | None
    description: str | None


class VacancyPage(BaseModel):
    items: list[VacancyListItem]
    total: int
    limit: int
    offset: int

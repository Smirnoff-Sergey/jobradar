from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict

from app.db.models import Vacancy, VacancyFilterResult


class FilterResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    passed: bool
    reasons: list[str]
    salary_unknown: bool


class VacancyListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

    @classmethod
    def build(cls, vacancy: Vacancy, decision: VacancyFilterResult | None) -> Self:
        result = None if decision is None else FilterResultRead.model_validate(decision)
        return cls.model_validate(vacancy).model_copy(update={"filter": result})


class VacancyRead(VacancyListItem):
    short_description: str | None
    description: str | None


class VacancyPage(BaseModel):
    items: list[VacancyListItem]
    total: int
    limit: int
    offset: int

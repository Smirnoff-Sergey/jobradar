from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.applications import ApplicationStatus

Notes = Field(default=None, max_length=10_000)


class ApplicationSet(BaseModel):
    """Создать отклик на вакансию или сменить его статус."""

    status: ApplicationStatus
    notes: str | None = Notes


class ApplicationUpdate(BaseModel):
    """Частичное обновление: переданные поля меняются, остальные — нет."""

    status: ApplicationStatus | None = None
    notes: str | None = Notes


class VacancyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str | None
    url: str
    is_active: bool


class StatusChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    changed_at: datetime


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vacancy_id: int
    status: ApplicationStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ApplicationListItem(ApplicationRead):
    vacancy: VacancyBrief


class ApplicationDetail(ApplicationRead):
    history: list[StatusChangeRead]


class ApplicationPage(BaseModel):
    items: list[ApplicationListItem]
    total: int
    limit: int
    offset: int

import hashlib
import json
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

WorkFormat = Literal["remote", "hybrid", "office", "relocation"]
ContractType = Literal["TK", "GPH", "IP", "SELF_EMPLOYED"]


@dataclass(frozen=True, slots=True)
class VacancyData:
    """Вакансия в общем для всех источников виде."""

    external_id: str
    url: str
    title: str
    company: str | None = None
    salary_from: int | None = None
    salary_to: int | None = None
    salary_currency: str | None = None
    salary_gross: bool | None = None
    work_formats: tuple[WorkFormat, ...] = ()
    contract_types: tuple[ContractType, ...] = ()
    short_description: str | None = None
    published_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    def content_hash(self) -> str:
        """Отпечаток значимых полей: по нему upsert понимает, изменилась ли вакансия.

        Сырой ответ не учитывается: в нём бывают служебные поля, которые меняются без повода.
        """
        data = asdict(self)
        data.pop("raw")
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ImportedVacancy:
    """Одна вакансия, загруженная по ссылке: карточка сразу с полным описанием."""

    data: VacancyData
    description: str | None
    is_active: bool = True


class SourceAdapter(Protocol):
    code: str

    def iter_pages(self) -> AsyncIterator[list[VacancyData]]:
        """Все актуальные вакансии источника, постранично."""
        ...

    async def fetch_description(self, external_id: str) -> str | None:
        """Полное описание вакансии (отдельный запрос)."""
        ...


@runtime_checkable
class VacancyImporter(Protocol):
    """Адаптер, который умеет загрузить одну вакансию по id из ссылки."""

    async def fetch_vacancy(self, external_id: str) -> ImportedVacancy:
        """Карточка вакансии. Нет такой — PermanentExternalError."""
        ...

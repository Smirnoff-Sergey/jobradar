from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.sources.base import ContractType

Word = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class SearchProfileUpdate(BaseModel):
    title_keywords: list[Word] = Field(default_factory=list, max_length=50)
    stop_words: list[Word] = Field(default_factory=list, max_length=200)
    min_salary: int | None = Field(default=None, ge=0, le=100_000_000)
    min_salary_is_net: bool = True
    remote_only: bool = True
    contract_types: list[ContractType] = Field(default_factory=list)


class SearchProfileRead(SearchProfileUpdate):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime


class SearchProfileUpdated(BaseModel):
    profile: SearchProfileRead
    refilter_task_id: str

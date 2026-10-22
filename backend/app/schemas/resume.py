from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

Title = Field(min_length=1, max_length=200)
Text = Field(min_length=50, max_length=50_000)


class ResumeCreate(BaseModel):
    title: str = Title
    text: str = Text
    make_active: bool = True


class ResumeUpdate(BaseModel):
    """Частичное обновление: переданные поля меняются, остальные — нет."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    text: str | None = Field(default=None, min_length=50, max_length=50_000)
    is_active: bool | None = None


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    text: str
    is_active: bool
    updated_at: datetime

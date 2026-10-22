from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class LLMUsageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: date
    used: int
    limit: int
    enabled: bool
    models: list[str]
    paused_until: datetime | None
    pause_reason: str | None

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    is_enabled: bool
    last_run_status: str | None
    last_run_finished_at: datetime | None
    last_run_stats: dict[str, Any] | None
    last_error: str | None


class TaskAccepted(BaseModel):
    task_id: str


class TaskStatusRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )

    task_id: str
    state: str
    result: Any = None
    error: str | None = None

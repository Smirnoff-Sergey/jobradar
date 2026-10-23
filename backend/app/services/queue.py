from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class TaskStatus:
    task_id: str
    state: str
    result: Any = None
    error: str | None = None


class TaskQueue(Protocol):
    """Постановка фоновых задач. Сервисы не знают, что за ней стоит Celery."""

    async def collect_source(self, source_code: str) -> str: ...

    async def fetch_details(self, vacancy_ids: Sequence[int]) -> None: ...

    async def refilter_user(self, user_id: int) -> str: ...

    async def evaluate_vacancy(
        self, vacancy_id: int, resume_id: int, *, force: bool = False
    ) -> str: ...

    async def notify_vacancy(self, user_id: int, vacancy_id: int) -> str: ...

    async def status(self, task_id: str) -> TaskStatus: ...

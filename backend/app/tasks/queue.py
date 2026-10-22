import asyncio
from collections.abc import Sequence
from typing import Any

from celery import Celery
from celery.result import AsyncResult

from app.services.queue import TaskStatus
from app.tasks.celery_app import celery_app
from app.tasks.names import COLLECT_SOURCE, EVALUATE_VACANCY, FETCH_DETAILS, REFILTER_USER


class CeleryTaskQueue:
    """Реализация TaskQueue на Celery. Клиент Celery синхронный — вызовы уходят в поток."""

    def __init__(self, app: Celery = celery_app) -> None:
        self._app = app

    async def _send(self, name: str, *args: object) -> str:
        result = await asyncio.to_thread(self._app.send_task, name, args=list(args))
        return str(result.id)

    async def collect_source(self, source_code: str) -> str:
        return await self._send(COLLECT_SOURCE, source_code)

    async def fetch_details(self, vacancy_ids: Sequence[int]) -> None:
        # Темп запросов к источнику ограничивает rate_limit задачи, а не задержки при постановке.
        for vacancy_id in vacancy_ids:
            await self._send(FETCH_DETAILS, vacancy_id)

    async def refilter_user(self, user_id: int) -> str:
        return await self._send(REFILTER_USER, user_id)

    async def evaluate_vacancy(
        self, vacancy_id: int, resume_id: int, *, force: bool = False
    ) -> str:
        return await self._send(EVALUATE_VACANCY, vacancy_id, resume_id, force)

    async def status(self, task_id: str) -> TaskStatus:
        def read() -> TaskStatus:
            result: AsyncResult[Any] = AsyncResult(task_id, app=self._app)
            state = str(result.state)
            if result.failed():
                return TaskStatus(task_id, state, error=repr(result.result))
            return TaskStatus(task_id, state, result=result.result if result.ready() else None)

        return await asyncio.to_thread(read)

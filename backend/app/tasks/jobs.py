"""Задачи Celery — тонкие обёртки над сервисами.

Celery синхронный, сервисы асинхронные: каждая задача запускает свой asyncio.run и создаёт
движок БД без пула (pooled=False), потому что соединения asyncpg привязаны к event loop.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import TransientExternalError
from app.core.http import create_client
from app.db.session import open_session_factory
from app.llm.base import LLMClient
from app.llm.openrouter import OpenRouterClient
from app.services.collector import CollectorService
from app.services.details import AdapterFactory, VacancyDetailsService
from app.services.evaluation import EvaluationScheduler, EvaluationService
from app.services.search_profiles import SearchProfileService
from app.sources.registry import create_adapter
from app.tasks.celery_app import celery_app
from app.tasks.names import (
    COLLECT_SOURCE,
    EVALUATE_PENDING,
    EVALUATE_VACANCY,
    FETCH_DETAILS,
    REFILTER_USER,
)
from app.tasks.queue import CeleryTaskQueue

# Сбор getmatch занимает около минуты; лимиты не дают зависшей задаче навсегда занять воркер.
COLLECT_SOFT_TIME_LIMIT = 25 * 60
COLLECT_TIME_LIMIT = 30 * 60


def run_in_session[T](work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async def main() -> T:
        settings = get_settings()
        async with (
            open_session_factory(settings.database_url, pooled=False) as session_factory,
            session_factory() as session,
        ):
            return await work(session)

    return asyncio.run(main())


@asynccontextmanager
async def adapters() -> AsyncIterator[AdapterFactory]:
    """Фабрика адаптеров источников с общим HTTP-клиентом на время задачи."""
    settings = get_settings().collector
    async with create_client(settings.request_timeout_seconds) as client:
        yield lambda code: create_adapter(code, client, settings)


@asynccontextmanager
async def llm_client() -> AsyncIterator[LLMClient]:
    settings = get_settings().llm
    async with create_client(settings.request_timeout_seconds) as client:
        yield OpenRouterClient(client, settings)


def scheduler(session: AsyncSession) -> EvaluationScheduler:
    return EvaluationScheduler(session, CeleryTaskQueue(), get_settings().llm)


@celery_app.task(
    name=COLLECT_SOURCE,
    soft_time_limit=COLLECT_SOFT_TIME_LIMIT,
    time_limit=COLLECT_TIME_LIMIT,
)
def collect_source(source_code: str) -> dict[str, Any]:
    async def work(session: AsyncSession) -> dict[str, Any]:
        async with adapters() as adapter_for:
            service = CollectorService(session, adapter_for(source_code), CeleryTaskQueue())
            stats = await service.collect()
        return {"status": stats.status, **stats.as_run_stats()}

    return run_in_session(work)


# Временные сбои источника повторяем с растущей паузой (до 15 минут) — минуты, а не секунды,
# как у повторов внутри HTTP-клиента: здесь пережидаем уже затяжную недоступность.
@celery_app.task(
    name=FETCH_DETAILS,
    autoretry_for=(TransientExternalError,),
    retry_backoff=30,
    retry_backoff_max=900,
    max_retries=5,
    rate_limit=get_settings().collector.details_rate_limit,
)
def fetch_details(vacancy_id: int) -> bool:
    async def work(session: AsyncSession) -> bool:
        async with adapters() as adapter_for:
            loaded = await VacancyDetailsService(session, adapter_for).load_description(vacancy_id)
        # Описание загружено (или выяснилось, что его нет) — вакансию можно оценивать.
        await scheduler(session).queue_pending(vacancy_id)
        return loaded

    return run_in_session(work)


@celery_app.task(name=REFILTER_USER)
def refilter_user(user_id: int) -> int:
    async def work(session: AsyncSession) -> int:
        return await SearchProfileService(session, CeleryTaskQueue()).refilter(user_id)

    return run_in_session(work)


# Повторы — только для временных сбоев провайдера; каждая попытка резервирует запрос в
# дневном лимите. Исчерпанный лимит — не ошибка: оценка откладывается до следующих суток.
@celery_app.task(
    name=EVALUATE_VACANCY,
    autoretry_for=(TransientExternalError,),
    retry_backoff=60,
    retry_backoff_max=1800,
    max_retries=3,
    rate_limit=get_settings().llm.rate_limit,
)
def evaluate_pair(vacancy_id: int, resume_id: int, force: bool = False) -> str:
    settings = get_settings().llm
    if not settings.enabled:
        return "disabled"

    async def work(session: AsyncSession) -> str:
        async with llm_client() as llm:
            service = EvaluationService(session, settings, llm)
            return await service.evaluate(vacancy_id, resume_id, force=force)

    return run_in_session(work)


@celery_app.task(name=EVALUATE_PENDING)
def evaluate_pending() -> int:
    async def work(session: AsyncSession) -> int:
        return await scheduler(session).queue_pending()

    return run_in_session(work)

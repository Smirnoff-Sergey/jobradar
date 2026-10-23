"""Приложение Celery.

Воркер:  celery -A app.tasks.celery_app worker -Q celery,details,llm,notify
Beat:    celery -A app.tasks.celery_app beat
"""

from datetime import timedelta
from typing import Any

import structlog
from celery import Celery, Task
from celery.schedules import crontab
from celery.signals import setup_logging, task_postrun, task_prerun

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.sources.registry import SOURCE_CODES
from app.tasks.names import (
    COLLECT_SOURCE,
    DETAILS_QUEUE,
    EVALUATE_PENDING,
    EVALUATE_VACANCY,
    FETCH_DETAILS,
    GENERATE_LETTER,
    LLM_QUEUE,
    NOTIFY_PENDING,
    NOTIFY_QUEUE,
    NOTIFY_VACANCY,
)


def cron_schedule(expression: str) -> crontab:
    minute, hour, day_of_month, month_of_year, day_of_week = expression.split()
    return crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
    )


def create_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "jobradar",
        broker=settings.redis.url,
        backend=settings.redis.url,
        include=["app.tasks.jobs"],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        # Задача подтверждается после выполнения: при падении воркера она не потеряется.
        # Поэтому все задачи обязаны быть идемпотентными.
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        result_expires=timedelta(days=1),
        # Сотни загрузок описаний идут своей очередью и не задерживают сбор и перефильтрацию.
        task_routes={
            FETCH_DETAILS: {"queue": DETAILS_QUEUE},
            GENERATE_LETTER: {"queue": LLM_QUEUE},
            EVALUATE_VACANCY: {"queue": LLM_QUEUE},
            NOTIFY_VACANCY: {"queue": NOTIFY_QUEUE},
        },
        beat_schedule={
            **{
                f"collect-{code}": {
                    "task": COLLECT_SOURCE,
                    "schedule": cron_schedule(settings.collector.schedule_cron),
                    "args": (code,),
                }
                for code in sorted(SOURCE_CODES)
            },
            # Досыл оценок, которые не дошли или не уложились в дневной лимит.
            "evaluate-pending": {
                "task": EVALUATE_PENDING,
                "schedule": crontab(minute=30),
            },
            # Досыл уведомлений: бот был недоступен, чат привязали после оценки и т.п.
            "notify-pending": {
                "task": NOTIFY_PENDING,
                "schedule": crontab(minute="*/10"),
            },
        },
    )
    return app


@setup_logging.connect
def _setup_logging(**_: Any) -> None:
    # Обработчик сигнала отключает настройку логов Celery: формат — общий для всех процессов.
    settings = get_settings().logging
    configure_logging(settings.level, settings.format)


@task_prerun.connect
def _bind_task(task_id: str, task: "Task[Any, Any]", **_: Any) -> None:
    structlog.contextvars.bind_contextvars(task_id=task_id, task=task.name)


@task_postrun.connect
def _unbind_task(**_: Any) -> None:
    structlog.contextvars.unbind_contextvars("task_id", "task")


celery_app = create_celery()

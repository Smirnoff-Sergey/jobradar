"""Приложение Celery.

Воркер:  celery -A app.tasks.celery_app worker -Q celery,details
Beat:    celery -A app.tasks.celery_app beat
"""

from datetime import timedelta

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings
from app.sources.registry import SOURCE_CODES
from app.tasks.names import COLLECT_SOURCE, DETAILS_QUEUE, FETCH_DETAILS


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
        task_routes={FETCH_DETAILS: {"queue": DETAILS_QUEUE}},
        beat_schedule={
            f"collect-{code}": {
                "task": COLLECT_SOURCE,
                "schedule": cron_schedule(settings.collector.schedule_cron),
                "args": (code,),
            }
            for code in sorted(SOURCE_CODES)
        },
    )
    return app


celery_app = create_celery()

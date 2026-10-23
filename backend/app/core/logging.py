"""Структурные логи: каждая запись — одна строка JSON с request_id (API) или task_id (Celery).

Модули пишут обычным logging.getLogger(__name__): записи стандартной библиотеки проходят
через тот же конвейер structlog, поэтому переписывать вызовы не нужно.
"""

import logging
import sys
from typing import Literal

import structlog
from structlog.typing import Processor

LogFormat = Literal["json", "console"]

_SHARED: list[Processor] = [
    # request_id и task_id привязываются через contextvars и попадают во все записи.
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]


def configure_logging(level: str = "INFO", log_format: LogFormat = "json") -> None:
    renderer: Processor = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[*_SHARED, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Журнал запросов пишет middleware API — с request_id и временем ответа.
    logging.getLogger("uvicorn.access").disabled = True

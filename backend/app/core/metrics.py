"""Метрики процесса API. Состояние сервиса (вакансии, сборы, LLM) снимается из БД
в момент запроса /metrics — см. services/metrics.py: воркеры Celery — отдельные процессы,
и их счётчики сюда не дошли бы."""

from prometheus_client import CollectorRegistry, Histogram

API_REGISTRY = CollectorRegistry()

HTTP_REQUEST_DURATION = Histogram(
    "jobradar_http_request_duration_seconds",
    "Время ответа API",
    # route — шаблон пути (/api/v1/vacancies/{vacancy_id}), а не сам путь: иначе метрик
    # стало бы столько же, сколько вакансий.
    labelnames=["method", "route", "status"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    registry=API_REGISTRY,
)

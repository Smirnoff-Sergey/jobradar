from collections.abc import Iterator
from datetime import UTC, datetime

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric
from prometheus_client.registry import Collector
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LLMSettings
from app.core.metrics import API_REGISTRY
from app.repositories.metrics import MetricsRepository, MetricsSnapshot


class _SnapshotCollector(Collector):
    """Отдаёт готовый срез из БД в формате Prometheus."""

    def __init__(self, snapshot: MetricsSnapshot, settings: LLMSettings) -> None:
        self._snapshot = snapshot
        self._settings = settings

    def collect(self) -> Iterator[Metric]:
        snapshot = self._snapshot
        vacancies = GaugeMetricFamily(
            "jobradar_vacancies", "Вакансии в базе", labels=["source", "active"]
        )
        for code, active, count in snapshot.vacancies:
            vacancies.add_metric([code, str(active).lower()], count)
        yield vacancies

        last_success = GaugeMetricFamily(
            "jobradar_source_last_run_success",
            "Последний сбор успешен (1) или нет (0)",
            labels=["source"],
        )
        last_finished = GaugeMetricFamily(
            "jobradar_source_last_run_timestamp_seconds",
            "Время окончания последнего сбора",
            labels=["source"],
        )
        received = GaugeMetricFamily(
            "jobradar_source_last_run_received",
            "Вакансий получено последним сбором",
            labels=["source"],
        )
        failures = CounterMetricFamily(
            "jobradar_source_failed_runs", "Неудачные сборы за всё время", labels=["source"]
        )
        for source in snapshot.sources:
            failures.add_metric([source.code], source.failed_runs)
            if source.last_run_status is None:
                continue
            last_success.add_metric([source.code], int(source.last_run_status == "success"))
            if source.last_run_finished_at is not None:
                last_finished.add_metric([source.code], source.last_run_finished_at.timestamp())
            stats = source.last_run_stats or {}
            if isinstance(stats.get("received"), int):
                received.add_metric([source.code], stats["received"])
        yield from (last_success, last_finished, received, failures)

        yield CounterMetricFamily(
            "jobradar_llm_requests",
            "Запросов к LLM за всё время",
            value=snapshot.llm_requests_total,
        )
        yield GaugeMetricFamily(
            "jobradar_llm_requests_today",
            "Запросов к LLM за текущие сутки UTC",
            value=snapshot.llm_requests_today,
        )
        yield GaugeMetricFamily(
            "jobradar_llm_daily_limit",
            "Дневной лимит запросов к LLM",
            value=self._settings.daily_request_limit,
        )

        labels = ["kind", "status", "model"]
        results = GaugeMetricFamily("jobradar_llm_results", "Оценки и письма", labels=labels)
        # Gauge, а не counter: это суммы по строкам оценок и писем, а оценки удаляются при
        # смене текста резюме или вакансии — сумма может уменьшиться.
        tokens = GaugeMetricFamily(
            "jobradar_llm_tokens",
            "Токены LLM в сохранённых оценках и письмах",
            labels=[*labels, "direction"],
        )
        cost = GaugeMetricFamily(
            "jobradar_llm_cost_usd",
            "Стоимость LLM в сохранённых оценках и письмах, USD",
            labels=labels,
        )
        for work in snapshot.llm_work:
            key = [work.kind, work.status, work.model]
            results.add_metric(key, work.count)
            tokens.add_metric([*key, "in"], work.tokens_in)
            tokens.add_metric([*key, "out"], work.tokens_out)
            cost.add_metric(key, float(work.cost_usd))
        yield from (results, tokens, cost)

        applications = GaugeMetricFamily(
            "jobradar_applications", "Отклики по статусам", labels=["status"]
        )
        for status, count in snapshot.applications:
            applications.add_metric([status], count)
        yield applications


async def render_metrics(session: AsyncSession, settings: LLMSettings) -> bytes:
    """Метрики процесса API и срез состояния сервиса из БД — одним текстом."""
    snapshot = await MetricsRepository(session).snapshot(datetime.now(UTC).date())
    registry = CollectorRegistry(auto_describe=False)
    registry.register(_SnapshotCollector(snapshot, settings))
    return generate_latest(API_REGISTRY) + generate_latest(registry)

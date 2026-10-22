"""Проверка качества LLM-оценки на размеченном наборе.

    cd backend
    python -m scripts.eval --dataset scripts/eval_demo/vacancies.jsonl \
        --resume scripts/eval_demo/resume.md [--limit 10] [--out results.jsonl]

Каждая вакансия — один-два запроса к модели: следите за дневным лимитом OpenRouter
(50 запросов на бесплатном тарифе). БД и счётчик сервиса скрипт не трогает.
Ответы пишутся в --out построчно сразу после каждой вакансии: сбой не теряет полученное.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from pydantic_settings import SettingsConfigDict

from app.core.config import DatabaseSettings, LLMSettings
from app.core.errors import ExternalServiceError, PaidUsageError
from app.core.http import create_client
from app.domain.evaluation import Verdict
from app.llm.dataset import LabeledVacancy, load_dataset
from app.llm.evaluator import EvaluationOutcome, request_evaluation
from app.llm.openrouter import OpenRouterClient
from app.llm.prompts import PROMPT_VERSION
from app.llm.quality import Prediction, QualityReport, compare, format_report

# Бесплатные модели допускают 20 запросов в минуту — держим паузу с запасом.
PAUSE_SECONDS = 4.0


class EvalSettings(DatabaseSettings):
    """Только настройки LLM: JWT-секрет и прочее скрипту не нужны."""

    model_config = SettingsConfigDict(
        env_prefix="JOBRADAR_",
        env_nested_delimiter="__",
        env_file=("../.env", ".env"),
        extra="ignore",
    )

    llm: LLMSettings = LLMSettings()


@dataclass(frozen=True, slots=True)
class ItemResult:
    item: LabeledVacancy
    label: Verdict
    outcome: EvaluationOutcome | None = None
    error: str | None = None

    @property
    def prediction(self) -> Prediction:
        return Prediction(self.label, self.outcome.result.verdict if self.outcome else None)

    def as_dict(self) -> dict[str, object]:
        row: dict[str, object] = {
            "id": self.item.id,
            "title": self.item.vacancy.title,
            "label": self.label,
        }
        if self.outcome is not None:
            row.update(
                predicted=self.outcome.result.verdict,
                model=self.outcome.model,
                attempts=self.outcome.attempts,
                result=self.outcome.result.model_dump(),
            )
        else:
            row["error"] = self.error
        return row


async def run(
    items: list[tuple[LabeledVacancy, Verdict]],
    resume: str,
    settings: LLMSettings,
    *,
    out: TextIO | None = None,
    pause: float = PAUSE_SECONDS,
) -> QualityReport:
    results: list[ItemResult] = []
    async with create_client(settings.request_timeout_seconds) as http:
        client = OpenRouterClient(http, settings)
        for index, (item, label) in enumerate(items):
            if index:
                await asyncio.sleep(pause)
            try:
                outcome = await request_evaluation(
                    client, resume, item.vacancy, max_chars=settings.max_description_chars
                )
            except PaidUsageError:
                print("Ответ оказался платным — прогон остановлен", file=sys.stderr)
                raise
            except ExternalServiceError as exc:
                result = ItemResult(item, label, error=exc.message)
            else:
                result = ItemResult(item, label, outcome=outcome)
            results.append(result)
            print(f"{item.id}: метка {label}, ответ {result.prediction.predicted or result.error}")
            if out is not None:
                out.write(json.dumps(result.as_dict(), ensure_ascii=False) + "\n")
                out.flush()
    return compare([result.prediction for result in results])


def labeled(path: Path, limit: int | None) -> list[tuple[LabeledVacancy, Verdict]]:
    items = [(item, item.label) for item in load_dataset(path) if item.label is not None]
    return items[:limit] if limit else items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.eval")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--resume", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=None, help="не больше N вакансий")
    parser.add_argument("--out", type=Path, default=None, help="куда писать ответы (JSON Lines)")
    args = parser.parse_args(argv)

    settings = EvalSettings().llm
    if not settings.enabled:
        print("Не задан JOBRADAR_LLM__API_KEY", file=sys.stderr)
        return 1
    items = labeled(args.dataset, args.limit)
    if not items:
        print("В наборе нет размеченных вакансий (поле label)", file=sys.stderr)
        return 1

    meta = {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "prompt_version": PROMPT_VERSION,
        "models": settings.models,
        "dataset": args.dataset.name,
    }
    print(
        f"Промпт {PROMPT_VERSION}; модели: {', '.join(settings.models)}; вакансий: {len(items)}\n"
    )
    resume = args.resume.read_text(encoding="utf-8")
    out = args.out.open("w", encoding="utf-8") if args.out else None
    try:
        if out is not None:
            out.write(json.dumps({"meta": meta}, ensure_ascii=False) + "\n")
        report = asyncio.run(run(items, resume, settings, out=out))
        if out is not None:
            summary = {"report": report.as_dict() | {"meta": meta}}
            out.write(json.dumps(summary, ensure_ascii=False) + "\n")
    except PaidUsageError:
        return 2
    finally:
        if out is not None:
            out.close()
    print("\n" + format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

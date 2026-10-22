"""Размеченный набор вакансий для проверки качества оценки (scripts/eval.py).

Формат — JSON Lines, по вакансии на строку:
{"id": "...", "title": "...", "company": "...", "salary": "...", "work_formats": ["remote"],
 "description": "...", "label": "apply" | "maybe" | "skip"}
Пустой label — вакансия ещё не размечена, при оценке пропускается.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import get_args

from app.domain.evaluation import Verdict
from app.llm.prompts import VacancyForPrompt, html_to_text

VERDICTS: frozenset[str] = frozenset(get_args(Verdict))


@dataclass(frozen=True, slots=True)
class LabeledVacancy:
    id: str
    vacancy: VacancyForPrompt
    label: Verdict | None


def to_record(item_id: str, vacancy: VacancyForPrompt, url: str | None = None) -> dict[str, object]:
    """Строка набора для разметки: описание уже без HTML, чтобы его было удобно читать."""
    record: dict[str, object] = {"id": item_id, **asdict(vacancy), "label": ""}
    record["work_formats"] = list(vacancy.work_formats)
    record["description"] = html_to_text(vacancy.description or "")
    if url:
        record["url"] = url
    return record


def load_dataset(path: Path) -> list[LabeledVacancy]:
    items = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        label = (record.get("label") or "").strip().lower() or None
        if label is not None and label not in VERDICTS:
            raise ValueError(f"{path}:{number}: неизвестная метка {label!r}")
        items.append(
            LabeledVacancy(
                id=str(record["id"]),
                vacancy=VacancyForPrompt(
                    title=record["title"],
                    company=record.get("company"),
                    salary=record.get("salary"),
                    work_formats=tuple(record.get("work_formats") or ()),
                    description=record.get("description"),
                ),
                label=label,  # type: ignore[arg-type]  # проверено по VERDICTS выше
            )
        )
    return items

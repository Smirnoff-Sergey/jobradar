"""Метрики качества оценки на размеченном наборе."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.domain.evaluation import Verdict


@dataclass(frozen=True, slots=True)
class Prediction:
    label: Verdict
    predicted: Verdict | None  # None — модель не дала валидного ответа


@dataclass(frozen=True, slots=True)
class QualityReport:
    total: int
    answered: int
    exact: int
    # «Откликаться или нет»: apply и maybe против skip — это решение важнее точного вердикта.
    binary: int
    confusion: Counter[tuple[str, str]] = field(default_factory=Counter)

    @property
    def exact_rate(self) -> float:
        return self.exact / self.answered if self.answered else 0.0

    @property
    def binary_rate(self) -> float:
        return self.binary / self.answered if self.answered else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "answered": self.answered,
            "exact": self.exact,
            "binary": self.binary,
            "confusion": [
                {"label": label, "predicted": predicted, "count": count}
                for (label, predicted), count in sorted(self.confusion.items())
            ],
        }


def _worth_applying(verdict: Verdict) -> bool:
    return verdict != "skip"


def compare(predictions: Sequence[Prediction]) -> QualityReport:
    answered = [p for p in predictions if p.predicted is not None]
    return QualityReport(
        total=len(predictions),
        answered=len(answered),
        exact=sum(p.predicted == p.label for p in answered),
        binary=sum(
            p.predicted is not None and _worth_applying(p.predicted) == _worth_applying(p.label)
            for p in answered
        ),
        confusion=Counter((p.label, p.predicted or "нет ответа") for p in predictions),
    )


def format_report(report: QualityReport) -> str:
    verdicts = ("apply", "maybe", "skip", "нет ответа")
    lines = [
        f"Вакансий: {report.total}, с валидным ответом: {report.answered}",
        f"Точный вердикт: {report.exact}/{report.answered} ({report.exact_rate:.0%})",
        f"Откликаться или нет: {report.binary}/{report.answered} ({report.binary_rate:.0%})",
        "",
        "Метка \\ ответ модели: " + " | ".join(verdicts),
    ]
    for label in verdicts[:3]:
        counts = " | ".join(str(report.confusion[(label, predicted)]) for predicted in verdicts)
        lines.append(f"{label:>5}: {counts}")
    return "\n".join(lines)

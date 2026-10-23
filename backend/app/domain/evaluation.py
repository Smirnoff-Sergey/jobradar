"""Схема ответа LLM об оценке вакансии и правила его проверки."""

from functools import cache
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Verdict = Literal["apply", "maybe", "skip"]
Severity = Literal["blocker", "minor"]
# pending — пара захвачена задачей, done — оценка готова, failed — модель не справилась.
EvaluationStatus = Literal["pending", "done", "failed"]
PENDING: EvaluationStatus = "pending"
DONE: EvaluationStatus = "done"
FAILED: EvaluationStatus = "failed"

# Границы балла для вердиктов. Модели склонны путать шкалу (балл 2 при «maybe»),
# поэтому согласованность проверяется, а не принимается на веру.
APPLY_MIN_SCORE = 70
MAYBE_MIN_SCORE = 40


def verdict_for(score: int) -> Verdict:
    if score >= APPLY_MIN_SCORE:
        return "apply"
    if score >= MAYBE_MIN_SCORE:
        return "maybe"
    return "skip"


class StrictModel(BaseModel):
    # extra="forbid" даёт в JSON-схеме additionalProperties: false — этого требует strict-режим.
    model_config = ConfigDict(extra="forbid")


class Match(StrictModel):
    requirement: str = Field(description="Требование вакансии")
    evidence: str = Field(description="Чем резюме это подтверждает")


class Gap(StrictModel):
    requirement: str = Field(description="Требование вакансии, которого нет в резюме")
    severity: Severity = Field(description="blocker — обязательное, minor — желательное")


class EvaluationResult(StrictModel):
    score: int = Field(ge=0, le=100, description="Соответствие от 0 до 100")
    verdict: Verdict
    matches: list[Match]
    gaps: list[Gap]
    dealbreakers: list[str] = Field(description="Условия вакансии, мешающие отклику")

    @model_validator(mode="after")
    def _verdict_matches_score(self) -> Self:
        expected = verdict_for(self.score)
        if self.verdict != expected:
            raise ValueError(
                f"вердикт {self.verdict!r} не соответствует баллу {self.score} "
                f"(ожидался {expected!r})"
            )
        return self


@cache
def evaluation_json_schema() -> dict[str, Any]:
    return EvaluationResult.model_json_schema()

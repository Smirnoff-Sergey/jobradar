"""Схема ответа LLM с черновиком письма и привязка письма к фактам резюме.

Резюме уходит модели пронумерованными фрагментами, и факт письма ссылается на номер
фрагмента. Цитату под письмом подставляет сервис — дословно из резюме: модели нечего
пересказывать своими словами, а несуществующий номер отклоняется проверкой.
"""

import re
from functools import cache
from typing import Any, Self

from pydantic import BaseModel, Field, ValidationInfo, model_validator

from app.domain.evaluation import StrictModel

# Длинная строка резюме (абзац) режется на предложения: цитата под письмом — короткая.
MAX_FRAGMENT_CHARS = 300
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")
_BULLET = re.compile(r"^[\s\-*•–—]+")


def resume_fragments(text: str) -> list[str]:
    """Фрагменты резюме для ссылок из письма: строки, а длинные строки — предложения."""
    fragments: list[str] = []
    for line in text.splitlines():
        line = _BULLET.sub("", line).strip()
        if not line:
            continue
        parts = _SENTENCE_END.split(line) if len(line) > MAX_FRAGMENT_CHARS else [line]
        fragments.extend(part.strip() for part in parts if part.strip())
    return fragments


class LetterFactAnswer(StrictModel):
    claim: str = Field(description="Утверждение письма о кандидате")
    resume_fragment: int = Field(description="Номер фрагмента резюме, который это подтверждает")


class LetterResult(StrictModel):
    text: str = Field(description="Текст письма без подписи и контактов")
    facts: list[LetterFactAnswer] = Field(
        description="Факты из резюме, на которые опирается письмо"
    )

    @model_validator(mode="after")
    def _grounded_in_resume(self, info: ValidationInfo) -> Self:
        if not self.text.strip():
            raise ValueError("пустой текст письма")
        if not self.facts:
            raise ValueError("нет фактов из резюме")
        fragments = (info.context or {}).get("fragments")
        if isinstance(fragments, int):
            # Номера фактов, а не их текст: в ошибки не попадают фрагменты ответа модели.
            missing = [
                str(index)
                for index, fact in enumerate(self.facts)
                if not 1 <= fact.resume_fragment <= fragments
            ]
            if missing:
                raise ValueError(f"нет такого фрагмента резюме: facts[{', '.join(missing)}]")
        return self


class LetterFact(BaseModel):
    """Сохранённый факт письма: утверждение и дословная цитата резюме."""

    claim: str
    resume_quote: str


def resolve_facts(result: LetterResult, fragments: list[str]) -> list[LetterFact]:
    return [
        LetterFact(claim=fact.claim, resume_quote=fragments[fact.resume_fragment - 1])
        for fact in result.facts
    ]


@cache
def letter_json_schema() -> dict[str, Any]:
    return LetterResult.model_json_schema()

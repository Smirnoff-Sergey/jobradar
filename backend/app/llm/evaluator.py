"""Оценка одной вакансии через LLM без БД — общая для сервиса и scripts/eval.py."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

from pydantic import ValidationError

from app.core.errors import LLMResponseError
from app.domain.evaluation import EvaluationResult, evaluation_json_schema
from app.llm.base import LLMClient, LLMResponse
from app.llm.prompts import SCHEMA_NAME, SYSTEM_PROMPT, VacancyForPrompt, build_user_prompt

logger = logging.getLogger(__name__)

# Невалидный ответ повторяем один раз: бесплатные модели иногда сбиваются со схемы,
# но больше двух попыток — уже трата дневного лимита впустую.
MAX_ATTEMPTS = 2

ReserveRequest = Callable[[], Awaitable[bool]]


class BudgetExhaustedError(Exception):
    """Дневной лимит запросов к LLM исчерпан."""


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    result: EvaluationResult
    model: str
    attempts: int
    # Суммы по всем попыткам, включая отклонённые ответы.
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal


def _summary(error: ValidationError) -> str:
    # Без input: в сообщение не должны попадать фрагменты ответа модели.
    return "; ".join(
        f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
        for item in error.errors(include_input=False, include_url=False)[:3]
    )


async def request_evaluation(
    client: LLMClient,
    resume: str,
    vacancy: VacancyForPrompt,
    *,
    max_chars: int,
    reserve_request: ReserveRequest | None = None,
) -> EvaluationOutcome:
    """Запрашивает оценку и проверяет её схемой.

    reserve_request вызывается перед каждым запросом: False — лимит исчерпан.
    """
    user_prompt = build_user_prompt(resume, vacancy, max_chars=max_chars)
    responses: list[LLMResponse] = []
    problem = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if reserve_request is not None and not await reserve_request():
            raise BudgetExhaustedError
        response = await client.complete_json(
            system=SYSTEM_PROMPT,
            user=user_prompt,
            schema_name=SCHEMA_NAME,
            schema=evaluation_json_schema(),
        )
        responses.append(response)
        try:
            result = EvaluationResult.model_validate(response.content)
        except ValidationError as exc:
            problem = _summary(exc)
            logger.warning(
                "Модель %s ответила не по схеме (попытка %d): %s", response.model, attempt, problem
            )
            continue
        return EvaluationOutcome(
            result=result,
            model=response.model,
            attempts=attempt,
            tokens_in=sum(r.tokens_in for r in responses),
            tokens_out=sum(r.tokens_out for r in responses),
            cost_usd=sum((r.cost_usd for r in responses), Decimal(0)),
        )
    raise LLMResponseError(f"Модель дважды ответила не по схеме: {problem}")

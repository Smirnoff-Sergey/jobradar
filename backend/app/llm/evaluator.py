"""Запросы к LLM со структурированным ответом без БД — общие для сервисов и scripts/eval.py."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError

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
class LLMOutcome[T: BaseModel]:
    result: T
    model: str
    attempts: int
    # Суммы по всем попыткам, включая отклонённые ответы.
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal


type EvaluationOutcome = LLMOutcome[EvaluationResult]


def _summary(error: ValidationError) -> str:
    # Без input: в сообщение не должны попадать фрагменты ответа модели.
    return "; ".join(
        f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
        for item in error.errors(include_input=False, include_url=False)[:3]
    )


async def request_validated[T: BaseModel](
    client: LLMClient,
    result_type: type[T],
    *,
    system: str,
    user: str,
    schema_name: str,
    schema: dict[str, Any],
    context: dict[str, Any] | None = None,
    reserve_request: ReserveRequest | None = None,
) -> LLMOutcome[T]:
    """Запрашивает ответ по JSON-схеме и проверяет его моделью result_type.

    context передаётся в валидаторы модели (например, текст резюме для сверки цитат).
    reserve_request вызывается перед каждым запросом: False — лимит исчерпан.
    """
    responses: list[LLMResponse] = []
    problem = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if reserve_request is not None and not await reserve_request():
            raise BudgetExhaustedError
        response = await client.complete_json(
            system=system, user=user, schema_name=schema_name, schema=schema
        )
        responses.append(response)
        try:
            result = result_type.model_validate(response.content, context=context)
        except ValidationError as exc:
            problem = _summary(exc)
            logger.warning(
                "Модель %s ответила не по схеме (попытка %d): %s", response.model, attempt, problem
            )
            continue
        return LLMOutcome(
            result=result,
            model=response.model,
            attempts=attempt,
            tokens_in=sum(r.tokens_in for r in responses),
            tokens_out=sum(r.tokens_out for r in responses),
            cost_usd=sum((r.cost_usd for r in responses), Decimal(0)),
        )
    raise LLMResponseError(f"Модель дважды ответила не по схеме: {problem}")


async def request_evaluation(
    client: LLMClient,
    resume: str,
    vacancy: VacancyForPrompt,
    *,
    max_chars: int,
    reserve_request: ReserveRequest | None = None,
) -> EvaluationOutcome:
    """Оценка вакансии по резюме, проверенная схемой."""
    return await request_validated(
        client,
        EvaluationResult,
        system=SYSTEM_PROMPT,
        user=build_user_prompt(resume, vacancy, max_chars=max_chars),
        schema_name=SCHEMA_NAME,
        schema=evaluation_json_schema(),
        reserve_request=reserve_request,
    )

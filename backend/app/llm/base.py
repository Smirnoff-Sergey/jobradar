from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: dict[str, Any]
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal


class LLMClient(Protocol):
    """Запрос к модели со структурированным ответом по JSON-схеме."""

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> LLMResponse: ...

"""Клиент OpenAI-совместимого chat completions API (OpenRouter)."""

import json
import logging
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import LLMSettings, is_free_model
from app.core.errors import (
    LLMResponseError,
    PaidUsageError,
    PermanentExternalError,
    TransientExternalError,
)
from app.core.http import RetryPolicy, request_json
from app.llm.base import LLMResponse

logger = logging.getLogger(__name__)

# Повторы — уровнем выше: каждый запрос расходует дневной лимит и учитывается в нём,
# поэтому HTTP-клиент не должен повторять запрос молча.
_NO_RETRY = RetryPolicy(max_attempts=1)
_TRANSIENT_ERROR_CODES = frozenset({408, 429, 500, 502, 503, 504})


class OpenRouterClient:
    def __init__(self, client: httpx.AsyncClient, settings: LLMSettings) -> None:
        if settings.api_key is None:
            raise ValueError("не задан JOBRADAR_LLM__API_KEY")
        self._client = client
        self._settings = settings
        self._headers = {"Authorization": f"Bearer {settings.api_key.get_secret_value()}"}

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> LLMResponse:
        body = {
            # Список моделей: если первая недоступна, OpenRouter сам переходит к следующей.
            "models": self._settings.models,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
            "provider": {
                # Только провайдеры, которые умеют response_format.
                "require_parameters": True,
                # Цена — ноль: OpenRouter сам отсечёт платные маршруты.
                "max_price": {"prompt": 0, "completion": 0},
                "data_collection": "deny" if self._settings.deny_data_collection else "allow",
            },
            "temperature": 0,
        }
        data = await request_json(
            self._client,
            "POST",
            f"{self._settings.base_url}/chat/completions",
            policy=_NO_RETRY,
            json=body,
            headers=self._headers,
        )
        return self._parse(data)

    def _parse(self, data: Any) -> LLMResponse:
        if not isinstance(data, dict):
            raise LLMResponseError("ответ LLM не является объектом JSON")
        # Ошибка провайдера может прийти со статусом 200 — смотрим тело, а не только код.
        if error := data.get("error"):
            self._raise_provider_error(error)

        model = str(data.get("model") or "")
        usage = data.get("usage") or {}
        # Главная гарантия бесплатности — нулевая стоимость в ответе. Без сведений о цене
        # ответ считается небезопасным (fail-closed). Имя модели провайдер может вернуть
        # без суффикса :free, поэтому по нему только предупреждаем.
        if "cost" not in usage:
            raise PaidUsageError("OpenRouter не сообщил стоимость запроса")
        cost = Decimal(str(usage["cost"] or 0))
        if cost > 0:
            logger.error("Платный ответ LLM: модель %s, стоимость %s", model, cost)
            raise PaidUsageError(f"Платный запрос к LLM: модель {model}, стоимость ${cost}")
        if model and not is_free_model(model) and f"{model}:free" not in self._settings.models:
            logger.warning("Ответила модель не из списка бесплатных: %s", model)

        try:
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMResponseError("модель вернула не JSON") from exc
        if not isinstance(parsed, dict):
            raise LLMResponseError("модель вернула JSON не того вида")

        return LLMResponse(
            content=parsed,
            model=model,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            cost_usd=cost,
        )

    @staticmethod
    def _raise_provider_error(error: Any) -> None:
        code = error.get("code") if isinstance(error, dict) else None
        message = error.get("message") if isinstance(error, dict) else str(error)
        text = f"OpenRouter: {message} (код {code})"
        if code in _TRANSIENT_ERROR_CODES:
            raise TransientExternalError(text)
        raise PermanentExternalError(text)

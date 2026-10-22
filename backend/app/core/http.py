"""HTTP-запросы к внешним API с повторами только для временных ошибок."""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.errors import PermanentExternalError, TransientExternalError

logger = logging.getLogger(__name__)

USER_AGENT = "JobRadar/0.1 (+https://github.com/Smirnoff-Sergey/jobradar)"

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 4
    backoff_seconds: float = 1.0
    max_delay_seconds: float = 60.0

    def delay(self, attempt: int, retry_after: float | None) -> float:
        """Пауза перед следующей попыткой: Retry-After от сервера или экспонента с джиттером."""
        if retry_after is not None:
            return min(retry_after, self.max_delay_seconds)
        ceiling = min(self.max_delay_seconds, self.backoff_seconds * 2 ** (attempt - 1))
        return random.uniform(0, ceiling)


def create_client(timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    )


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None  # формат HTTP-даты не поддерживаем: обычная экспонента тоже подойдёт


async def _get_once(
    client: httpx.AsyncClient, url: str, params: Mapping[str, str | int] | None
) -> Any:
    try:
        response = await client.get(url, params=params)
    except httpx.TimeoutException as exc:
        raise TransientExternalError(f"Таймаут запроса к {url}") from exc
    except httpx.TransportError as exc:
        raise TransientExternalError(f"Сетевая ошибка при запросе к {url}: {exc}") from exc

    status = response.status_code
    if status == httpx.codes.TOO_MANY_REQUESTS:
        raise TransientExternalError(
            f"{url}: превышен лимит запросов",
            retry_after=_parse_retry_after(response.headers.get("Retry-After")),
        )
    if status >= httpx.codes.INTERNAL_SERVER_ERROR:
        raise TransientExternalError(f"{url}: HTTP {status}")
    if status >= httpx.codes.BAD_REQUEST:
        raise PermanentExternalError(f"{url}: HTTP {status}")
    try:
        return response.json()
    except ValueError as exc:
        raise PermanentExternalError(f"{url}: ответ не в формате JSON") from exc


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Mapping[str, str | int] | None = None,
    policy: RetryPolicy,
    sleep: Sleep = asyncio.sleep,
) -> Any:
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await _get_once(client, url, params)
        except TransientExternalError as exc:
            if attempt == policy.max_attempts:
                raise
            delay = policy.delay(attempt, exc.retry_after)
            logger.warning(
                "Попытка %d/%d не удалась (%s), повтор через %.1f с",
                attempt,
                policy.max_attempts,
                exc.message,
                delay,
            )
            await sleep(delay)
    raise AssertionError("недостижимо: цикл либо возвращает ответ, либо бросает ошибку")

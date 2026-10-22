from collections.abc import Callable

import httpx

from app.core.config import CollectorSettings
from app.core.errors import NotFoundError
from app.core.http import RetryPolicy
from app.sources.base import SourceAdapter
from app.sources.getmatch import GetmatchAdapter

AdapterFactory = Callable[[httpx.AsyncClient, RetryPolicy, CollectorSettings], SourceAdapter]

_FACTORIES: dict[str, AdapterFactory] = {
    GetmatchAdapter.code: lambda client, policy, settings: GetmatchAdapter(
        client, policy, page_size=settings.getmatch_page_size
    ),
}

SOURCE_CODES = frozenset(_FACTORIES)


def create_adapter(
    code: str, client: httpx.AsyncClient, settings: CollectorSettings
) -> SourceAdapter:
    factory = _FACTORIES.get(code)
    if factory is None:
        raise NotFoundError(f"Неизвестный источник: {code}")
    policy = RetryPolicy(
        max_attempts=settings.http_max_attempts,
        backoff_seconds=settings.http_backoff_seconds,
    )
    return factory(client, policy, settings)

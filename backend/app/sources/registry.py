import re
from collections.abc import Callable

import httpx

from app.core.config import CollectorSettings
from app.core.errors import InvalidUrlError, NotFoundError
from app.core.http import RetryPolicy
from app.sources.base import SourceAdapter
from app.sources.getmatch import VACANCY_URL as GETMATCH_URL
from app.sources.getmatch import GetmatchAdapter

AdapterFactory = Callable[[httpx.AsyncClient, RetryPolicy, CollectorSettings], SourceAdapter]

_FACTORIES: dict[str, AdapterFactory] = {
    GetmatchAdapter.code: lambda client, policy, settings: GetmatchAdapter(
        client, policy, page_size=settings.getmatch_page_size
    ),
}

SOURCE_CODES = frozenset(_FACTORIES)

# Ссылки на вакансии, которые можно добавить вручную: код источника → шаблон с id в группе.
_VACANCY_URLS: dict[str, re.Pattern[str]] = {GetmatchAdapter.code: GETMATCH_URL}


def parse_vacancy_url(url: str) -> tuple[str, str]:
    """Код источника и id вакансии из ссылки на её страницу."""
    for code, pattern in _VACANCY_URLS.items():
        if match := pattern.match(url.strip()):
            return code, match.group(1)
    raise InvalidUrlError(
        "Это не ссылка на вакансию getmatch.ru: ожидается getmatch.ru/vacancies/…"
    )


def create_adapter(
    code: str,
    client: httpx.AsyncClient,
    settings: CollectorSettings,
    *,
    max_attempts: int | None = None,
) -> SourceAdapter:
    """max_attempts — меньше повторов, когда ответа ждёт пользователь (импорт по ссылке)."""
    factory = _FACTORIES.get(code)
    if factory is None:
        raise NotFoundError(f"Неизвестный источник: {code}")
    policy = RetryPolicy(
        max_attempts=max_attempts or settings.http_max_attempts,
        backoff_seconds=settings.http_backoff_seconds,
    )
    return factory(client, policy, settings)

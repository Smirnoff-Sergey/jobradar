"""Адаптер getmatch.ru: открытый API без авторизации."""

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.errors import PermanentExternalError, TransientExternalError
from app.core.http import RetryPolicy, get_json
from app.sources.base import VacancyData, WorkFormat

logger = logging.getLogger(__name__)

BASE_URL = "https://getmatch.ru"
OFFERS_URL = f"{BASE_URL}/api/offers"

_WORK_FORMATS: dict[str, WorkFormat] = {
    "remote": "remote",
    "hybrid": "hybrid",
    "office": "office",
    "relocation_company": "relocation",
}
_SALARY_GROSS = {"gross": True, "net": False}


def _published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    published = datetime.fromisoformat(value)
    # API отдаёт время без зоны; считаем его UTC.
    return published if published.tzinfo else published.replace(tzinfo=UTC)


def _salary(offer: dict[str, Any]) -> dict[str, Any]:
    if offer.get("salary_hidden", True):
        return {}
    return {
        "salary_from": offer.get("salary_display_from"),
        "salary_to": offer.get("salary_display_to"),
        "salary_currency": offer.get("salary_currency"),
        "salary_gross": _SALARY_GROSS.get(offer.get("salary_taxes") or ""),
    }


def parse_offer(offer: dict[str, Any]) -> VacancyData:
    formats = {
        _WORK_FORMATS[item["format"]]
        for item in offer.get("location_items") or []
        if not item.get("exclude") and item.get("format") in _WORK_FORMATS
    }
    return VacancyData(
        external_id=str(offer["id"]),
        url=BASE_URL + offer["url"],
        title=offer["position"].strip(),
        company=(offer.get("company") or {}).get("name"),
        **_salary(offer),
        work_formats=tuple(sorted(formats)),
        # Тип договора getmatch не сообщает.
        contract_types=(),
        short_description=offer.get("offer_description"),
        published_at=_published_at(offer.get("published_at")),
        raw=offer,
    )


class GetmatchAdapter:
    code = "getmatch"

    def __init__(self, client: httpx.AsyncClient, policy: RetryPolicy, page_size: int = 20) -> None:
        self._client = client
        self._policy = policy
        self._page_size = page_size

    async def iter_pages(self) -> AsyncIterator[list[VacancyData]]:
        # Выдача не отсортирована строго по дате (закреплённые вакансии идут первыми),
        # поэтому остановиться на первой знакомой вакансии нельзя — обходим все страницы.
        offset = 0
        while True:
            data = await get_json(
                self._client,
                OFFERS_URL,
                params={"pa": "all", "limit": self._page_size, "offset": offset},
                policy=self._policy,
            )
            try:
                offers: list[dict[str, Any]] = data["offers"]
                total = int(data["meta"]["total"])
            except (KeyError, TypeError, ValueError) as exc:
                raise PermanentExternalError(
                    "getmatch: неожиданный формат списка вакансий"
                ) from exc
            if not offers:
                if offset < total:
                    # Пустая страница посреди обхода — сбой API, а не конец выдачи. Если принять
                    # её за конец, коллектор деактивирует все вакансии, до которых не дошёл.
                    raise TransientExternalError(
                        f"getmatch: пустая страница на offset={offset} при total={total}"
                    )
                return
            yield self._parse_page(offers)
            offset += self._page_size
            if offset >= total:
                return

    async def fetch_description(self, external_id: str) -> str | None:
        data = await get_json(self._client, f"{OFFERS_URL}/{external_id}", policy=self._policy)
        description = data.get("description") or data.get("offer_description")
        return str(description) if description else None

    @staticmethod
    def _parse_page(offers: list[dict[str, Any]]) -> list[VacancyData]:
        page = []
        for offer in offers:
            try:
                page.append(parse_offer(offer))
            except (KeyError, TypeError, ValueError):
                # Одна битая запись не должна останавливать весь сбор.
                logger.warning(
                    "getmatch: пропущена вакансия с неожиданным форматом: %r", offer.get("id")
                )
        return page

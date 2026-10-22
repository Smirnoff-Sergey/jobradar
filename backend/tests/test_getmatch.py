import dataclasses
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.core.errors import PermanentExternalError, TransientExternalError
from app.core.http import RetryPolicy
from app.sources.base import VacancyData
from app.sources.getmatch import OFFERS_URL, GetmatchAdapter, parse_offer
from tests.fakes import load_getmatch_fixture as load_fixture

POLICY = RetryPolicy(max_attempts=1)


async def collect(adapter: GetmatchAdapter) -> list[list[VacancyData]]:
    return [page async for page in adapter.iter_pages()]


def test_parse_offer_with_salary() -> None:
    item = parse_offer(load_fixture()["offers"][0])

    assert item.external_id == "101"
    assert item.title == "Python Backend Developer"
    assert item.url == "https://getmatch.ru/vacancies/101-python-backend-developer"
    assert item.company == "Пример Тех"
    assert (item.salary_from, item.salary_to, item.salary_currency) == (250_000, 320_000, "RUB")
    assert item.salary_gross is False
    assert item.work_formats == ("office", "remote")
    assert item.contract_types == ()
    assert item.published_at == datetime(2026, 10, 20, 10, 0, tzinfo=UTC)


def test_parse_offer_with_hidden_salary_and_excluded_location() -> None:
    item = parse_offer(load_fixture()["offers"][1])

    assert item.salary_from is None
    assert item.salary_currency is None
    assert item.salary_gross is None
    # Удалёнка из Казани исключена (exclude=true), релокация нормализуется.
    assert item.work_formats == ("hybrid", "relocation")


def test_content_hash_ignores_raw_and_tracks_fields() -> None:
    item = parse_offer(load_fixture()["offers"][0])
    same = dataclasses.replace(item, raw={"viewed": True})

    assert same.content_hash() == item.content_hash()
    assert (
        parse_offer({**item.raw, "position": "Go Developer"}).content_hash() != item.content_hash()
    )


@respx.mock
async def test_iter_pages_skips_broken_offers() -> None:
    respx.get(OFFERS_URL).respond(json=load_fixture())

    async with httpx.AsyncClient() as client:
        pages = await collect(GetmatchAdapter(client, POLICY))

    assert [[item.external_id for item in page] for page in pages] == [["101", "102"]]


@respx.mock
async def test_iter_pages_walks_offsets_until_total() -> None:
    offers = load_fixture()["offers"][:2]
    route = respx.get(OFFERS_URL).mock(
        side_effect=[
            httpx.Response(200, json={"meta": {"total": 3}, "offers": offers[:1]}),
            httpx.Response(200, json={"meta": {"total": 3}, "offers": offers[1:]}),
            httpx.Response(200, json={"meta": {"total": 3}, "offers": offers[:1]}),
        ]
    )

    async with httpx.AsyncClient() as client:
        pages = await collect(GetmatchAdapter(client, POLICY, page_size=1))

    assert len(pages) == 3
    offsets = [call.request.url.params["offset"] for call in route.calls]
    assert offsets == ["0", "1", "2"]


@respx.mock
async def test_empty_result() -> None:
    respx.get(OFFERS_URL).respond(json={"meta": {"total": 0}, "offers": []})

    async with httpx.AsyncClient() as client:
        assert await collect(GetmatchAdapter(client, POLICY)) == []


@respx.mock
async def test_empty_page_before_total_is_an_error() -> None:
    offers = load_fixture()["offers"][:1]
    respx.get(OFFERS_URL).mock(
        side_effect=[
            httpx.Response(200, json={"meta": {"total": 3}, "offers": offers}),
            httpx.Response(200, json={"meta": {"total": 3}, "offers": []}),
        ]
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(TransientExternalError, match="пустая страница"):
            await collect(GetmatchAdapter(client, POLICY, page_size=1))


@respx.mock
async def test_unexpected_list_format() -> None:
    respx.get(OFFERS_URL).respond(json={"items": []})

    async with httpx.AsyncClient() as client:
        with pytest.raises(PermanentExternalError, match="формат"):
            await collect(GetmatchAdapter(client, POLICY))


@respx.mock
async def test_fetch_description() -> None:
    respx.get(f"{OFFERS_URL}/101").respond(json={"description": "<p>Полный текст</p>"})
    respx.get(f"{OFFERS_URL}/102").respond(json={"offer_description": "Кратко"})
    respx.get(f"{OFFERS_URL}/103").respond(json={})

    async with httpx.AsyncClient() as client:
        adapter = GetmatchAdapter(client, POLICY)
        assert await adapter.fetch_description("101") == "<p>Полный текст</p>"
        assert await adapter.fetch_description("102") == "Кратко"
        assert await adapter.fetch_description("103") is None

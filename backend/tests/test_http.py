import httpx
import pytest
import respx

from app.core.errors import ExternalAccessError, PermanentExternalError, TransientExternalError
from app.core.http import RetryPolicy, get_json

URL = "https://api.example.com/items"
POLICY = RetryPolicy(max_attempts=3, backoff_seconds=1.0)


class RecordingSleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


@pytest.fixture
def sleep() -> RecordingSleep:
    return RecordingSleep()


async def get(sleep: RecordingSleep) -> object:
    async with httpx.AsyncClient() as client:
        return await get_json(client, URL, policy=POLICY, sleep=sleep)


@respx.mock
async def test_returns_json(sleep: RecordingSleep) -> None:
    respx.get(URL).respond(json={"ok": True})

    assert await get(sleep) == {"ok": True}
    assert sleep.delays == []


@respx.mock
async def test_retries_server_errors(sleep: RecordingSleep) -> None:
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(200, json=[1])]
    )

    assert await get(sleep) == [1]
    assert route.call_count == 3
    assert len(sleep.delays) == 2
    assert all(0 <= delay <= 2 for delay in sleep.delays)


@respx.mock
async def test_respects_retry_after(sleep: RecordingSleep) -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json={}),
        ]
    )

    await get(sleep)

    assert sleep.delays == [7.0]


@respx.mock
async def test_retries_network_errors_and_gives_up(sleep: RecordingSleep) -> None:
    route = respx.get(URL).mock(side_effect=httpx.ConnectTimeout("timeout"))

    with pytest.raises(TransientExternalError, match="Таймаут"):
        await get(sleep)

    assert route.call_count == POLICY.max_attempts
    assert len(sleep.delays) == POLICY.max_attempts - 1


@respx.mock
async def test_client_errors_are_not_retried(sleep: RecordingSleep) -> None:
    route = respx.get(URL).respond(400)

    with pytest.raises(PermanentExternalError, match="HTTP 400"):
        await get(sleep)

    assert route.call_count == 1
    assert sleep.delays == []


@respx.mock
async def test_invalid_json_is_permanent(sleep: RecordingSleep) -> None:
    respx.get(URL).respond(200, text="<html>")

    with pytest.raises(PermanentExternalError, match="JSON"):
        await get(sleep)


def test_backoff_grows_and_is_capped() -> None:
    policy = RetryPolicy(backoff_seconds=1.0, max_delay_seconds=5.0)

    assert all(0 <= policy.delay(1, None) <= 1 for _ in range(50))
    assert all(0 <= policy.delay(10, None) <= 5 for _ in range(50))
    assert policy.delay(1, retry_after=100) == 5.0


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
async def test_access_denied(sleep: RecordingSleep, status: int) -> None:
    route = respx.get(URL).respond(status)

    with pytest.raises(ExternalAccessError, match="доступ запрещён"):
        await get(sleep)
    assert route.call_count == 1

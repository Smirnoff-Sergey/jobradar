from httpx import AsyncClient

from app.db.models import User
from tests.fakes import FakeTaskQueue

PROFILE = {
    "title_keywords": [" python ", "backend"],
    "stop_words": ["devops"],
    "min_salary": 150_000,
    "min_salary_is_net": True,
    "remote_only": True,
    "contract_types": ["GPH", "IP"],
}


async def test_get_creates_default_profile(
    client: AsyncClient, user: User, auth_headers: dict[str, str], task_queue: FakeTaskQueue
) -> None:
    response = await client.get("/api/v1/search-profile", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["title_keywords"] == []
    assert body["remote_only"] is True
    assert body["min_salary"] is None
    assert task_queue.refiltered == [user.id]


async def test_put_saves_and_queues_refilter(
    client: AsyncClient, user: User, auth_headers: dict[str, str], task_queue: FakeTaskQueue
) -> None:
    response = await client.put("/api/v1/search-profile", json=PROFILE, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["refilter_task_id"] == "refilter-2"  # первая — от создания профиля
    assert body["profile"]["title_keywords"] == ["python", "backend"]
    assert body["profile"]["contract_types"] == ["GPH", "IP"]
    assert task_queue.refiltered == [user.id, user.id]

    saved = await client.get("/api/v1/search-profile", headers=auth_headers)
    assert saved.json()["stop_words"] == ["devops"]


async def test_put_validates(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.put(
        "/api/v1/search-profile",
        json={**PROFILE, "contract_types": ["FREELANCE"], "min_salary": -1, "stop_words": [" "]},
        headers=auth_headers,
    )

    assert response.status_code == 422
    fields = {item["loc"][1] for item in response.json()["error"]["details"]}
    assert fields == {"contract_types", "min_salary", "stop_words"}

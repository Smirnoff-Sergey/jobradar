from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SearchProfile
from tests.fakes import FakeAdapter, collector, vacancy


async def seed(db_session: AsyncSession) -> None:
    adapter = FakeAdapter(
        pages=[
            [
                vacancy("1"),
                vacancy("2", title="PHP Developer"),
                vacancy("3", salary_from=None, salary_to=None),
            ]
        ]
    )
    await collector(db_session, adapter).collect()


async def test_list_returns_passed_by_default(
    client: AsyncClient,
    db_session: AsyncSession,
    profile: SearchProfile,
    auth_headers: dict[str, str],
) -> None:
    await seed(db_session)

    response = await client.get("/api/v1/vacancies", headers=auth_headers)

    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 2
    assert {item["title"] for item in page["items"]} == {
        "Python Backend Developer 1",
        "Python Backend Developer 3",
    }
    unknown = next(item for item in page["items"] if item["salary_to"] is None)
    assert unknown["filter"] == {"passed": True, "reasons": [], "salary_unknown": True}


async def test_list_rejected_and_pagination(
    client: AsyncClient,
    db_session: AsyncSession,
    profile: SearchProfile,
    auth_headers: dict[str, str],
) -> None:
    await seed(db_session)

    rejected = await client.get(
        "/api/v1/vacancies", params={"status": "rejected"}, headers=auth_headers
    )
    everything = await client.get(
        "/api/v1/vacancies", params={"status": "all", "limit": 2}, headers=auth_headers
    )

    assert [item["title"] for item in rejected.json()["items"]] == ["PHP Developer"]
    assert rejected.json()["items"][0]["filter"]["reasons"] == ["в названии нет ключевых слов"]
    assert everything.json()["total"] == 3
    assert len(everything.json()["items"]) == 2


async def test_list_validates_params(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.get(
        "/api/v1/vacancies", params={"status": "maybe", "limit": 1000}, headers=auth_headers
    )

    assert response.status_code == 422


async def test_get_vacancy(
    client: AsyncClient,
    db_session: AsyncSession,
    profile: SearchProfile,
    auth_headers: dict[str, str],
) -> None:
    await seed(db_session)
    listed = (await client.get("/api/v1/vacancies", headers=auth_headers)).json()["items"][0]

    response = await client.get(f"/api/v1/vacancies/{listed['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["short_description"] == "FastAPI, PostgreSQL"
    assert response.json()["description"] is None


async def test_get_unknown_vacancy(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.get("/api/v1/vacancies/999999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_vacancies_require_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/vacancies")

    assert response.status_code == 401

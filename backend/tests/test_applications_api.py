from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.services.applications import ApplicationService
from app.services.auth import AuthService
from tests.fakes import ready_vacancy


async def put_status(
    client: AsyncClient, headers: dict[str, str], vacancy_id: int, **body: object
) -> dict[str, Any]:
    response = await client.put(
        f"/api/v1/vacancies/{vacancy_id}/application", json=body, headers=headers
    )
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


async def test_status_changes_are_logged(
    client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    target = await ready_vacancy(db_session, user)

    created = await put_status(client, auth_headers, target.id, status="applied")
    again = await put_status(client, auth_headers, target.id, status="applied")
    changed = await put_status(
        client, auth_headers, target.id, status="invited", notes="Созвон в пятницу"
    )

    assert created["id"] == again["id"] == changed["id"]
    assert (changed["status"], changed["notes"]) == ("invited", "Созвон в пятницу")
    detail = await client.get(f"/api/v1/applications/{created['id']}", headers=auth_headers)
    history = [(h["from_status"], h["to_status"]) for h in detail.json()["history"]]
    assert history == [(None, "applied"), ("applied", "invited")]  # повтор не пишется


async def test_patch_and_list(
    client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    first = await ready_vacancy(db_session, user, "1")
    second = await ready_vacancy(db_session, user, "2")
    application = await put_status(client, auth_headers, first.id, status="applied")
    await put_status(client, auth_headers, second.id, status="declined")

    response = await client.patch(
        f"/api/v1/applications/{application['id']}",
        json={"status": "rejected", "notes": "Отказ после интервью"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert [h["to_status"] for h in response.json()["history"]] == ["applied", "rejected"]

    page = (
        await client.get(
            "/api/v1/applications", params={"status": "rejected"}, headers=auth_headers
        )
    ).json()
    assert page["total"] == 1
    [item] = page["items"]
    assert (item["notes"], item["vacancy"]["title"]) == ("Отказ после интервью", first.title)
    assert (await client.get("/api/v1/applications", headers=auth_headers)).json()["total"] == 2


async def test_vacancies_show_application_status(
    client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    applied = await ready_vacancy(db_session, user, "1")
    other = await ready_vacancy(db_session, user, "2")
    await put_status(client, auth_headers, applied.id, status="applied")

    listed = (await client.get("/api/v1/vacancies", headers=auth_headers)).json()["items"]
    statuses = {
        item["id"]: item["application"] and item["application"]["status"] for item in listed
    }
    assert statuses == {applied.id: "applied", other.id: None}

    filtered = await client.get(
        "/api/v1/vacancies", params={"application_status": "applied"}, headers=auth_headers
    )
    assert [item["id"] for item in filtered.json()["items"]] == [applied.id]
    card = (await client.get(f"/api/v1/vacancies/{applied.id}", headers=auth_headers)).json()
    assert card["application"]["status"] == "applied"


async def test_foreign_and_missing(
    client: AsyncClient,
    db_session: AsyncSession,
    user: User,
    auth_service: AuthService,
    auth_headers: dict[str, str],
) -> None:
    other_user = await auth_service.create_user("other@example.com", "other-password")
    target = await ready_vacancy(db_session, other_user)
    foreign = await ApplicationService(db_session).set_status(other_user.id, target.id, "applied")

    for request in (
        client.get(f"/api/v1/applications/{foreign.id}", headers=auth_headers),
        client.patch(
            f"/api/v1/applications/{foreign.id}", json={"notes": "x"}, headers=auth_headers
        ),
    ):
        assert (await request).status_code == 404
    response = await client.put(
        "/api/v1/vacancies/999999/application", json={"status": "applied"}, headers=auth_headers
    )
    assert response.status_code == 404
    response = await client.put(
        f"/api/v1/vacancies/{target.id}/application", json={"status": "maybe"}, headers=auth_headers
    )
    assert response.status_code == 422

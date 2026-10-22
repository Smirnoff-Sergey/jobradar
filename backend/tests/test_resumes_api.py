from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import Evaluation, User
from app.services.auth import AuthService
from tests.fakes import active_resume, add_evaluation, ready_vacancy

TEXT = "Backend-разработчик: Python, Django, PostgreSQL, Celery, Docker. Опыт 4 года."


async def create(client: AsyncClient, headers: dict[str, str], **body: object) -> dict[str, object]:
    response = await client.post(
        "/api/v1/resumes", json={"title": "Основное", "text": TEXT, **body}, headers=headers
    )
    assert response.status_code == 201, response.text
    data: dict[str, object] = response.json()
    return data


async def test_create_and_list(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await create(client, auth_headers)

    listed = (await client.get("/api/v1/resumes", headers=auth_headers)).json()

    assert created["is_active"] is True
    assert [item["id"] for item in listed] == [created["id"]]


async def test_only_one_active(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    first = await create(client, auth_headers)
    second = await create(client, auth_headers, title="Второе")

    listed = (await client.get("/api/v1/resumes", headers=auth_headers)).json()
    assert {item["id"]: item["is_active"] for item in listed} == {
        first["id"]: False,
        second["id"]: True,
    }

    await client.put(
        f"/api/v1/resumes/{first['id']}", json={"is_active": True}, headers=auth_headers
    )
    listed = (await client.get("/api/v1/resumes", headers=auth_headers)).json()
    assert {item["id"]: item["is_active"] for item in listed} == {
        first["id"]: True,
        second["id"]: False,
    }


async def test_new_text_resets_evaluations(
    client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    target = await ready_vacancy(db_session, user)
    resume = await active_resume(db_session, user)
    await add_evaluation(db_session, target.id, resume.id)

    await client.put(
        f"/api/v1/resumes/{resume.id}", json={"title": "Новое имя"}, headers=auth_headers
    )
    assert await db_session.scalar(select(func.count()).select_from(Evaluation)) == 1

    response = await client.put(
        f"/api/v1/resumes/{resume.id}", json={"text": TEXT + " Ещё FastAPI."}, headers=auth_headers
    )
    assert response.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(Evaluation)) == 0


async def test_foreign_resume_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
    settings: Settings,
    auth_headers: dict[str, str],
) -> None:
    stranger = await AuthService(db_session, settings).create_user("other@example.com", "password1")
    await ready_vacancy(db_session, stranger)
    foreign = await active_resume(db_session, stranger)

    response = await client.get(f"/api/v1/resumes/{foreign.id}", headers=auth_headers)

    assert response.status_code == 404


async def test_validation(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/resumes", json={"title": "", "text": "коротко"}, headers=auth_headers
    )

    assert response.status_code == 422

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User
from app.llm.prompts import PROMPT_VERSION
from tests.fakes import FakeTaskQueue, active_resume, add_evaluation, ready_vacancy


async def evaluated(
    db_session: AsyncSession, user: User, external_id: str, score: int, verdict: str
) -> int:
    target = await ready_vacancy(db_session, user, external_id)
    resume = await active_resume(db_session, user)
    await add_evaluation(db_session, target.id, resume.id, score=score, verdict=verdict)
    return target.id


async def test_list_shows_evaluation_and_filters(
    client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    good = await evaluated(db_session, user, "1", 85, "apply")
    await evaluated(db_session, user, "2", 30, "skip")
    await ready_vacancy(db_session, user, "3")  # ещё без оценки

    everything = (
        await client.get("/api/v1/vacancies", params={"sort": "score"}, headers=auth_headers)
    ).json()
    apply_only = (
        await client.get("/api/v1/vacancies", params={"verdict": "apply"}, headers=auth_headers)
    ).json()
    high = (
        await client.get("/api/v1/vacancies", params={"score_min": 50}, headers=auth_headers)
    ).json()

    assert [item["evaluation"] and item["evaluation"]["score"] for item in everything["items"]] == [
        85,
        30,
        None,
    ]
    assert [item["id"] for item in apply_only["items"]] == [good]
    assert high["total"] == 1


async def test_card_has_full_evaluation(
    client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    vacancy_id = await evaluated(db_session, user, "1", 85, "apply")

    card = (await client.get(f"/api/v1/vacancies/{vacancy_id}", headers=auth_headers)).json()

    assert card["evaluation"]["matches"] == [{"requirement": "Python", "evidence": "4 года"}]
    assert card["evaluation"]["prompt_version"] == PROMPT_VERSION


async def test_request_evaluation(
    client: AsyncClient,
    db_session: AsyncSession,
    user: User,
    auth_headers: dict[str, str],
    task_queue: FakeTaskQueue,
    llm_enabled: None,
) -> None:
    target = await ready_vacancy(db_session, user)
    resume = await active_resume(db_session, user)

    response = await client.post(f"/api/v1/vacancies/{target.id}/evaluate", headers=auth_headers)

    assert response.status_code == 202
    assert task_queue.evaluations == [(target.id, resume.id, True)]


async def test_request_evaluation_needs_key(
    client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    target = await ready_vacancy(db_session, user)

    response = await client.post(f"/api/v1/vacancies/{target.id}/evaluate", headers=auth_headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_disabled"


async def test_request_evaluation_needs_resume(
    client: AsyncClient, auth_headers: dict[str, str], llm_enabled: None
) -> None:
    response = await client.post("/api/v1/vacancies/1/evaluate", headers=auth_headers)

    assert response.status_code == 404
    assert "резюме" in response.json()["error"]["message"]


async def test_llm_usage(
    client: AsyncClient, auth_headers: dict[str, str], llm_enabled: None
) -> None:
    usage = (await client.get("/api/v1/llm/usage", headers=auth_headers)).json()

    assert usage["used"] == 0
    assert usage["limit"] == get_settings().llm.daily_request_limit
    assert usage["paused_until"] is None
    assert usage["enabled"] is True
    assert all(model.endswith(":free") for model in usage["models"])

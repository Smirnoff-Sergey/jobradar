from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Source
from app.services.queue import TaskStatus
from tests.fakes import FakeTaskQueue


async def test_list_sources(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.get("/api/v1/sources", headers=auth_headers)

    assert response.status_code == 200
    assert [source["code"] for source in response.json()] == ["getmatch"]


async def test_run_source_queues_task(
    client: AsyncClient, auth_headers: dict[str, str], task_queue: FakeTaskQueue
) -> None:
    response = await client.post("/api/v1/sources/getmatch/run", headers=auth_headers)

    assert response.status_code == 202
    assert response.json() == {"task_id": "collect-1"}
    assert task_queue.collected == ["getmatch"]


async def test_run_unknown_source(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post("/api/v1/sources/nope/run", headers=auth_headers)

    assert response.status_code == 404


async def test_run_disabled_source(
    client: AsyncClient, db_session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    source = await db_session.get(Source, "getmatch")
    assert source is not None
    source.is_enabled = False
    await db_session.commit()

    response = await client.post("/api/v1/sources/getmatch/run", headers=auth_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_task_status(
    client: AsyncClient, auth_headers: dict[str, str], task_queue: FakeTaskQueue
) -> None:
    task_queue.statuses["t1"] = TaskStatus("t1", "SUCCESS", result={"status": "success"})

    done = await client.get("/api/v1/tasks/t1", headers=auth_headers)
    unknown = await client.get("/api/v1/tasks/t2", headers=auth_headers)

    assert done.json() == {
        "task_id": "t1",
        "state": "SUCCESS",
        "result": {"status": "success"},
        "error": None,
    }
    assert unknown.json()["state"] == "PENDING"

from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, SessionDep, TaskQueueDep
from app.schemas.common import ErrorResponse
from app.schemas.source import SourceRead, TaskAccepted, TaskStatusRead
from app.services.sources import SourceService

router = APIRouter(tags=["sources"])


@router.get("/sources")
async def list_sources(
    _: CurrentUserDep, session: SessionDep, queue: TaskQueueDep
) -> list[SourceRead]:
    sources = await SourceService(session, queue).list_all()
    return [SourceRead.model_validate(source) for source in sources]


@router.post(
    "/sources/{code}/run",
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def run_source(
    code: str, _: CurrentUserDep, session: SessionDep, queue: TaskQueueDep
) -> TaskAccepted:
    return TaskAccepted(task_id=await SourceService(session, queue).run(code))


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, _: CurrentUserDep, queue: TaskQueueDep) -> TaskStatusRead:
    return TaskStatusRead.model_validate(await queue.status(task_id))

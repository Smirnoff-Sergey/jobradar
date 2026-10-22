from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, SessionDep
from app.schemas.common import ErrorResponse
from app.schemas.resume import ResumeCreate, ResumeRead, ResumeUpdate
from app.services.resumes import ResumeService

router = APIRouter(prefix="/resumes", tags=["resumes"], responses={404: {"model": ErrorResponse}})


@router.get("")
async def list_resumes(user: CurrentUserDep, session: SessionDep) -> list[ResumeRead]:
    return [
        ResumeRead.model_validate(r) for r in await ResumeService(session).list_for_user(user.id)
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_resume(
    body: ResumeCreate, user: CurrentUserDep, session: SessionDep
) -> ResumeRead:
    resume = await ResumeService(session).create(
        user.id, body.title, body.text, make_active=body.make_active
    )
    return ResumeRead.model_validate(resume)


@router.get("/{resume_id}")
async def get_resume(resume_id: int, user: CurrentUserDep, session: SessionDep) -> ResumeRead:
    return ResumeRead.model_validate(await ResumeService(session).get(user.id, resume_id))


@router.put("/{resume_id}")
async def update_resume(
    resume_id: int, body: ResumeUpdate, user: CurrentUserDep, session: SessionDep
) -> ResumeRead:
    resume = await ResumeService(session).update(
        user.id, resume_id, **body.model_dump(exclude_unset=True)
    )
    return ResumeRead.model_validate(resume)

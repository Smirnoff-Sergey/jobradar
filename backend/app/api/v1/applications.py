from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, SessionDep
from app.domain.applications import ApplicationStatus
from app.schemas.application import (
    ApplicationDetail,
    ApplicationListItem,
    ApplicationPage,
    ApplicationRead,
    ApplicationUpdate,
    StatusChangeRead,
    VacancyBrief,
)
from app.schemas.common import ErrorResponse
from app.services.applications import ApplicationService

router = APIRouter(
    prefix="/applications", tags=["applications"], responses={404: {"model": ErrorResponse}}
)


@router.get("")
async def list_applications(
    user: CurrentUserDep,
    session: SessionDep,
    status: ApplicationStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApplicationPage:
    rows, total = await ApplicationService(session).list_for_user(user.id, status, limit, offset)
    items = [
        ApplicationListItem(
            **ApplicationRead.model_validate(application).model_dump(),
            vacancy=VacancyBrief.model_validate(vacancy),
        )
        for application, vacancy in rows
    ]
    return ApplicationPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{application_id}")
async def get_application(
    application_id: int, user: CurrentUserDep, session: SessionDep
) -> ApplicationDetail:
    service = ApplicationService(session)
    application = await service.get(user.id, application_id)
    return await _detail(service, application.id, ApplicationRead.model_validate(application))


@router.patch("/{application_id}")
async def update_application(
    application_id: int, body: ApplicationUpdate, user: CurrentUserDep, session: SessionDep
) -> ApplicationDetail:
    service = ApplicationService(session)
    application = await service.update(
        user.id, application_id, **body.model_dump(exclude_unset=True)
    )
    return await _detail(service, application.id, ApplicationRead.model_validate(application))


async def _detail(
    service: ApplicationService, application_id: int, application: ApplicationRead
) -> ApplicationDetail:
    history = [StatusChangeRead.model_validate(h) for h in await service.history(application_id)]
    return ApplicationDetail(**application.model_dump(), history=history)

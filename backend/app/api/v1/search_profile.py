from fastapi import APIRouter

from app.api.deps import CurrentUserDep, SessionDep, TaskQueueDep
from app.domain.filtering import SearchCriteria
from app.schemas.search_profile import SearchProfileRead, SearchProfileUpdate, SearchProfileUpdated
from app.services.search_profiles import SearchProfileService

router = APIRouter(prefix="/search-profile", tags=["search-profile"])


@router.get("")
async def get_search_profile(
    user: CurrentUserDep, session: SessionDep, queue: TaskQueueDep
) -> SearchProfileRead:
    profile = await SearchProfileService(session, queue).get_or_create(user.id)
    return SearchProfileRead.model_validate(profile)


@router.put("")
async def update_search_profile(
    body: SearchProfileUpdate,
    user: CurrentUserDep,
    session: SessionDep,
    queue: TaskQueueDep,
) -> SearchProfileUpdated:
    profile, task_id = await SearchProfileService(session, queue).update(
        user.id, SearchCriteria(**body.model_dump())
    )
    return SearchProfileUpdated(
        profile=SearchProfileRead.model_validate(profile),
        refilter_task_id=task_id,
    )

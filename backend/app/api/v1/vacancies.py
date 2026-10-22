from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, SessionDep
from app.domain.vacancies import FilterStatus, VacancyListQuery
from app.schemas.common import ErrorResponse
from app.schemas.vacancy import VacancyListItem, VacancyPage, VacancyRead
from app.services.vacancies import VacancyService

router = APIRouter(prefix="/vacancies", tags=["vacancies"])


@router.get("")
async def list_vacancies(
    user: CurrentUserDep,
    session: SessionDep,
    status: Annotated[FilterStatus, Query(description="Решение фильтра")] = "passed",
    source: Annotated[str | None, Query(max_length=32)] = None,
    active_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VacancyPage:
    query = VacancyListQuery(
        user_id=user.id,
        status=status,
        source_code=source,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    rows, total = await VacancyService(session).search(query)
    return VacancyPage(
        items=[VacancyListItem.build(vacancy, decision) for vacancy, decision in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{vacancy_id}", responses={404: {"model": ErrorResponse}})
async def get_vacancy(vacancy_id: int, user: CurrentUserDep, session: SessionDep) -> VacancyRead:
    vacancy, decision = await VacancyService(session).get(vacancy_id, user.id)
    return VacancyRead.build(vacancy, decision)

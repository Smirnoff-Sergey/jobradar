from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserDep, EvaluationSchedulerDep, SessionDep
from app.domain.evaluation import Verdict
from app.domain.vacancies import FilterStatus, VacancyListQuery, VacancySort
from app.schemas.common import ErrorResponse
from app.schemas.source import TaskAccepted
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
    verdict: Annotated[Verdict | None, Query(description="Вердикт LLM-оценки")] = None,
    score_min: Annotated[int | None, Query(ge=0, le=100)] = None,
    sort: VacancySort = "published",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VacancyPage:
    query = VacancyListQuery(
        user_id=user.id,
        status=status,
        source_code=source,
        active_only=active_only,
        verdict=verdict,
        score_min=score_min,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    rows, total = await VacancyService(session).search(query)
    return VacancyPage(
        items=[VacancyListItem.build(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{vacancy_id}", responses={404: {"model": ErrorResponse}})
async def get_vacancy(vacancy_id: int, user: CurrentUserDep, session: SessionDep) -> VacancyRead:
    return VacancyRead.build(await VacancyService(session).get(vacancy_id, user.id))


@router.post(
    "/{vacancy_id}/evaluate",
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def request_reevaluation(
    vacancy_id: int, user: CurrentUserDep, scheduler: EvaluationSchedulerDep
) -> TaskAccepted:
    """Переоценить вакансию по активному резюме. Прежняя оценка заменится только новой."""
    return TaskAccepted(task_id=await scheduler.request_reevaluation(user.id, vacancy_id))

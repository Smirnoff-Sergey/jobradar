from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    CurrentUserDep,
    EvaluationSchedulerDep,
    LetterSchedulerDep,
    SessionDep,
    VacancyImportServiceDep,
)
from app.domain.applications import ApplicationStatus
from app.domain.evaluation import Verdict
from app.domain.vacancies import FilterStatus, VacancyListQuery, VacancySort
from app.schemas.application import ApplicationRead, ApplicationSet
from app.schemas.common import ErrorResponse
from app.schemas.letter import LetterAccepted, LetterRead
from app.schemas.source import TaskAccepted
from app.schemas.vacancy import VacancyImport, VacancyListItem, VacancyPage, VacancyRead
from app.services.applications import ApplicationService
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
    application_status: Annotated[
        ApplicationStatus | None, Query(description="Статус отклика")
    ] = None,
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
        application_status=application_status,
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


@router.post(
    "/import",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def import_vacancy(
    body: VacancyImport,
    user: CurrentUserDep,
    session: SessionDep,
    importer: VacancyImportServiceDep,
) -> VacancyRead:
    """Добавить вакансию по ссылке на её страницу (getmatch.ru/vacancies/…).

    Вакансия проходит фильтр по критериям пользователя; прошла — встаёт в очередь на оценку.
    Повтор с той же ссылкой не создаёт дубля.
    """
    vacancy_id = await importer.import_url(user.id, body.url)
    return VacancyRead.build(await VacancyService(session).get(vacancy_id, user.id))


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


@router.post(
    "/{vacancy_id}/letter",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def request_letter(
    vacancy_id: int, user: CurrentUserDep, scheduler: LetterSchedulerDep
) -> LetterAccepted:
    """Заказать черновик сопроводительного письма по активному резюме.

    Отклика нет — он создаётся со статусом «новый»; готовый черновик переводит его
    в «письмо готово». Пока пишется один черновик, второй не заказать (409).
    """
    letter, task_id = await scheduler.request_letter(user.id, vacancy_id)
    return LetterAccepted(task_id=task_id, letter_id=letter.id)


@router.get("/{vacancy_id}/letters")
async def list_letters(
    vacancy_id: int, user: CurrentUserDep, scheduler: LetterSchedulerDep
) -> list[LetterRead]:
    """Черновики писем к вакансии, новые первыми."""
    letters = await scheduler.list_for_vacancy(user.id, vacancy_id)
    return [LetterRead.model_validate(letter) for letter in letters]


@router.put("/{vacancy_id}/application", responses={404: {"model": ErrorResponse}})
async def set_application(
    vacancy_id: int, body: ApplicationSet, user: CurrentUserDep, session: SessionDep
) -> ApplicationRead:
    """Создать отклик на вакансию или сменить его статус — как кнопки бота."""
    application = await ApplicationService(session).set_status(
        user.id, vacancy_id, body.status, notes=body.notes
    )
    return ApplicationRead.model_validate(application)

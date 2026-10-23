from collections.abc import AsyncIterator
from functools import cache
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import NotAuthenticatedError, TelegramDisabledError
from app.core.http import create_client
from app.db.models import User
from app.services.auth import AuthService
from app.services.evaluation import EvaluationScheduler
from app.services.letters import LetterScheduler
from app.services.queue import TaskQueue
from app.services.vacancy_import import AdapterFactory, VacancyImportService
from app.sources.registry import create_adapter
from app.telegram.client import TelegramClient, open_telegram_client


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_auth_service(session: SessionDep, settings: SettingsDep) -> AuthService:
    return AuthService(session, settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


@cache
def get_task_queue() -> TaskQueue:
    # Импорт внутри функции: Celery поднимается только при первой постановке задачи,
    # а тесты подменяют эту зависимость фейковой очередью.
    from app.tasks.queue import CeleryTaskQueue

    return CeleryTaskQueue()


TaskQueueDep = Annotated[TaskQueue, Depends(get_task_queue)]


def get_evaluation_scheduler(
    session: SessionDep, queue: TaskQueueDep, settings: SettingsDep
) -> EvaluationScheduler:
    return EvaluationScheduler(session, queue, settings.llm)


EvaluationSchedulerDep = Annotated[EvaluationScheduler, Depends(get_evaluation_scheduler)]


def get_letter_scheduler(
    session: SessionDep, queue: TaskQueueDep, settings: SettingsDep
) -> LetterScheduler:
    return LetterScheduler(session, queue, settings.llm)


LetterSchedulerDep = Annotated[LetterScheduler, Depends(get_letter_scheduler)]


async def get_import_adapters(settings: SettingsDep) -> AsyncIterator[AdapterFactory]:
    """Адаптеры источников для импорта по ссылке: короткий таймаут и мало повторов —
    ответа ждёт пользователь."""
    collector = settings.collector
    async with create_client(collector.import_timeout_seconds) as client:
        yield lambda code: create_adapter(
            code, client, collector, max_attempts=collector.import_max_attempts
        )


def get_import_service(
    session: SessionDep,
    adapters: Annotated[AdapterFactory, Depends(get_import_adapters)],
    queue: TaskQueueDep,
    settings: SettingsDep,
) -> VacancyImportService:
    return VacancyImportService(session, adapters, queue, settings.llm)


VacancyImportServiceDep = Annotated[VacancyImportService, Depends(get_import_service)]

# auto_error=False: отсутствие токена обрабатываем сами, чтобы ответ был в едином формате ошибок.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth: AuthServiceDep,
) -> User:
    if credentials is None:
        raise NotAuthenticatedError
    return await auth.get_user_by_access_token(credentials.credentials)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_telegram_client(settings: SettingsDep) -> AsyncIterator[TelegramClient]:
    if not settings.telegram.enabled:
        raise TelegramDisabledError
    async with open_telegram_client(settings.telegram) as client:
        yield client


TelegramClientDep = Annotated[TelegramClient, Depends(get_telegram_client)]

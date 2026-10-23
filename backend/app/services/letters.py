import logging
from collections.abc import Sequence
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.config import LLMSettings
from app.core.errors import (
    ConflictError,
    ExternalAccessError,
    LLMDisabledError,
    NotFoundError,
    PaidUsageError,
    PermanentExternalError,
    TransientExternalError,
)
from app.db.models import Letter
from app.domain.evaluation import DONE, FAILED, PENDING
from app.domain.letters import (
    LetterResult,
    letter_json_schema,
    resolve_facts,
    resume_fragments,
)
from app.llm.base import LLMClient
from app.llm.evaluator import BudgetExhaustedError, request_validated
from app.llm.letter_prompts import (
    LETTER_PROMPT_VERSION,
    LETTER_SCHEMA_NAME,
    LETTER_SYSTEM_PROMPT,
    numbered_resume,
)
from app.llm.prompts import build_user_prompt, vacancy_for_prompt
from app.repositories.applications import ApplicationRepository
from app.repositories.claims import stale_before
from app.repositories.letters import LetterRepository
from app.repositories.resumes import ResumeRepository
from app.repositories.vacancies import VacancyRepository
from app.services.llm_budget import LLMBudget
from app.services.queue import TaskQueue

logger = logging.getLogger(__name__)

LetterRunResult = Literal["done", "failed", "skipped", "retry"]

BUDGET_EXHAUSTED = "Дневной лимит запросов к модели исчерпан. Повторите завтра (сутки по UTC)"
LETTERS_DISABLED = "Письма выключены: не задан ключ LLM"
STUCK = "Генерация зависла и прервана. Напишите письмо заново"


class LetterScheduler:
    """Заказ черновика письма. Клиент LLM не нужен — его использует API."""

    def __init__(self, session: AsyncSession, queue: TaskQueue, settings: LLMSettings) -> None:
        self._session = session
        self._queue = queue
        self._settings = settings
        self._applications = ApplicationRepository(session)
        self._letters = LetterRepository(session)
        self._resumes = ResumeRepository(session)
        self._vacancies = VacancyRepository(session)

    async def request_letter(self, user_id: int, vacancy_id: int) -> tuple[Letter, str]:
        """Создаёт черновик в статусе pending и ставит задачу. Возвращает черновик и id задачи.

        Отклика ещё нет — он создаётся со статусом «новый».
        """
        if not self._settings.enabled:
            raise LLMDisabledError(LETTERS_DISABLED)
        resume = await self._resumes.get_active(user_id)
        if resume is None:
            raise NotFoundError("Нет активного резюме")
        if await self._vacancies.get(vacancy_id) is None:
            raise NotFoundError("Вакансия не найдена")
        application, created = await self._applications.get_or_create(user_id, vacancy_id, "new")
        if created:
            await self._applications.add_history(application.id, None, "new")
        letter = await self._letters.create_pending(
            application.id,
            resume.id,
            LETTER_PROMPT_VERSION,
            stale_before=stale_before(),
            stuck_message=STUCK,
        )
        if letter is None:
            await self._session.rollback()
            raise ConflictError("Письмо к этой вакансии уже пишется")
        await self._session.commit()
        try:
            task_id = await self._queue.generate_letter(letter.id)
        except Exception:
            # Задача не встала (Redis недоступен) — черновик не должен навсегда остаться pending.
            await fail_letter(self._session, letter.id, "Не удалось поставить задачу в очередь")
            raise
        return letter, task_id

    async def list_for_vacancy(self, user_id: int, vacancy_id: int) -> Sequence[Letter]:
        """Черновики, новые первыми. Зависший pending (воркер упал, задача потерялась)
        показывается неудавшимся: кнопка снова доступна, а новый заказ его закроет."""
        letters = await self._letters.list_for_vacancy(user_id, vacancy_id)
        cutoff = stale_before()
        for letter in letters:
            if letter.status == PENDING and letter.updated_at < cutoff:
                # Только для ответа: строка в БД закроется при следующем заказе письма.
                self._session.expunge(letter)
                letter.status = FAILED
                letter.error = STUCK
        return letters


async def fail_letter(session: AsyncSession, letter_id: int, message: str) -> None:
    """Отметить незаконченный черновик неудавшимся — задача исчерпала повторы или LLM выключена."""
    letter = await LetterRepository(session).get(letter_id)
    if letter is not None and letter.status not in (DONE, FAILED):
        letter.status = FAILED
        letter.error = message
        await session.commit()


class LetterService:
    """Генерация черновика моделью: только по фактам резюме, цитаты сверяются с текстом."""

    def __init__(self, session: AsyncSession, settings: LLMSettings, llm: LLMClient) -> None:
        self._session = session
        self._settings = settings
        self._llm = llm
        self._applications = ApplicationRepository(session)
        self._letters = LetterRepository(session)
        self._resumes = ResumeRepository(session)
        self._vacancies = VacancyRepository(session)
        self._budget = LLMBudget(session, settings)

    async def generate(self, letter_id: int) -> LetterRunResult:
        """Идемпотентна: готовый черновик или захваченный другой задачей пропускает."""
        letter = await self._letters.claim(letter_id, stale_before=stale_before())
        if letter is None:
            await self._session.commit()
            return "skipped"
        application = await self._applications.get_by_id(letter.application_id)
        resume = await self._resumes.get(letter.resume_id) if letter.resume_id else None
        vacancy = await self._vacancies.get(application.vacancy_id) if application else None
        if application is None or resume is None or vacancy is None:
            return await self._fail(letter, "Резюме или вакансия удалены")
        fragments = resume_fragments(resume.text)
        if not fragments:
            return await self._fail(letter, "Резюме пустое")
        # Захват виден другим задачам, а запрос к модели идёт вне транзакции.
        await self._session.commit()

        try:
            outcome = await request_validated(
                self._llm,
                LetterResult,
                system=LETTER_SYSTEM_PROMPT,
                user=build_user_prompt(
                    numbered_resume(fragments),
                    vacancy_for_prompt(vacancy, vacancy.description),
                    max_chars=self._settings.max_description_chars,
                ),
                schema_name=LETTER_SCHEMA_NAME,
                schema=letter_json_schema(),
                context={"fragments": len(fragments)},
                reserve_request=self._budget.reserve,
            )
        except BudgetExhaustedError:
            return await self._fail(letter, BUDGET_EXHAUSTED)
        except TransientExternalError:
            letter.started_at = None  # повтор задачи снова захватит черновик
            await self._commit("retry")
            raise
        except ExternalAccessError as exc:
            # В отличие от оценки, письмо не повторяется: его ждёт пользователь, а пауза — час.
            await self._budget.pause_after_access_error(exc.message)
            return await self._fail(letter, exc.message)
        except PaidUsageError as exc:
            await self._budget.stop_after_paid_response(exc.message)
            await self._fail(letter, exc.message)
            raise
        except PermanentExternalError as exc:
            return await self._fail(letter, exc.message)

        result = outcome.result
        letter.status = DONE
        letter.text = result.text.strip()
        letter.facts = [fact.model_dump() for fact in resolve_facts(result, fragments)]
        letter.model = outcome.model
        letter.tokens_in = outcome.tokens_in
        letter.tokens_out = outcome.tokens_out
        letter.cost_usd = outcome.cost_usd
        letter.error = None
        await self._mark_letter_ready(letter.application_id)
        return await self._commit("done")

    async def _mark_letter_ready(self, application_id: int) -> None:
        # Только из «нового»: готовый черновик не откатывает «откликнулся» или «пригласили».
        application = await self._applications.get_by_id(application_id, for_update=True)
        if application is not None and application.status == "new":
            await self._applications.add_history(application.id, "new", "letter_ready")
            application.status = "letter_ready"

    async def _fail(self, letter: Letter, message: str) -> LetterRunResult:
        logger.warning("Письмо %d не написано: %s", letter.id, message)
        letter.status = FAILED
        letter.error = message
        return await self._commit("failed")

    async def _commit(self, result: LetterRunResult) -> LetterRunResult:
        try:
            await self._session.commit()
        except StaleDataError:
            # Отклик удалили вместе с черновиком, пока шёл запрос.
            await self._session.rollback()
            return "skipped"
        return result

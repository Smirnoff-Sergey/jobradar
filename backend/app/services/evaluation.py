import logging
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.config import LLMSettings
from app.core.errors import (
    ExternalAccessError,
    LLMDisabledError,
    NotFoundError,
    PaidUsageError,
    PermanentExternalError,
    TransientExternalError,
)
from app.db.models import Evaluation
from app.domain.evaluation import DONE, FAILED
from app.llm.base import LLMClient
from app.llm.evaluator import BudgetExhaustedError, EvaluationOutcome, request_evaluation
from app.llm.prompts import PROMPT_VERSION, vacancy_for_prompt
from app.repositories.claims import stale_before
from app.repositories.evaluations import Claim, EvaluationRepository
from app.repositories.resumes import ResumeRepository
from app.repositories.vacancies import VacancyRepository
from app.services.llm_budget import LLMBudget
from app.services.queue import TaskQueue

logger = logging.getLogger(__name__)

EvaluateResult = Literal["done", "failed", "skipped", "not_ready", "postponed"]


class EvaluationScheduler:
    """Постановка оценок в очередь. Клиент LLM не нужен — его использует API и фоновый досыл."""

    def __init__(self, session: AsyncSession, queue: TaskQueue, settings: LLMSettings) -> None:
        self._session = session
        self._queue = queue
        self._settings = settings
        self._evaluations = EvaluationRepository(session)
        self._resumes = ResumeRepository(session)
        self._vacancies = VacancyRepository(session)
        self.budget = LLMBudget(session, settings)

    async def queue_pending(self, vacancy_id: int | None = None) -> int:
        """Ставит оценку пар, которые её ждут, — не больше, чем осталось в дневном лимите."""
        available = await self.budget.available()
        if not available:
            return 0
        pairs = await self._evaluations.pending_pairs(
            PROMPT_VERSION, stale_before=stale_before(), limit=available, vacancy_id=vacancy_id
        )
        await self._session.commit()
        for pair_vacancy_id, resume_id in pairs:
            await self._queue.evaluate_vacancy(pair_vacancy_id, resume_id)
        return len(pairs)

    async def request_reevaluation(self, user_id: int, vacancy_id: int) -> str:
        """Переоценка по запросу пользователя. Возвращает id задачи."""
        if not self._settings.enabled:
            raise LLMDisabledError("Оценка выключена: не задан ключ LLM")
        resume = await self._resumes.get_active(user_id)
        if resume is None:
            raise NotFoundError("Нет активного резюме")
        if await self._vacancies.get(vacancy_id) is None:
            raise NotFoundError("Вакансия не найдена")
        return await self._queue.evaluate_vacancy(vacancy_id, resume.id, force=True)


class EvaluationService:
    """Оценка пары (вакансия, резюме) моделью. Каждый запрос проходит через дневной лимит."""

    def __init__(self, session: AsyncSession, settings: LLMSettings, llm: LLMClient) -> None:
        self._session = session
        self._settings = settings
        self._llm = llm
        self._vacancies = VacancyRepository(session)
        self._resumes = ResumeRepository(session)
        self._evaluations = EvaluationRepository(session)
        self._budget = LLMBudget(session, settings)

    async def evaluate(
        self, vacancy_id: int, resume_id: int, *, force: bool = False
    ) -> EvaluateResult:
        """Идемпотентна: готовую или захваченную другой задачей пару пропускает.

        force — переоценить готовую пару; прежняя оценка заменяется только успешной новой.
        """
        vacancy = await self._vacancies.get(vacancy_id)
        resume = await self._resumes.get(resume_id)
        if vacancy is None or resume is None or not vacancy.is_active or not resume.is_active:
            return "skipped"
        if vacancy.description_fetched_at is None:
            return "not_ready"

        claim = await self._evaluations.claim(
            vacancy_id, resume_id, PROMPT_VERSION, stale_before=stale_before(), force=force
        )
        # Захват виден другим задачам, а запрос к модели идёт вне транзакции.
        await self._session.commit()
        if claim is None:
            return "skipped"

        try:
            outcome = await request_evaluation(
                self._llm,
                resume.text,
                vacancy_for_prompt(vacancy, vacancy.description),
                max_chars=self._settings.max_description_chars,
                reserve_request=self._budget.reserve,
            )
        except BudgetExhaustedError:
            return await self._release(claim, "postponed")
        except TransientExternalError:
            await self._release(claim, "postponed")
            raise  # Celery повторит задачу
        except ExternalAccessError as exc:
            await self._budget.pause_after_access_error(exc.message)
            await self._release(claim, "postponed")
            raise
        except PaidUsageError as exc:
            await self._budget.stop_after_paid_response(exc.message)
            await self._fail(claim, exc.message)
            raise
        except PermanentExternalError as exc:
            return await self._fail(claim, exc.message)

        _apply_outcome(claim.evaluation, outcome)
        return await self._commit("done")

    async def _fail(self, claim: Claim, message: str) -> EvaluateResult:
        logger.warning("Оценка %d не удалась: %s", claim.evaluation.id, message)
        claim.evaluation.status = FAILED
        claim.evaluation.error = message
        return await self._commit("failed")

    async def _release(self, claim: Claim, result: EvaluateResult) -> EvaluateResult:
        await self._evaluations.release(claim)
        return await self._commit(result)

    async def _commit(self, result: EvaluateResult) -> EvaluateResult:
        try:
            await self._session.commit()
        except StaleDataError:
            # Строку удалили, пока шла оценка (сменился текст резюме или вакансии):
            # результат устарел, пару оценит следующий досыл.
            await self._session.rollback()
            return "skipped"
        return result


def _apply_outcome(evaluation: Evaluation, outcome: EvaluationOutcome) -> None:
    result = outcome.result
    evaluation.status = DONE
    evaluation.model = outcome.model
    evaluation.score = result.score
    evaluation.verdict = result.verdict
    evaluation.matches = [match.model_dump() for match in result.matches]
    evaluation.gaps = [gap.model_dump() for gap in result.gaps]
    evaluation.dealbreakers = list(result.dealbreakers)
    evaluation.tokens_in = outcome.tokens_in
    evaluation.tokens_out = outcome.tokens_out
    evaluation.cost_usd = outcome.cost_usd
    evaluation.error = None

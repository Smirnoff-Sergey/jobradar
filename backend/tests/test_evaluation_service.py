from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LLMSettings
from app.core.errors import (
    ExternalAccessError,
    LLMDisabledError,
    PaidUsageError,
    PermanentExternalError,
    TransientExternalError,
)
from app.db.models import Evaluation, Resume, User, Vacancy
from app.llm.prompts import PROMPT_VERSION
from app.services.evaluation import EvaluationScheduler, EvaluationService
from app.services.llm_budget import LLMBudget
from tests.fakes import (
    FakeAdapter,
    FakeLLM,
    FakeTaskQueue,
    active_resume,
    add_evaluation,
    collector,
    llm_answer,
    ready_vacancy,
    vacancy,
)

SETTINGS = LLMSettings(api_key="test-key", daily_request_limit=10)


def settings(limit: int = 10) -> LLMSettings:
    return SETTINGS.model_copy(update={"daily_request_limit": limit})


def evaluator(session: AsyncSession, llm: FakeLLM, *, limit: int = 10) -> EvaluationService:
    return EvaluationService(session, settings(limit), llm)


def scheduler(
    session: AsyncSession, queue: FakeTaskQueue | None = None, *, limit: int = 10
) -> EvaluationScheduler:
    return EvaluationScheduler(session, queue or FakeTaskQueue(), settings(limit))


async def ready_pair(
    session: AsyncSession, user: User, external_id: str = "1"
) -> tuple[Vacancy, Resume]:
    target = await ready_vacancy(session, user, external_id)
    return target, await active_resume(session, user)


async def evaluations(session: AsyncSession) -> list[Evaluation]:
    found = list(await session.scalars(select(Evaluation)))
    for evaluation in found:
        await session.refresh(evaluation)
    return found


async def test_evaluate_saves_result(db_session: AsyncSession, user: User) -> None:
    target, resume = await ready_pair(db_session, user)
    llm = FakeLLM(answers=[llm_answer(score=82)])

    assert await evaluator(db_session, llm).evaluate(target.id, resume.id) == "done"

    [evaluation] = await evaluations(db_session)
    assert (evaluation.status, evaluation.score, evaluation.verdict) == ("done", 82, "apply")
    assert evaluation.prompt_version == PROMPT_VERSION
    assert evaluation.model == "fake/model:free"
    assert evaluation.gaps == [{"requirement": "Kafka", "severity": "minor"}]
    assert "Нужен Python и PostgreSQL" in llm.prompts[0]  # описание без HTML
    assert (await scheduler(db_session).budget.usage()).used == 1


async def test_tokens_of_rejected_attempt_are_counted(db_session: AsyncSession, user: User) -> None:
    target, resume = await ready_pair(db_session, user)
    llm = FakeLLM(answers=[{"score": "много"}, llm_answer()])

    await evaluator(db_session, llm).evaluate(target.id, resume.id)

    [evaluation] = await evaluations(db_session)
    assert (evaluation.tokens_in, evaluation.tokens_out) == (200, 100)


async def test_evaluate_is_idempotent(db_session: AsyncSession, user: User) -> None:
    target, resume = await ready_pair(db_session, user)
    llm = FakeLLM(answers=[llm_answer()])
    await evaluator(db_session, llm).evaluate(target.id, resume.id)

    assert await evaluator(db_session, llm).evaluate(target.id, resume.id) == "skipped"
    assert len(llm.prompts) == 1


async def test_force_replaces_evaluation(db_session: AsyncSession, user: User) -> None:
    target, resume = await ready_pair(db_session, user)
    await add_evaluation(db_session, target.id, resume.id, score=90)
    llm = FakeLLM(answers=[llm_answer(score=50, verdict="maybe")])

    assert await evaluator(db_session, llm).evaluate(target.id, resume.id, force=True) == "done"

    [evaluation] = await evaluations(db_session)
    assert (evaluation.score, evaluation.verdict) == (50, "maybe")


async def test_failed_reevaluation_keeps_previous(db_session: AsyncSession, user: User) -> None:
    """Переоценка не удалась (лимит, сбой) — прежняя оценка остаётся как была."""
    target, resume = await ready_pair(db_session, user)
    await add_evaluation(db_session, target.id, resume.id, score=90)

    result = await evaluator(db_session, FakeLLM(), limit=0).evaluate(
        target.id, resume.id, force=True
    )

    assert result == "postponed"
    [evaluation] = await evaluations(db_session)
    assert (evaluation.status, evaluation.score) == ("done", 90)


async def test_budget_exhausted_postpones(db_session: AsyncSession, user: User) -> None:
    target, resume = await ready_pair(db_session, user)
    # Первый ответ не по схеме съедает единственный запрос лимита, на повтор места нет.
    llm = FakeLLM(answers=[{"score": "много"}, llm_answer()])

    assert await evaluator(db_session, llm, limit=1).evaluate(target.id, resume.id) == "postponed"

    assert await evaluations(db_session) == []  # захват снят — пару оценят завтра
    assert await evaluator(db_session, llm, limit=1).evaluate(target.id, resume.id) == "postponed"
    assert len(llm.prompts) == 1


async def test_transient_error_releases_claim(db_session: AsyncSession, user: User) -> None:
    target, resume = await ready_pair(db_session, user)
    llm = FakeLLM(answers=[TransientExternalError("429"), llm_answer()])

    with pytest.raises(TransientExternalError):
        await evaluator(db_session, llm).evaluate(target.id, resume.id)
    assert await evaluations(db_session) == []

    assert await evaluator(db_session, llm).evaluate(target.id, resume.id) == "done"


async def test_permanent_error_marks_failed(db_session: AsyncSession, user: User) -> None:
    target, resume = await ready_pair(db_session, user)
    llm = FakeLLM(answers=[PermanentExternalError("HTTP 400")])

    assert await evaluator(db_session, llm).evaluate(target.id, resume.id) == "failed"

    [evaluation] = await evaluations(db_session)
    assert (evaluation.status, evaluation.error) == ("failed", "HTTP 400")


async def test_paid_response_stops_everything(db_session: AsyncSession, user: User) -> None:
    first, resume = await ready_pair(db_session, user, "1")
    second = await ready_vacancy(db_session, user, "2")
    llm = FakeLLM(answers=[PaidUsageError("Платный запрос"), llm_answer()])

    with pytest.raises(PaidUsageError):
        await evaluator(db_session, llm).evaluate(first.id, resume.id)

    # Дальше не уходит ни одного запроса, пока остановку не снимут вручную.
    assert await evaluator(db_session, llm).evaluate(second.id, resume.id) == "postponed"
    assert len(llm.prompts) == 1
    assert await scheduler(db_session).queue_pending() == 0
    usage = await scheduler(db_session).budget.usage()
    assert usage.pause_reason == "Платный запрос"
    assert usage.paused_until is not None
    assert usage.paused_until.year == 9999

    await LLMBudget(db_session, settings()).unpause()
    assert await evaluator(db_session, llm).evaluate(second.id, resume.id) == "done"


async def test_access_denied_pauses_and_keeps_vacancy(db_session: AsyncSession, user: User) -> None:
    """403 (ключ отозван, регион заблокирован) — не провал вакансии, а пауза на час."""
    target, resume = await ready_pair(db_session, user)
    llm = FakeLLM(answers=[ExternalAccessError("HTTP 403")])

    with pytest.raises(ExternalAccessError):
        await evaluator(db_session, llm).evaluate(target.id, resume.id)

    assert await evaluations(db_session) == []
    usage = await scheduler(db_session).budget.usage()
    assert usage.paused_until is not None
    assert usage.paused_until - datetime.now(UTC) < timedelta(hours=1, minutes=1)
    assert await scheduler(db_session).queue_pending() == 0  # на паузе лимит не тратится


async def test_row_deleted_during_request_is_skipped(db_session: AsyncSession, user: User) -> None:
    """Текст резюме сменили, пока шёл запрос: устаревший результат не записывается."""
    target, resume = await ready_pair(db_session, user)

    async def resume_changed() -> None:
        # Как будто удалил другой процесс: identity map сессии об этом не знает.
        await db_session.execute(delete(Evaluation).execution_options(synchronize_session=False))
        await db_session.commit()

    llm = FakeLLM(answers=[llm_answer()], on_call=resume_changed)

    assert await evaluator(db_session, llm).evaluate(target.id, resume.id) == "skipped"
    assert await evaluations(db_session) == []


async def test_not_ready_and_missing(db_session: AsyncSession, user: User) -> None:
    target, resume = await ready_pair(db_session, user)
    target.description_fetched_at = None
    await db_session.commit()

    assert await evaluator(db_session, FakeLLM()).evaluate(target.id, resume.id) == "not_ready"
    assert await evaluator(db_session, FakeLLM()).evaluate(999_999, resume.id) == "skipped"


async def test_stale_claim_is_taken_over(db_session: AsyncSession, user: User) -> None:
    target, resume = await ready_pair(db_session, user)
    await add_evaluation(db_session, target.id, resume.id, status="pending", score=None)
    llm = FakeLLM(answers=[llm_answer()])

    assert await evaluator(db_session, llm).evaluate(target.id, resume.id) == "skipped"

    await db_session.execute(
        update(Evaluation).values(updated_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db_session.commit()
    assert await evaluator(db_session, llm).evaluate(target.id, resume.id) == "done"


async def test_changed_vacancy_loses_evaluation(db_session: AsyncSession, user: User) -> None:
    target, resume = await ready_pair(db_session, user)
    await add_evaluation(db_session, target.id, resume.id)

    await collector(db_session, FakeAdapter(pages=[[vacancy("1", title="Python Lead")]])).collect()

    assert await evaluations(db_session) == []


async def test_queue_pending_respects_budget(db_session: AsyncSession, user: User) -> None:
    first, resume = await ready_pair(db_session, user, "1")
    second = await ready_vacancy(db_session, user, "2")
    queue = FakeTaskQueue()

    assert await scheduler(db_session, queue, limit=1).queue_pending() == 1
    assert await scheduler(db_session, queue).queue_pending(second.id) == 1
    assert queue.evaluations[-1] == (second.id, resume.id, False)

    await add_evaluation(db_session, first.id, resume.id)
    queue.evaluations.clear()
    await scheduler(db_session, queue).queue_pending()
    assert queue.evaluations == [(second.id, resume.id, False)]


async def test_scheduler_disabled_without_key(db_session: AsyncSession, user: User) -> None:
    target, _ = await ready_pair(db_session, user)
    queue = FakeTaskQueue()
    disabled = EvaluationScheduler(db_session, queue, LLMSettings())

    assert await disabled.queue_pending() == 0
    with pytest.raises(LLMDisabledError):
        await disabled.request_reevaluation(user.id, target.id)
    assert queue.evaluations == []


async def test_no_evaluations_without_active_resume(db_session: AsyncSession, user: User) -> None:
    _, resume = await ready_pair(db_session, user)
    resume.is_active = False
    await db_session.commit()

    assert await scheduler(db_session).queue_pending() == 0


async def test_daily_counter_is_atomic(db_session: AsyncSession) -> None:
    budget = LLMBudget(db_session, settings(limit=2))

    assert [await budget.reserve() for _ in range(3)] == [True, True, False]
    usage = await budget.usage()
    assert (usage.used, usage.limit, usage.enabled) == (2, 2, True)
    assert await budget.available() == 0

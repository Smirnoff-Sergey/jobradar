from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LLMSettings
from app.core.errors import (
    ConflictError,
    ExternalAccessError,
    LLMDisabledError,
    NotFoundError,
    PaidUsageError,
    TransientExternalError,
)
from app.db.models import Application, Letter, StatusHistory, User, Vacancy
from app.domain.letters import LetterResult, resume_fragments
from app.llm.letter_prompts import LETTER_PROMPT_VERSION
from app.services.letters import (
    BUDGET_EXHAUSTED,
    STUCK,
    LetterScheduler,
    LetterService,
    fail_letter,
)
from app.services.llm_budget import LLMBudget
from tests.fakes import FakeLLM, FakeTaskQueue, ready_vacancy

SETTINGS = LLMSettings(api_key="test-key", daily_request_limit=10)
RESUME = "Python-разработчик, 4 года"


def letter_answer(**overrides: object) -> dict[str, object]:
    """Ответ модели по схеме LetterResult; цитата есть в резюме из ready_vacancy."""
    answer: dict[str, object] = {
        "text": "Здравствуйте! Я Python-разработчик с опытом 4 года.",
        "facts": [{"claim": "Опыт Python 4 года", "resume_fragment": 1}],
    }
    answer.update(overrides)
    return answer


def scheduler(session: AsyncSession, queue: FakeTaskQueue | None = None) -> LetterScheduler:
    return LetterScheduler(session, queue or FakeTaskQueue(), SETTINGS)


def writer(session: AsyncSession, llm: FakeLLM, *, limit: int = 10) -> LetterService:
    return LetterService(session, SETTINGS.model_copy(update={"daily_request_limit": limit}), llm)


async def ordered(session: AsyncSession, user: User) -> tuple[Vacancy, Letter]:
    """Вакансия и заказанный к ней черновик в статусе pending."""
    target = await ready_vacancy(session, user)
    letter, _ = await scheduler(session).request_letter(user.id, target.id)
    return target, letter


async def fresh(session: AsyncSession, letter: Letter) -> Letter:
    await session.refresh(letter)
    return letter


async def application_status(session: AsyncSession, vacancy_id: int) -> str | None:
    application = await session.scalar(
        select(Application).where(Application.vacancy_id == vacancy_id)
    )
    if application is None:
        return None
    await session.refresh(application)
    return application.status


# --- проверка фактов ---


def test_resume_fragments() -> None:
    long_line = "Первое предложение. " * 20
    text = f"# Резюме\n\n- Python, 4 года\n  * FastAPI  \n{long_line}"

    fragments = resume_fragments(text)

    assert fragments[:3] == ["# Резюме", "Python, 4 года", "FastAPI"]
    # Длинный абзац разрезан на предложения — цитата под письмом остаётся короткой.
    assert fragments[3:] == ["Первое предложение."] * 20


def test_letter_rejects_unknown_fragment() -> None:
    answer = letter_answer(facts=[{"claim": "Kafka", "resume_fragment": 7}])
    with pytest.raises(ValueError, match=r"facts\[0\]"):
        LetterResult.model_validate(answer, context={"fragments": 1})


def test_letter_needs_text_and_facts() -> None:
    with pytest.raises(ValueError, match="пустой"):
        LetterResult.model_validate(letter_answer(text="  "), context={"fragments": 1})
    with pytest.raises(ValueError, match="нет фактов"):
        LetterResult.model_validate(letter_answer(facts=[]), context={"fragments": 1})


# --- заказ черновика ---


async def test_request_creates_application_and_pending_letter(
    db_session: AsyncSession, user: User
) -> None:
    queue = FakeTaskQueue()
    target = await ready_vacancy(db_session, user)

    letter, task_id = await scheduler(db_session, queue).request_letter(user.id, target.id)

    assert task_id == "letter-1"
    assert queue.letters == [letter.id]
    assert letter.status == "pending"
    assert letter.prompt_version == LETTER_PROMPT_VERSION
    assert await application_status(db_session, target.id) == "new"


async def test_second_request_while_writing_conflicts(db_session: AsyncSession, user: User) -> None:
    target, _ = await ordered(db_session, user)

    with pytest.raises(ConflictError):
        await scheduler(db_session).request_letter(user.id, target.id)


async def test_stuck_letter_does_not_block_new_one(db_session: AsyncSession, user: User) -> None:
    target, stuck = await ordered(db_session, user)
    await db_session.execute(
        update(Letter)
        .where(Letter.id == stuck.id)
        .values(updated_at=datetime.now(UTC) - timedelta(hours=1))
    )

    letter, _ = await scheduler(db_session).request_letter(user.id, target.id)

    assert letter.id != stuck.id
    assert (await fresh(db_session, stuck)).status == "failed"


async def test_request_needs_key(db_session: AsyncSession, user: User) -> None:
    off = LetterScheduler(db_session, FakeTaskQueue(), LLMSettings())
    with pytest.raises(LLMDisabledError):
        await off.request_letter(user.id, 1)


async def test_request_needs_resume_and_vacancy(db_session: AsyncSession, user: User) -> None:
    with pytest.raises(NotFoundError, match="резюме"):
        await scheduler(db_session).request_letter(user.id, 1)
    await ready_vacancy(db_session, user)
    with pytest.raises(NotFoundError, match="Вакансия"):
        await scheduler(db_session).request_letter(user.id, 999_999)


class BrokenQueue(FakeTaskQueue):
    async def generate_letter(self, letter_id: int) -> str:
        raise ConnectionError("Redis недоступен")


async def test_queue_failure_does_not_leave_pending(db_session: AsyncSession, user: User) -> None:
    target = await ready_vacancy(db_session, user)

    with pytest.raises(ConnectionError):
        await scheduler(db_session, BrokenQueue()).request_letter(user.id, target.id)

    [letter] = list(await db_session.scalars(select(Letter)))
    assert (await fresh(db_session, letter)).status == "failed"


async def test_stuck_letter_is_listed_as_failed(db_session: AsyncSession, user: User) -> None:
    target, stuck = await ordered(db_session, user)
    user_id, vacancy_id, letter_id = user.id, target.id, stuck.id
    await db_session.execute(
        update(Letter)
        .where(Letter.id == letter_id)
        .values(updated_at=datetime.now(UTC) - timedelta(hours=1))
    )
    db_session.expire_all()  # как в новом запросе API: строка читается из БД

    [listed] = await scheduler(db_session).list_for_vacancy(user_id, vacancy_id)

    assert (listed.status, listed.error) == ("failed", STUCK)
    # В БД строка не тронута: её закроет следующий заказ письма.
    status = await db_session.scalar(select(Letter.status).where(Letter.id == letter_id))
    assert status == "pending"


# --- генерация ---


async def test_generate_saves_letter_and_marks_application(
    db_session: AsyncSession, user: User
) -> None:
    target, letter = await ordered(db_session, user)
    llm = FakeLLM([letter_answer()])

    assert await writer(db_session, llm).generate(letter.id) == "done"

    saved = await fresh(db_session, letter)
    assert saved.status == "done"
    assert saved.text is not None and saved.text.startswith("Здравствуйте")
    assert saved.facts == [
        {"claim": "Опыт Python 4 года", "resume_quote": "Python-разработчик, 4 года"}
    ]
    assert (saved.model, saved.tokens_in, saved.tokens_out) == ("fake/model:free", 100, 50)
    assert "<resume>\n[1] Python-разработчик, 4 года\n</resume>" in llm.prompts[0]
    assert await application_status(db_session, target.id) == "letter_ready"
    history = list(await db_session.scalars(select(StatusHistory.to_status)))
    assert history == ["new", "letter_ready"]


async def test_ready_letter_keeps_later_status(db_session: AsyncSession, user: User) -> None:
    target, letter = await ordered(db_session, user)
    await db_session.execute(
        update(Application).where(Application.vacancy_id == target.id).values(status="applied")
    )

    await writer(db_session, FakeLLM([letter_answer()])).generate(letter.id)

    assert await application_status(db_session, target.id) == "applied"


async def test_unknown_fragment_is_retried_then_fails(db_session: AsyncSession, user: User) -> None:
    _, letter = await ordered(db_session, user)
    invented = letter_answer(facts=[{"claim": "5 лет Kafka", "resume_fragment": 9}])
    llm = FakeLLM([invented, invented])

    assert await writer(db_session, llm).generate(letter.id) == "failed"

    saved = await fresh(db_session, letter)
    assert len(llm.prompts) == 2
    assert saved.error is not None and "нет такого фрагмента" in saved.error
    assert "Kafka" not in saved.error  # ответ модели в ошибку не попадает


async def test_generate_is_idempotent(db_session: AsyncSession, user: User) -> None:
    _, letter = await ordered(db_session, user)
    llm = FakeLLM([letter_answer()])
    await writer(db_session, llm).generate(letter.id)

    assert await writer(db_session, llm).generate(letter.id) == "skipped"
    assert len(llm.prompts) == 1


async def test_running_letter_is_not_taken_twice(db_session: AsyncSession, user: User) -> None:
    _, letter = await ordered(db_session, user)
    await db_session.execute(
        update(Letter).where(Letter.id == letter.id).values(started_at=datetime.now(UTC))
    )

    assert await writer(db_session, FakeLLM()).generate(letter.id) == "skipped"


async def test_budget_exhausted_fails_with_reason(db_session: AsyncSession, user: User) -> None:
    _, letter = await ordered(db_session, user)

    assert await writer(db_session, FakeLLM(), limit=0).generate(letter.id) == "failed"
    assert (await fresh(db_session, letter)).error == BUDGET_EXHAUSTED


async def test_transient_error_releases_claim(db_session: AsyncSession, user: User) -> None:
    _, letter = await ordered(db_session, user)
    llm = FakeLLM([TransientExternalError("503"), letter_answer()])

    with pytest.raises(TransientExternalError):
        await writer(db_session, llm).generate(letter.id)
    assert (await fresh(db_session, letter)).started_at is None

    assert await writer(db_session, llm).generate(letter.id) == "done"


async def test_access_error_pauses_llm(db_session: AsyncSession, user: User) -> None:
    _, letter = await ordered(db_session, user)

    result = await writer(db_session, FakeLLM([ExternalAccessError("403")])).generate(letter.id)

    assert result == "failed"
    usage = await LLMBudget(db_session, SETTINGS).usage()
    assert usage.paused_until is not None


async def test_paid_response_stops_llm(db_session: AsyncSession, user: User) -> None:
    _, letter = await ordered(db_session, user)

    with pytest.raises(PaidUsageError):
        await writer(db_session, FakeLLM([PaidUsageError("платно")])).generate(letter.id)

    assert (await fresh(db_session, letter)).status == "failed"
    usage = await LLMBudget(db_session, SETTINGS).usage()
    assert usage.paused_until is not None and usage.paused_until.year == 9999


async def test_deleted_resume_fails_letter(db_session: AsyncSession, user: User) -> None:
    _, letter = await ordered(db_session, user)
    await db_session.execute(update(Letter).where(Letter.id == letter.id).values(resume_id=None))

    assert await writer(db_session, FakeLLM()).generate(letter.id) == "failed"
    assert (await fresh(db_session, letter)).error == "Резюме или вакансия удалены"


async def test_fail_letter_skips_finished(db_session: AsyncSession, user: User) -> None:
    _, letter = await ordered(db_session, user)
    await writer(db_session, FakeLLM([letter_answer()])).generate(letter.id)

    await fail_letter(db_session, letter.id, "поздно")

    assert (await fresh(db_session, letter)).status == "done"


# --- API ---


async def test_letter_api(
    client: AsyncClient,
    db_session: AsyncSession,
    user: User,
    auth_headers: dict[str, str],
    task_queue: FakeTaskQueue,
    llm_enabled: None,
) -> None:
    target = await ready_vacancy(db_session, user)

    response = await client.post(f"/api/v1/vacancies/{target.id}/letter", headers=auth_headers)

    assert response.status_code == 202
    body = response.json()
    assert task_queue.letters == [body["letter_id"]]
    again = await client.post(f"/api/v1/vacancies/{target.id}/letter", headers=auth_headers)
    assert again.status_code == 409

    await writer(db_session, FakeLLM([letter_answer()])).generate(body["letter_id"])
    listed = await client.get(f"/api/v1/vacancies/{target.id}/letters", headers=auth_headers)
    assert listed.status_code == 200
    [letter] = listed.json()
    assert letter["status"] == "done"
    assert letter["facts"][0]["resume_quote"] == "Python-разработчик, 4 года"


async def test_letter_api_needs_key(
    client: AsyncClient, db_session: AsyncSession, user: User, auth_headers: dict[str, str]
) -> None:
    target = await ready_vacancy(db_session, user)

    response = await client.post(f"/api/v1/vacancies/{target.id}/letter", headers=auth_headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_disabled"


async def test_letters_of_other_vacancy_are_empty(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/vacancies/999/letters", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []

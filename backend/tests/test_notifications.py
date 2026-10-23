from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TelegramSettings
from app.core.errors import (
    ChatUnavailableError,
    ExternalAccessError,
    PermanentExternalError,
    TransientExternalError,
)
from app.db.models import Evaluation, Notification, User, Vacancy, VacancyFilterResult
from app.domain.notifications import notification_key
from app.services.notifications import NotificationScheduler, NotificationService
from tests.fakes import (
    CHAT_ID,
    FakeTaskQueue,
    FakeTelegram,
    active_resume,
    add_evaluation,
    link_chat,
    ready_vacancy,
)

SETTINGS = TelegramSettings(bot_token="42:test-token")


def scheduler(
    session: AsyncSession, queue: FakeTaskQueue, settings: TelegramSettings = SETTINGS
) -> NotificationScheduler:
    return NotificationScheduler(session, queue, settings)


async def evaluated(
    session: AsyncSession, user: User, external_id: str = "1", verdict: str = "apply"
) -> Vacancy:
    target = await ready_vacancy(session, user, external_id)
    resume = await active_resume(session, user)
    score = {"apply": 85, "maybe": 55, "skip": 10}[verdict]
    await add_evaluation(session, target.id, resume.id, verdict=verdict, score=score)
    return target


async def notifications(session: AsyncSession) -> list[Notification]:
    found = list(await session.scalars(select(Notification)))
    for notification in found:
        await session.refresh(notification)
    return found


async def test_apply_vacancy_is_sent_once(db_session: AsyncSession, user: User) -> None:
    await link_chat(db_session, user)
    target = await evaluated(db_session, user)
    queue = FakeTaskQueue()
    telegram = FakeTelegram()

    assert await scheduler(db_session, queue).queue_pending() == 1
    assert queue.notifications == [(user.id, target.id)]
    assert await NotificationService(db_session, telegram).notify(user.id, target.id) == "sent"

    [(chat_id, message)] = telegram.sent
    assert chat_id == CHAT_ID
    assert target.title in message.text
    [notification] = await notifications(db_session)
    assert notification.status == "sent"
    assert notification.message_id == 1
    assert notification.idempotency_key == notification_key("telegram", user.id, target.id)

    # Повторная задача и досыл ничего не шлют.
    assert await NotificationService(db_session, telegram).notify(user.id, target.id) == "skipped"
    assert await scheduler(db_session, queue).queue_pending() == 0
    assert len(telegram.sent) == 1


async def test_reevaluation_does_not_resend(db_session: AsyncSession, user: User) -> None:
    await link_chat(db_session, user)
    target = await evaluated(db_session, user)
    await NotificationService(db_session, FakeTelegram()).notify(user.id, target.id)

    await db_session.execute(update(Evaluation).values(score=90, updated_at=datetime.now(UTC)))
    await db_session.commit()

    assert await scheduler(db_session, FakeTaskQueue()).queue_pending() == 0


async def test_only_apply_after_link_is_pending(db_session: AsyncSession, user: User) -> None:
    await link_chat(db_session, user)
    await evaluated(db_session, user, "1", verdict="maybe")
    old = await evaluated(db_session, user, "2")
    # Оценку сделали до привязки чата — задним числом не рассылаем.
    await db_session.execute(
        update(Evaluation)
        .where(Evaluation.vacancy_id == old.id)
        .values(updated_at=datetime.now(UTC) - timedelta(days=2))
    )
    await db_session.commit()

    assert await scheduler(db_session, FakeTaskQueue()).queue_pending() == 0


async def test_nothing_without_chat_or_token(db_session: AsyncSession, user: User) -> None:
    target = await evaluated(db_session, user)
    queue = FakeTaskQueue()

    assert await scheduler(db_session, queue).queue_pending() == 0
    assert await NotificationService(db_session, FakeTelegram()).notify(user.id, target.id) == (
        "skipped"
    )

    await link_chat(db_session, user)
    assert await scheduler(db_session, queue, TelegramSettings()).queue_pending() == 0
    assert queue.notifications == []


async def test_queue_pending_for_one_vacancy(db_session: AsyncSession, user: User) -> None:
    await link_chat(db_session, user)
    await evaluated(db_session, user, "1")
    second = await evaluated(db_session, user, "2")
    queue = FakeTaskQueue()

    assert await scheduler(db_session, queue).queue_pending(second.id) == 1
    assert queue.notifications == [(user.id, second.id)]


async def test_transient_error_releases_claim(db_session: AsyncSession, user: User) -> None:
    await link_chat(db_session, user)
    target = await evaluated(db_session, user)
    telegram = FakeTelegram(errors=[TransientExternalError("429")])

    with pytest.raises(TransientExternalError):
        await NotificationService(db_session, telegram).notify(user.id, target.id)
    assert await notifications(db_session) == []

    assert await NotificationService(db_session, telegram).notify(user.id, target.id) == "sent"


async def test_revoked_token_is_not_retried(db_session: AsyncSession, user: User) -> None:
    """Токен отозван: задача не падает и не повторяется, вакансию отправит досыл позже."""
    await link_chat(db_session, user)
    target = await evaluated(db_session, user)
    telegram = FakeTelegram(errors=[ExternalAccessError("Telegram отклонил токен бота")])

    result = await NotificationService(db_session, telegram).notify(user.id, target.id)

    assert result == "access_denied"
    assert await notifications(db_session) == []
    assert await scheduler(db_session, FakeTaskQueue()).queue_pending() == 1


async def test_blocked_bot_unlinks_chat(db_session: AsyncSession, user: User) -> None:
    await link_chat(db_session, user)
    target = await evaluated(db_session, user)
    telegram = FakeTelegram(errors=[ChatUnavailableError("Forbidden: bot was blocked")])

    result = await NotificationService(db_session, telegram).notify(user.id, target.id)

    assert result == "chat_unavailable"
    await db_session.refresh(user)
    assert user.telegram_chat_id is None
    [notification] = await notifications(db_session)
    assert (notification.status, notification.error) == ("failed", "Forbidden: bot was blocked")


async def test_permanent_error_marks_failed(db_session: AsyncSession, user: User) -> None:
    await link_chat(db_session, user)
    target = await evaluated(db_session, user)
    telegram = FakeTelegram(errors=[PermanentExternalError("Bad Request")])

    assert await NotificationService(db_session, telegram).notify(user.id, target.id) == "failed"

    [notification] = await notifications(db_session)
    assert notification.status == "failed"
    assert await scheduler(db_session, FakeTaskQueue()).queue_pending() == 0  # без повторов


async def test_stale_claim_is_taken_over(db_session: AsyncSession, user: User) -> None:
    await link_chat(db_session, user)
    target = await evaluated(db_session, user)
    db_session.add(
        Notification(
            user_id=user.id,
            vacancy_id=target.id,
            channel="telegram",
            idempotency_key=notification_key("telegram", user.id, target.id),
            status="pending",
        )
    )
    await db_session.commit()
    telegram = FakeTelegram()

    assert await NotificationService(db_session, telegram).notify(user.id, target.id) == "skipped"

    await db_session.execute(
        update(Notification).values(updated_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db_session.commit()
    assert await scheduler(db_session, FakeTaskQueue()).queue_pending() == 1
    assert await NotificationService(db_session, telegram).notify(user.id, target.id) == "sent"


async def test_inactive_vacancy_is_not_sent(db_session: AsyncSession, user: User) -> None:
    await link_chat(db_session, user)
    target = await evaluated(db_session, user)
    target.is_active = False
    await db_session.commit()

    assert await scheduler(db_session, FakeTaskQueue()).queue_pending() == 0
    assert await NotificationService(db_session, FakeTelegram()).notify(user.id, target.id) == (
        "skipped"
    )


async def test_pending_needs_passed_filter_and_active_owner(
    db_session: AsyncSession, user: User
) -> None:
    await link_chat(db_session, user)
    target = await evaluated(db_session, user)
    queue = FakeTaskQueue()
    decision = await db_session.get(VacancyFilterResult, (target.id, user.id))
    assert decision is not None
    resume = await active_resume(db_session, user)

    decision.passed = False
    await db_session.commit()
    assert await scheduler(db_session, queue).queue_pending() == 0

    decision.passed = True
    resume.is_active = False
    await db_session.commit()
    assert await scheduler(db_session, queue).queue_pending() == 0

    resume.is_active = True
    user.is_active = False
    await db_session.commit()
    assert await scheduler(db_session, queue).queue_pending() == 0
    assert queue.notifications == []

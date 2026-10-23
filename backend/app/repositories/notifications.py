from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Evaluation,
    Notification,
    Resume,
    User,
    Vacancy,
    VacancyFilterResult,
)
from app.domain.evaluation import DONE
from app.domain.notifications import NOTIFICATION_PENDING, notification_key
from app.repositories.claims import settled_or_fresh


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self, user_id: int, vacancy_id: int, channel: str, *, stale_before: datetime
    ) -> Notification | None:
        """Захватывает отправку. None — уже отправлено, провалено или отправляется сейчас."""
        key = notification_key(channel, user_id, vacancy_id)
        created = await self._session.scalar(
            insert(Notification)
            .values(
                user_id=user_id,
                vacancy_id=vacancy_id,
                channel=channel,
                idempotency_key=key,
                status=NOTIFICATION_PENDING,
            )
            .on_conflict_do_nothing()
            .returning(Notification.id)
        )
        found = await self._session.scalar(
            select(Notification)
            .where(Notification.idempotency_key == key)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert found is not None  # строка только что вставлена или уже была
        if created is not None:
            return found
        # Захват задачи, упавшей вместе с воркером, перехватываем; остальное не трогаем.
        if found.status != NOTIFICATION_PENDING or found.updated_at >= stale_before:
            return None
        found.updated_at = datetime.now(UTC)
        await self._session.flush()
        return found

    async def release(self, notification: Notification) -> None:
        await self._session.delete(notification)
        await self._session.flush()

    async def pending_pairs(
        self,
        prompt_version: str,
        verdict: str,
        channel: str,
        *,
        stale_before: datetime,
        limit: int,
        vacancy_id: int | None = None,
    ) -> list[tuple[int, int]]:
        """Пары (пользователь, вакансия), о которых пора уведомить.

        Оценка с нужным вердиктом по активному резюме, чат привязан, а оценка сделана после
        привязки — старые вакансии при первой привязке не рассылаются.
        """
        notified = (
            select(Notification.id)
            .where(
                Notification.user_id == User.id,
                Notification.vacancy_id == Vacancy.id,
                Notification.channel == channel,
                settled_or_fresh(
                    Notification.status,
                    Notification.updated_at,
                    pending=NOTIFICATION_PENDING,
                    stale_before=stale_before,
                ),
            )
            .exists()
        )
        stmt = (
            select(User.id, Vacancy.id)
            .select_from(Evaluation)
            .join(Resume, and_(Resume.id == Evaluation.resume_id, Resume.is_active))
            .join(User, User.id == Resume.user_id)
            .join(Vacancy, Vacancy.id == Evaluation.vacancy_id)
            .join(
                VacancyFilterResult,
                and_(
                    VacancyFilterResult.vacancy_id == Vacancy.id,
                    VacancyFilterResult.user_id == User.id,
                    VacancyFilterResult.passed,
                ),
            )
            .where(
                Evaluation.prompt_version == prompt_version,
                Evaluation.status == DONE,
                Evaluation.verdict == verdict,
                Evaluation.updated_at >= User.telegram_linked_at,
                User.is_active,
                User.telegram_chat_id.is_not(None),
                Vacancy.is_active,
                ~notified,
            )
            .order_by(Evaluation.updated_at, Vacancy.id)
            .limit(limit)
        )
        if vacancy_id is not None:
            stmt = stmt.where(Vacancy.id == vacancy_id)
        return [(row[0], row[1]) for row in await self._session.execute(stmt)]

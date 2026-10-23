import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TelegramSettings
from app.core.errors import (
    ChatUnavailableError,
    ExternalAccessError,
    PermanentExternalError,
    TransientExternalError,
)
from app.db.models import Notification
from app.domain.evaluation import DONE
from app.domain.notifications import NOTIFICATION_FAILED, NOTIFICATION_SENT, TELEGRAM_CHANNEL
from app.llm.prompts import PROMPT_VERSION
from app.repositories.claims import stale_cutoff
from app.repositories.notifications import NotificationRepository
from app.repositories.users import UserRepository
from app.repositories.vacancies import VacancyRepository
from app.services.queue import TaskQueue
from app.telegram.client import TelegramClient
from app.telegram.messages import vacancy_message

logger = logging.getLogger(__name__)

NotifyResult = Literal["sent", "skipped", "failed", "chat_unavailable", "access_denied"]

# Уведомляем только о вакансиях, на которые модель советует откликнуться.
NOTIFY_VERDICT = "apply"
# Захват старше этого считается зависшим (воркер упал посреди отправки) и перехватывается.
# Цена перехвата — редкий дубль, если упали ровно между отправкой и записью результата.
STALE_CLAIM = timedelta(minutes=10)
PENDING_BATCH = 50


def stale_before() -> datetime:
    return stale_cutoff(STALE_CLAIM)


class NotificationScheduler:
    """Постановка уведомлений в очередь: после оценки и досылом по расписанию."""

    def __init__(self, session: AsyncSession, queue: TaskQueue, settings: TelegramSettings) -> None:
        self._session = session
        self._queue = queue
        self._settings = settings
        self._notifications = NotificationRepository(session)

    async def queue_pending(self, vacancy_id: int | None = None) -> int:
        if not self._settings.enabled:
            return 0
        pairs = await self._notifications.pending_pairs(
            PROMPT_VERSION,
            NOTIFY_VERDICT,
            TELEGRAM_CHANNEL,
            stale_before=stale_before(),
            limit=PENDING_BATCH,
            vacancy_id=vacancy_id,
        )
        await self._session.commit()
        for user_id, pair_vacancy_id in pairs:
            await self._queue.notify_vacancy(user_id, pair_vacancy_id)
        return len(pairs)


class NotificationService:
    """Отправка уведомления о вакансии. Идемпотентна: вакансия уходит в чат один раз."""

    def __init__(self, session: AsyncSession, client: TelegramClient) -> None:
        self._session = session
        self._client = client
        self._users = UserRepository(session)
        self._vacancies = VacancyRepository(session)
        self._notifications = NotificationRepository(session)

    async def notify(self, user_id: int, vacancy_id: int) -> NotifyResult:
        user = await self._users.get_by_id(user_id)
        if user is None or user.telegram_chat_id is None or not user.is_active:
            return "skipped"
        row = await self._vacancies.get_for_user(vacancy_id, user_id, PROMPT_VERSION)
        evaluation = row.evaluation if row is not None else None
        if (
            row is None
            or evaluation is None
            or evaluation.status != DONE
            or evaluation.verdict != NOTIFY_VERDICT
            or not row.vacancy.is_active
        ):
            return "skipped"

        claim = await self._notifications.claim(
            user_id, vacancy_id, TELEGRAM_CHANNEL, stale_before=stale_before()
        )
        await self._session.commit()  # захват виден другим задачам, отправка — вне транзакции
        if claim is None:
            return "skipped"

        chat_id = user.telegram_chat_id
        try:
            message_id = await self._client.send_message(
                chat_id, vacancy_message(row.vacancy, evaluation)
            )
        except TransientExternalError:
            # Снимаем захват, задачу повторит Celery. Если запрос дошёл, а ответ потерялся
            # (таймаут), повтор пришлёт дубль — это осознанная цена: потерять вакансию хуже.
            await self._release(claim)
            raise
        except ExternalAccessError as exc:
            # Токен бота отозван: повторы бесполезны. Захват снят — отправит досыл,
            # когда токен заменят; до тех пор каждый досыл даёт одну ошибку в лог на пару.
            logger.error("Telegram не принимает токен бота: %s", exc.message)
            await self._release(claim)
            return "access_denied"
        except ChatUnavailableError as exc:
            # Бот заблокирован — писать в этот чат бессмысленно, отвязываем его.
            await self._users.release_chat(chat_id)
            await self._fail(claim, exc.message)
            return "chat_unavailable"
        except PermanentExternalError as exc:
            await self._fail(claim, exc.message)
            return "failed"

        claim.status = NOTIFICATION_SENT
        claim.message_id = message_id
        claim.sent_at = datetime.now(UTC)
        await self._session.commit()
        return "sent"

    async def _release(self, claim: Notification) -> None:
        await self._notifications.release(claim)
        await self._session.commit()

    async def _fail(self, claim: Notification, message: str) -> None:
        logger.warning("Уведомление %d не отправлено: %s", claim.id, message)
        claim.status = NOTIFICATION_FAILED
        claim.error = message
        await self._session.commit()

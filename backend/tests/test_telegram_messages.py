import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.methods import SendMessage

from app.core.errors import (
    ChatUnavailableError,
    ExternalAccessError,
    ExternalServiceError,
    PermanentExternalError,
    TransientExternalError,
)
from app.db.models import Evaluation, Vacancy
from app.telegram.client import AiogramTelegramClient
from app.telegram.messages import (
    MAX_ITEM_CHARS,
    ApplicationCallback,
    vacancy_keyboard,
    vacancy_message,
)
from tests.fakes import BOT_USERNAME, TEST_BOT_TOKEN, RecordingSession, recording_bot

URL = "https://getmatch.ru/vacancies/1"


def make_vacancy(**fields: object) -> Vacancy:
    values: dict[str, object] = {
        "id": 5,
        "url": URL,
        "title": "Python Developer",
        "company": "Example",
        "salary_from": 200_000,
        "salary_to": 250_000,
        "salary_currency": "RUB",
        "salary_gross": False,
        "work_formats": ["remote"],
        "contract_types": ["GPH", "IP"],
    }
    values.update(fields)
    return Vacancy(**values)


def make_evaluation(**fields: object) -> Evaluation:
    values: dict[str, object] = {
        "score": 82,
        "verdict": "apply",
        "matches": [{"requirement": f"Навык {n}", "evidence": f"Опыт {n}"} for n in range(1, 5)],
        "gaps": [
            {"requirement": "Kafka", "severity": "minor"},
            {"requirement": "Go", "severity": "blocker"},
        ],
    }
    values.update(fields)
    return Evaluation(**values)


def test_message_has_key_facts() -> None:
    message = vacancy_message(make_vacancy(), make_evaluation())

    assert message.text.startswith("<b>Python Developer</b>\nExample\n")
    assert "Зарплата: 200 000 – 250 000 RUB на руки" in message.text
    assert "Оформление: ГПХ, ИП" in message.text
    assert "Оценка: <b>82</b>/100" in message.text
    assert "• Навык 3 — Опыт 3" in message.text
    assert "Навык 4" not in message.text  # не больше трёх пунктов
    assert "• Kafka\n• Go (обязательно)" in message.text


def test_message_without_salary_and_contract() -> None:
    vacancy = make_vacancy(salary_from=None, salary_to=None, contract_types=[], company=None)

    text = vacancy_message(vacancy, make_evaluation(matches=[], gaps=None)).text

    assert "Зарплата: не указана" in text
    assert "Оформление: не указано" in text
    assert "Совпадения" not in text
    assert "Пробелы" not in text


def test_vacancy_and_model_text_is_escaped() -> None:
    vacancy = make_vacancy(title="<script>Dev & Ops</script>", company="A" * 500)

    text = vacancy_message(vacancy, make_evaluation(matches=[], gaps=[])).text

    assert "<b>&lt;script&gt;Dev &amp; Ops&lt;/script&gt;</b>" in text
    assert "A" * MAX_ITEM_CHARS not in text
    assert "A" * (MAX_ITEM_CHARS - 1) + "…" in text


def test_keyboard_marks_selected_status() -> None:
    keyboard = vacancy_keyboard(5, URL, "declined")

    [applied, declined], [open_button] = keyboard.inline_keyboard
    assert (applied.text, declined.text) == ("Откликнусь", "✓ Не подходит")
    assert applied.callback_data == "app:5:applied"
    assert ApplicationCallback.unpack(declined.callback_data or "").status == "declined"
    assert open_button.url == URL


SEND = SendMessage(chat_id=1, text="x")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TelegramRetryAfter(SEND, "Too Many Requests", retry_after=5), TransientExternalError),
        (TelegramNetworkError(SEND, "timeout"), TransientExternalError),
        (TelegramServerError(SEND, "Bad Gateway"), TransientExternalError),
        (TelegramForbiddenError(SEND, "bot was blocked by the user"), ChatUnavailableError),
        (TelegramUnauthorizedError(SEND, "Unauthorized"), ExternalAccessError),
        (TelegramBadRequest(SEND, "chat not found"), PermanentExternalError),
    ],
)
async def test_client_maps_aiogram_errors(
    error: Exception, expected: type[ExternalServiceError]
) -> None:
    client = AiogramTelegramClient(recording_bot(RecordingSession(errors={SendMessage: error})))
    message = vacancy_message(make_vacancy(), make_evaluation())

    with pytest.raises(expected) as raised:
        await client.send_message(1, message)
    assert TEST_BOT_TOKEN not in raised.value.message


async def test_client_sends_with_keyboard() -> None:
    session = RecordingSession()
    client = AiogramTelegramClient(recording_bot(session))

    assert await client.bot_username() == BOT_USERNAME
    assert await client.send_message(7, vacancy_message(make_vacancy(), make_evaluation())) == 2
    [sent] = session.calls(SendMessage)
    assert sent.chat_id == 7
    assert sent.reply_markup.inline_keyboard[1][0].url == URL

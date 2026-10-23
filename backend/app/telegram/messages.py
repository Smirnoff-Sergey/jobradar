"""Тексты и клавиатуры сообщений бота. Без сети: всё проверяется юнит-тестами."""

from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from typing import Any

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Evaluation, Vacancy
from app.domain.applications import ApplicationStatus
from app.llm.prompts import format_salary

# Сколько совпадений и пробелов показывать: сообщение должно читаться с телефона.
TOP_ITEMS = 3
MAX_ITEM_CHARS = 150

CONTRACT_LABELS = {"TK": "ТК", "GPH": "ГПХ", "IP": "ИП", "SELF_EMPLOYED": "самозанятость"}
STATUS_BUTTONS: tuple[tuple[ApplicationStatus, str], ...] = (
    ("applied", "Откликнусь"),
    ("declined", "Не подходит"),
)
STATUS_LABELS: dict[str, str] = {
    "new": "новый",
    "letter_ready": "письмо готово",
    "applied": "откликнулся",
    "invited": "пригласили",
    "rejected": "отказ",
    "declined": "не подходит",
}
SELECTED_MARK = "✓ "


class ApplicationCallback(CallbackData, prefix="app"):
    """Нажатие кнопки статуса: «app:<vacancy_id>:<status>» (лимит Telegram — 64 байта)."""

    vacancy_id: int
    status: str


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    text: str  # HTML-разметка Telegram
    keyboard: InlineKeyboardMarkup


def vacancy_keyboard(vacancy_id: int, url: str, selected: str | None) -> InlineKeyboardMarkup:
    """Кнопки статусов (выбранная отмечена) и ссылка на вакансию."""
    status_row = [
        InlineKeyboardButton(
            text=(SELECTED_MARK if status == selected else "") + label,
            callback_data=ApplicationCallback(vacancy_id=vacancy_id, status=status).pack(),
        )
        for status, label in STATUS_BUTTONS
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[status_row, [InlineKeyboardButton(text="Открыть", url=url)]]
    )


def vacancy_message(vacancy: Vacancy, evaluation: Evaluation) -> OutgoingMessage:
    lines = [f"<b>{_text(vacancy.title)}</b>"]
    if vacancy.company:
        lines.append(_text(vacancy.company))
    lines.append(f"Зарплата: {_text(format_salary(vacancy) or 'не указана')}")
    contracts = ", ".join(CONTRACT_LABELS.get(code, code) for code in vacancy.contract_types)
    lines.append(f"Оформление: {_text(contracts or 'не указано')}")
    lines.append(f"Оценка: <b>{evaluation.score}</b>/100")
    lines += _section("Совпадения", evaluation.matches, _match)
    lines += _section("Пробелы", evaluation.gaps, _gap)
    return OutgoingMessage(
        text="\n".join(lines), keyboard=vacancy_keyboard(vacancy.id, vacancy.url, None)
    )


def _section(
    title: str, items: list[dict[str, Any]] | None, render: Callable[[dict[str, Any]], str]
) -> list[str]:
    if not items:
        return []
    return ["", f"<b>{title}:</b>", *(f"• {render(item)}" for item in items[:TOP_ITEMS])]


def _match(item: dict[str, Any]) -> str:
    return _text(f"{item.get('requirement', '')} — {item.get('evidence', '')}")


def _gap(item: dict[str, Any]) -> str:
    suffix = " (обязательно)" if item.get("severity") == "blocker" else ""
    return _text(str(item.get("requirement", ""))) + suffix


def _text(value: str) -> str:
    # Текст вакансии и ответ модели — данные: экранируем, чтобы не сломать HTML-разметку.
    if len(value) > MAX_ITEM_CHARS:
        value = value[: MAX_ITEM_CHARS - 1] + "…"
    return escape(value, quote=False)

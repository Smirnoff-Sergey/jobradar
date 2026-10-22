"""Фильтр вакансий по критериям поиска. Чистые функции: без БД и сети."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

# НДФЛ упрощённо — 13%. Прогрессивную шкалу не учитываем: для грубого отсева этого достаточно.
NDFL_RATE = 0.13
RUB = "RUB"


class FilterCriteria(Protocol):
    # Свойства, а не атрибуты: модели ORM хранят list[str], а протоколу хватает Sequence[str].
    @property
    def title_keywords(self) -> Sequence[str]: ...

    @property
    def stop_words(self) -> Sequence[str]: ...

    @property
    def min_salary(self) -> int | None: ...

    @property
    def min_salary_is_net(self) -> bool: ...

    @property
    def remote_only(self) -> bool: ...

    @property
    def contract_types(self) -> Sequence[str]: ...


class FilterableVacancy(Protocol):
    @property
    def title(self) -> str: ...

    @property
    def company(self) -> str | None: ...

    @property
    def short_description(self) -> str | None: ...

    @property
    def salary_from(self) -> int | None: ...

    @property
    def salary_to(self) -> int | None: ...

    @property
    def salary_currency(self) -> str | None: ...

    @property
    def salary_gross(self) -> bool | None: ...

    @property
    def work_formats(self) -> Sequence[str]: ...

    @property
    def contract_types(self) -> Sequence[str]: ...


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    """Критерии поиска как значение. Удовлетворяет FilterCriteria, как и модель SearchProfile."""

    title_keywords: Sequence[str] = ()
    stop_words: Sequence[str] = ()
    min_salary: int | None = None
    min_salary_is_net: bool = True
    remote_only: bool = True
    contract_types: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class FilterDecision:
    passed: bool
    reasons: tuple[str, ...] = ()
    salary_unknown: bool = False


def _contains_word(text: str, word: str) -> bool:
    # Границы слова: стоп-слово «go» не должно срабатывать на «Google».
    return re.search(rf"(?<!\w){re.escape(word.lower())}(?!\w)", text) is not None


def _matching(text: str, words: Iterable[str]) -> list[str]:
    return [word for word in words if word.strip() and _contains_word(text, word.strip())]


def _after_tax(amount: int) -> int:
    return round(amount * (1 - NDFL_RATE))


def net_salary(vacancy: FilterableVacancy) -> int | None:
    """Верхняя граница зарплаты на руки в рублях; None — если узнать нельзя."""
    upper = vacancy.salary_to or vacancy.salary_from
    if upper is None or vacancy.salary_currency != RUB:
        return None
    # Если источник не сказал про налоги, считаем сумму «на руки»: лучше пропустить лишнее.
    return _after_tax(upper) if vacancy.salary_gross else upper


def required_net_salary(criteria: FilterCriteria) -> int | None:
    if criteria.min_salary is None:
        return None
    return criteria.min_salary if criteria.min_salary_is_net else _after_tax(criteria.min_salary)


def evaluate(criteria: FilterCriteria, vacancy: FilterableVacancy) -> FilterDecision:
    reasons: list[str] = []
    title = vacancy.title.lower()
    text = " ".join(
        part for part in (vacancy.title, vacancy.company, vacancy.short_description) if part
    ).lower()

    if criteria.title_keywords and not _matching(title, criteria.title_keywords):
        reasons.append("в названии нет ключевых слов")

    if stop_words := _matching(text, criteria.stop_words):
        reasons.append(f"стоп-слова: {', '.join(stop_words)}")

    if criteria.remote_only and "remote" not in vacancy.work_formats:
        reasons.append("нет удалёнки")

    # Пустой список у вакансии — источник не сообщил оформление; такое не отсеиваем.
    if (
        criteria.contract_types
        and vacancy.contract_types
        and not set(criteria.contract_types) & set(vacancy.contract_types)
    ):
        reasons.append("неподходящее оформление")

    salary = net_salary(vacancy)
    required = required_net_salary(criteria)
    if salary is not None and required is not None and salary < required:
        reasons.append(f"зарплата ниже порога: {salary} < {required} на руки")

    return FilterDecision(
        passed=not reasons,
        reasons=tuple(reasons),
        salary_unknown=salary is None,
    )

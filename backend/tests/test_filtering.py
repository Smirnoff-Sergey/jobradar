from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from app.domain.filtering import evaluate, net_salary
from tests.fakes import vacancy


@dataclass
class Criteria:
    title_keywords: Sequence[str] = ("python",)
    stop_words: Sequence[str] = ()
    min_salary: int | None = 150_000
    min_salary_is_net: bool = True
    remote_only: bool = True
    contract_types: Sequence[str] = field(default_factory=list)


def test_matching_vacancy_passes() -> None:
    decision = evaluate(Criteria(), vacancy("1"))

    assert decision.passed
    assert decision.reasons == ()
    assert not decision.salary_unknown


def test_title_keywords_use_word_boundaries() -> None:
    criteria = Criteria(title_keywords=("go",))

    assert evaluate(criteria, vacancy("1", title="Go Developer")).passed
    assert not evaluate(criteria, vacancy("2", title="Google Ads manager")).passed


def test_stop_words_check_company_and_description() -> None:
    criteria = Criteria(stop_words=("devops", "Битрикс"))

    decision = evaluate(criteria, vacancy("1", short_description="Поддержка 1С-Битрикс и DevOps"))

    assert not decision.passed
    assert decision.reasons == ("стоп-слова: devops, Битрикс",)


def test_remote_only() -> None:
    decision = evaluate(Criteria(), vacancy("1", work_formats=("office", "hybrid")))

    assert decision.reasons == ("нет удалёнки",)
    assert evaluate(Criteria(remote_only=False), vacancy("2", work_formats=("office",))).passed


def test_unknown_salary_passes_with_flag() -> None:
    decision = evaluate(Criteria(), vacancy("1", salary_from=None, salary_to=None))

    assert decision.passed
    assert decision.salary_unknown


def test_foreign_currency_counts_as_unknown() -> None:
    decision = evaluate(Criteria(), vacancy("1", salary_to=3_000, salary_currency="USD"))

    assert decision.passed
    assert decision.salary_unknown


def test_low_salary_is_rejected() -> None:
    decision = evaluate(Criteria(), vacancy("1", salary_from=100_000, salary_to=140_000))

    assert not decision.passed
    assert decision.reasons == ("зарплата ниже порога: 140000 < 150000 на руки",)


@pytest.mark.parametrize(
    ("salary_gross", "expected"),
    [(False, 170_000), (True, 147_900), (None, 170_000)],
)
def test_net_salary_converts_gross(salary_gross: bool | None, expected: int) -> None:
    assert net_salary(vacancy("1", salary_to=170_000, salary_gross=salary_gross)) == expected


def test_gross_threshold_is_converted_to_net() -> None:
    criteria = Criteria(min_salary=200_000, min_salary_is_net=False)  # 174 000 на руки

    assert evaluate(criteria, vacancy("1", salary_to=180_000)).passed
    assert not evaluate(criteria, vacancy("2", salary_to=170_000)).passed


def test_contract_types_unknown_passes_known_mismatch_rejected() -> None:
    criteria = Criteria(contract_types=["GPH", "IP"])

    assert evaluate(criteria, vacancy("1", contract_types=())).passed
    assert evaluate(criteria, vacancy("2", contract_types=("TK", "IP"))).passed
    assert not evaluate(criteria, vacancy("3", contract_types=("TK",))).passed


def test_all_reasons_are_collected() -> None:
    decision = evaluate(
        Criteria(stop_words=("php",)),
        vacancy("1", title="PHP Developer", work_formats=("office",), salary_to=50_000),
    )

    assert len(decision.reasons) == 4

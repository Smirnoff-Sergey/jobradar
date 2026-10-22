import json
from pathlib import Path

import httpx
import pytest
import respx

from app.core.config import LLMSettings
from app.core.errors import PaidUsageError
from app.llm.dataset import load_dataset, to_record
from app.llm.prompts import VacancyForPrompt
from app.llm.quality import Prediction, compare, format_report
from scripts import eval as eval_script
from tests.fakes import completion_body, llm_answer

DEMO = Path(__file__).resolve().parent.parent / "scripts" / "eval_demo"


def test_demo_dataset_is_labeled() -> None:
    items = load_dataset(DEMO / "vacancies.jsonl")

    assert len(items) == 5
    assert {item.label for item in items} == {"apply", "maybe", "skip"}


def test_unknown_label_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "set.jsonl"
    path.write_text(json.dumps({"id": "1", "title": "Dev", "label": "yes"}), encoding="utf-8")

    with pytest.raises(ValueError, match="неизвестная метка"):
        load_dataset(path)


def test_record_for_labeling_roundtrip(tmp_path: Path) -> None:
    vacancy = VacancyForPrompt(title="Dev", work_formats=("remote",), description="<p>Python</p>")
    path = tmp_path / "set.jsonl"
    record = to_record("getmatch:1", vacancy, url="https://example.com/1")
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    [item] = load_dataset(path)

    assert record["description"] == "Python"
    assert item.label is None  # не размечено
    assert item.vacancy.work_formats == ("remote",)


def test_quality_report() -> None:
    report = compare(
        [
            Prediction("apply", "apply"),
            Prediction("apply", "maybe"),
            Prediction("skip", "maybe"),
            Prediction("skip", None),
        ]
    )

    assert (report.total, report.answered, report.exact, report.binary) == (4, 3, 1, 2)
    assert "Точный вердикт: 1/3 (33%)" in format_report(report)
    confusion = report.as_dict()["confusion"]
    assert isinstance(confusion, list)
    assert confusion[0] == {"label": "apply", "predicted": "apply", "count": 1}


@respx.mock
async def test_eval_run_with_mocked_openrouter(tmp_path: Path) -> None:
    settings = LLMSettings(api_key="test-key")
    answers = {
        "apply": llm_answer(),
        "maybe": llm_answer(55, "maybe"),
        "skip": llm_answer(10, "skip"),
    }
    items = eval_script.labeled(DEMO / "vacancies.jsonl", None)
    respx.post(f"{settings.base_url}/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json=completion_body(answers[label])) for _, label in items
        ]
    )
    out_path = tmp_path / "results.jsonl"

    with out_path.open("w", encoding="utf-8") as out:
        report = await eval_script.run(items, "резюме", settings, out=out, pause=0)

    assert (report.answered, report.exact) == (5, 5)
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert [row["predicted"] for row in rows] == [label for _, label in items]


@respx.mock
async def test_eval_stops_on_paid_response() -> None:
    settings = LLMSettings(api_key="test-key")
    items = eval_script.labeled(DEMO / "vacancies.jsonl", 2)
    route = respx.post(f"{settings.base_url}/chat/completions").respond(
        json=completion_body(llm_answer(), cost=0.001)
    )

    with pytest.raises(PaidUsageError):
        await eval_script.run(items, "резюме", settings, pause=0)
    assert route.call_count == 1

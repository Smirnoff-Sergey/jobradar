import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from app import cli
from app.core.errors import ConflictError


def _passwords(monkeypatch: pytest.MonkeyPatch, *answers: str) -> None:
    replies: Iterator[str] = iter(answers)
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(replies))


def test_create_user_command(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[tuple[str, str]] = []

    async def fake_create_user(email: str, password: str) -> None:
        created.append((email, password))

    monkeypatch.setattr(cli, "create_user", fake_create_user)
    _passwords(monkeypatch, "long-password", "long-password")

    assert cli.main(["create-user", "--email", "owner@example.com"]) == 0
    assert created == [("owner@example.com", "long-password")]


def test_create_user_command_password_mismatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _passwords(monkeypatch, "long-password", "other-password")

    assert cli.main(["create-user", "--email", "owner@example.com"]) == 1
    assert "не совпадают" in capsys.readouterr().err


def test_create_user_command_reports_app_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def failing_create_user(email: str, password: str) -> None:
        raise ConflictError("Пользователь с таким email уже есть")

    monkeypatch.setattr(cli, "create_user", failing_create_user)
    _passwords(monkeypatch, "long-password", "long-password")

    assert cli.main(["create-user", "--email", "owner@example.com"]) == 1
    assert "уже есть" in capsys.readouterr().err


def test_openapi_command(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"

    assert cli.main(["openapi", "--out", str(out)]) == 0
    schema = json.loads(out.read_text(encoding="utf-8"))
    operation_ids = [
        operation["operationId"] for path in schema["paths"].values() for operation in path.values()
    ]
    # Имена обработчиков, без суффиксов пути и метода — из них генерируются типы frontend.
    assert "list_vacancies" in operation_ids
    assert len(operation_ids) == len(set(operation_ids))
    evaluation = schema["components"]["schemas"]["EvaluationRead"]["properties"]
    assert "Match" in json.dumps(evaluation["matches"])

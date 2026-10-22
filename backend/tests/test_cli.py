from collections.abc import Iterator

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

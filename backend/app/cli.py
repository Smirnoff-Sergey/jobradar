"""Служебные команды.

python -m app.cli create-user --email owner@example.com
python -m app.cli load-resume --email owner@example.com --file резюме.txt [--title ...]
python -m app.cli export-eval-set --out vacancies.jsonl [--limit 20]
python -m app.cli llm-unpause
"""

import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import open_session_factory
from app.llm.dataset import to_record
from app.llm.prompts import vacancy_for_prompt
from app.services.auth import AuthService
from app.services.llm_budget import LLMBudget
from app.services.resumes import ResumeService
from app.services.vacancies import VacancyService


async def create_user(email: str, password: str) -> None:
    settings = get_settings()
    async with (
        open_session_factory(settings.database_url) as session_factory,
        session_factory() as session,
    ):
        user = await AuthService(session, settings).create_user(email, password)
    print(f"Создан пользователь id={user.id} email={user.email}")


async def load_resume(email: str, text: str, title: str) -> None:
    async with (
        open_session_factory(get_settings().database_url) as session_factory,
        session_factory() as session,
    ):
        resume = await ResumeService(session).create_for_email(email, title, text)
    print(f"Загружено резюме id={resume.id} ({len(text)} символов), оно активно")


async def eval_set_records(limit: int) -> list[dict[str, object]]:
    async with (
        open_session_factory(get_settings().database_url) as session_factory,
        session_factory() as session,
    ):
        vacancies = await VacancyService(session).for_labeling(limit)
    return [
        to_record(
            f"{v.source_code}:{v.external_id}", vacancy_for_prompt(v, v.description), url=v.url
        )
        for v in vacancies
    ]


def export_eval_set(path: Path, limit: int) -> None:
    records = asyncio.run(eval_set_records(limit))
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    print(f"Выгружено вакансий: {len(records)} → {path}. Проставьте label: apply/maybe/skip")


async def llm_unpause() -> None:
    settings = get_settings()
    async with (
        open_session_factory(settings.database_url) as session_factory,
        session_factory() as session,
    ):
        budget = LLMBudget(session, settings.llm)
        usage = await budget.usage()
        await budget.unpause()
    print(f"Остановка LLM-оценки снята (была: {usage.pause_reason or 'нет'})")


def _ask_password() -> str | None:
    password = getpass.getpass("Пароль: ")
    if password != getpass.getpass("Повторите пароль: "):
        print("Пароли не совпадают", file=sys.stderr)
        return None
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="создать пользователя")
    create.add_argument("--email", required=True)

    resume = commands.add_parser("load-resume", help="загрузить резюме из файла и сделать активным")
    resume.add_argument("--email", required=True)
    resume.add_argument("--file", required=True, type=Path)
    resume.add_argument("--title", default="Основное резюме")

    export = commands.add_parser("export-eval-set", help="выгрузить вакансии для разметки")
    export.add_argument("--out", required=True, type=Path)
    export.add_argument("--limit", type=int, default=20)

    commands.add_parser("llm-unpause", help="снять аварийную остановку LLM-оценки")

    args = parser.parse_args(argv)
    try:
        if args.command == "create-user":
            password = _ask_password()
            if password is None:
                return 1
            asyncio.run(create_user(args.email, password))
        elif args.command == "load-resume":
            text = args.file.read_text(encoding="utf-8").strip()
            asyncio.run(load_resume(args.email, text, args.title))
        elif args.command == "export-eval-set":
            export_eval_set(args.out, args.limit)
        else:
            asyncio.run(llm_unpause())
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

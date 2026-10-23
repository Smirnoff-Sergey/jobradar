"""Служебные команды.

python -m app.cli create-user --email owner@example.com
python -m app.cli load-resume --email owner@example.com --file резюме.txt [--title ...]
python -m app.cli export-eval-set --out vacancies.jsonl [--limit 20]
python -m app.cli llm-unpause
python -m app.cli telegram-link --email owner@example.com
python -m app.cli telegram-webhook --url https://example.com/api/v1/telegram/webhook | --delete
python -m app.cli openapi --out ../frontend/openapi.json
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
from app.services.telegram_link import TelegramLinkService
from app.services.vacancies import VacancyService
from app.telegram.client import call, open_bot, open_telegram_client


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


async def telegram_link(email: str) -> None:
    settings = get_settings()
    async with (
        open_session_factory(settings.database_url) as session_factory,
        session_factory() as session,
        open_telegram_client(settings.telegram) as client,
    ):
        link = await TelegramLinkService(session, settings.telegram).issue_link_for_email(
            email, client
        )
    expires = link.expires_at.astimezone().strftime("%H:%M")
    print(f"Откройте в Telegram и нажмите «Start» (действует до {expires}):\n{link.url}")


async def telegram_webhook(url: str | None) -> None:
    """Регистрирует вебхук с секретом из настроек или удаляет его (возврат к polling)."""
    settings = get_settings().telegram
    async with open_bot(settings) as bot:
        if url is None:
            await call(bot.delete_webhook())
            print("Вебхук удалён: обновления снова забирает python -m app.bot (polling)")
            return
        if settings.webhook_secret is None:
            raise AppError("Не задан JOBRADAR_TELEGRAM__WEBHOOK_SECRET")
        await call(bot.set_webhook(url, secret_token=settings.webhook_secret.get_secret_value()))
    print(f"Вебхук зарегистрирован: {url}. В API нужен JOBRADAR_TELEGRAM__MODE=webhook")


def dump_openapi(path: Path) -> None:
    """Снимок схемы API для генерации типов frontend. БД и настройки не нужны."""
    from app.main import app

    schema = json.dumps(app.openapi(), ensure_ascii=False, indent=2)
    path.write_text(f"{schema}\n", encoding="utf-8", newline="\n")
    print(f"Схема OpenAPI записана: {path}")


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

    link = commands.add_parser("telegram-link", help="ссылка для привязки чата Telegram")
    link.add_argument("--email", required=True)

    webhook = commands.add_parser("telegram-webhook", help="зарегистрировать или удалить вебхук")
    target = webhook.add_mutually_exclusive_group(required=True)
    target.add_argument("--url", help="публичный HTTPS-адрес /api/v1/telegram/webhook")
    target.add_argument("--delete", action="store_true")

    openapi = commands.add_parser("openapi", help="выгрузить схему OpenAPI в файл")
    openapi.add_argument("--out", required=True, type=Path)

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
        elif args.command == "telegram-link":
            asyncio.run(telegram_link(args.email))
        elif args.command == "openapi":
            dump_openapi(args.out)
        elif args.command == "telegram-webhook":
            asyncio.run(telegram_webhook(None if args.delete else args.url))
        else:
            asyncio.run(llm_unpause())
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

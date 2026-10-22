"""Служебные команды. Запуск: python -m app.cli create-user --email owner@example.com"""

import argparse
import asyncio
import getpass
import sys

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import open_session_factory
from app.services.auth import AuthService


async def create_user(email: str, password: str) -> None:
    settings = get_settings()
    async with (
        open_session_factory(settings.database_url) as session_factory,
        session_factory() as session,
    ):
        user = await AuthService(session, settings).create_user(email, password)
    print(f"Создан пользователь id={user.id} email={user.email}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="создать пользователя")
    create.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    password = getpass.getpass("Пароль: ")
    if password != getpass.getpass("Повторите пароль: "):
        print("Пароли не совпадают", file=sys.stderr)
        return 1
    try:
        asyncio.run(create_user(args.email, password))
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

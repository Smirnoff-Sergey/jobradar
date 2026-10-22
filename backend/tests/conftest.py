import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Connection, make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# Секрет нужен до первого вызова get_settings().
os.environ.setdefault("JOBRADAR_JWT_SECRET", "test-secret-" + "x" * 52)

from app.api.deps import get_session
from app.core.config import Settings, get_settings
from app.db.models import User
from app.main import create_app
from app.services.auth import AuthService
from tests.constants import USER_EMAIL, USER_PASSWORD

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL_ENV = "JOBRADAR_TEST_DATABASE_URL"
TEST_DATABASE_SUFFIX = "_test"


def _upgrade_to_head(connection: Connection) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


def _test_database_url() -> str:
    url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not url:
        message = f"интеграционные тесты: не задана переменная {TEST_DATABASE_URL_ENV}"
        if os.environ.get("CI"):
            pytest.fail(message)  # в CI тихий пропуск дал бы зелёную сборку без тестов
        pytest.skip(message)
    database = make_url(url).database or ""
    if not database.endswith(TEST_DATABASE_SUFFIX):
        # Фикстура удаляет схему целиком: защищаемся от случайно указанной рабочей базы.
        pytest.exit(f"имя тестовой БД должно оканчиваться на {TEST_DATABASE_SUFFIX}: {database}")
    return url


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_test_database_url(), poolclass=NullPool)
    async with engine.begin() as conn:
        # Тестовая БД пересоздаётся с нуля и заполняется миграциями — так проверяются и они.
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(_upgrade_to_head)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Сессия внутри внешней транзакции.

    commit() в коде становится SAVEPOINT, после теста всё откатывается.
    """
    async with engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def auth_service(db_session: AsyncSession, settings: Settings) -> AuthService:
    return AuthService(db_session, settings)


@pytest.fixture
async def user(auth_service: AuthService) -> User:
    return await auth_service.create_user(USER_EMAIL, USER_PASSWORD)


@pytest.fixture
def app(db_session: AsyncSession) -> FastAPI:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

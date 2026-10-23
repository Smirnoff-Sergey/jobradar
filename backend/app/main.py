from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api import metrics
from app.api.errors import register_error_handlers
from app.api.middleware import register_request_middleware
from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import open_session_factory
from app.telegram.client import open_bot
from app.telegram.handlers import create_dispatcher


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.logging.level, settings.logging.format)
    async with open_session_factory(settings.database_url) as session_factory:
        app.state.session_factory = session_factory
        if settings.telegram.enabled and settings.telegram.mode == "webhook":
            # Вебхук: обновления Telegram обрабатывает API теми же обработчиками, что и polling.
            async with open_bot(settings.telegram) as bot:
                app.state.telegram_bot = bot
                app.state.telegram_dispatcher = create_dispatcher(
                    session_factory, settings.telegram
                )
                yield
        else:
            yield


def _operation_id(route: APIRoute) -> str:
    # Имя обработчика вместо «list_vacancies_api_v1_vacancies_get»:
    # из схемы генерируются типы frontend.
    return route.name


def create_app() -> FastAPI:
    app = FastAPI(
        title="JobRadar",
        version="0.1.0",
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    register_error_handlers(app)
    register_request_middleware(app)
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(metrics.router)
    return app


app = create_app()

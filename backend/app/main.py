from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.v1 import api_router
from app.core.config import get_settings
from app.db.session import open_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with open_session_factory(get_settings().database_url) as session_factory:
        app.state.session_factory = session_factory
        yield


def create_app() -> FastAPI:
    app = FastAPI(title="JobRadar", version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()

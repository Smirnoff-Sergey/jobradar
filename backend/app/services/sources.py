from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.db.models import Source
from app.repositories.sources import SourceRepository
from app.services.queue import TaskQueue


class SourceService:
    def __init__(self, session: AsyncSession, queue: TaskQueue) -> None:
        self._sources = SourceRepository(session)
        self._queue = queue

    async def list_all(self) -> Sequence[Source]:
        return await self._sources.list_all()

    async def run(self, code: str) -> str:
        source = await self._sources.get(code)
        if source is None:
            raise NotFoundError(f"Неизвестный источник: {code}")
        if not source.is_enabled:
            raise ConflictError(f"Источник {code} отключён")
        return await self._queue.collect_source(code)

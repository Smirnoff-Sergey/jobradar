from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SearchProfile


class SearchProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user(self, user_id: int) -> SearchProfile | None:
        return await self._session.scalar(
            select(SearchProfile).where(SearchProfile.user_id == user_id)
        )

    async def list_all(self) -> Sequence[SearchProfile]:
        return (await self._session.scalars(select(SearchProfile))).all()

    async def add(self, profile: SearchProfile) -> SearchProfile:
        self._session.add(profile)
        await self._session.flush()
        return profile

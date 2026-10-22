import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PermanentExternalError, TransientExternalError
from app.db.models import Vacancy
from app.repositories.vacancies import VacancyRepository
from app.services.details import VacancyDetailsService
from tests.fakes import FakeAdapter, vacancy


async def store(session: AsyncSession, external_id: str = "1") -> int:
    [vacancy_id] = await VacancyRepository(session).upsert_many("getmatch", [vacancy(external_id)])
    await session.commit()
    return vacancy_id


def service(session: AsyncSession, adapter: FakeAdapter) -> VacancyDetailsService:
    return VacancyDetailsService(session, lambda _code: adapter)


async def stored(session: AsyncSession, vacancy_id: int) -> Vacancy:
    found = await VacancyRepository(session).get(vacancy_id)
    assert found is not None
    return found


async def test_loads_description_once(db_session: AsyncSession) -> None:
    vacancy_id = await store(db_session)
    adapter = FakeAdapter(descriptions={"1": "<p>Полное описание</p>"})

    assert await service(db_session, adapter).load_description(vacancy_id)
    assert not await service(db_session, adapter).load_description(vacancy_id)

    found = await stored(db_session, vacancy_id)
    assert found.description == "<p>Полное описание</p>"
    assert found.description_fetched_at is not None
    assert adapter.description_requests == ["1"]


async def test_missing_description_is_remembered(db_session: AsyncSession) -> None:
    vacancy_id = await store(db_session)
    adapter = FakeAdapter()

    assert not await service(db_session, adapter).load_description(vacancy_id)
    assert not await service(db_session, adapter).load_description(vacancy_id)
    assert adapter.description_requests == ["1"]


async def test_permanent_error_is_remembered(db_session: AsyncSession) -> None:
    vacancy_id = await store(db_session)
    adapter = FakeAdapter(error=PermanentExternalError("HTTP 404"))

    assert not await service(db_session, adapter).load_description(vacancy_id)

    assert (await stored(db_session, vacancy_id)).description_fetched_at is not None


async def test_transient_error_propagates_for_retry(db_session: AsyncSession) -> None:
    vacancy_id = await store(db_session)
    adapter = FakeAdapter(error=TransientExternalError("timeout"))

    with pytest.raises(TransientExternalError):
        await service(db_session, adapter).load_description(vacancy_id)

    assert (await stored(db_session, vacancy_id)).description_fetched_at is None


async def test_unknown_vacancy(db_session: AsyncSession) -> None:
    assert not await service(db_session, FakeAdapter()).load_description(999_999)

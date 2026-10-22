import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.errors import TransientExternalError
from app.db.models import SearchProfile, Vacancy, VacancyFilterResult
from tests.fakes import FakeAdapter, FakeTaskQueue, collector, get_source, vacancy


async def count_vacancies(session: AsyncSession, *, active: bool | None = None) -> int:
    stmt = select(func.count()).select_from(Vacancy)
    if active is not None:
        stmt = stmt.where(Vacancy.is_active.is_(active))
    return await session.scalar(stmt) or 0


async def vacancy_by_external_id(session: AsyncSession, external_id: str) -> Vacancy:
    found = await session.scalar(select(Vacancy).where(Vacancy.external_id == external_id))
    assert found is not None
    await session.refresh(found)
    return found


async def test_first_run_stores_filters_and_queues_details(
    db_session: AsyncSession, profile: SearchProfile
) -> None:
    adapter = FakeAdapter(
        pages=[
            [vacancy("1"), vacancy("2", title="PHP Developer")],
            [vacancy("3", work_formats=("office",))],
        ]
    )
    queue = FakeTaskQueue()

    stats = await collector(db_session, adapter, queue).collect()

    assert (stats.status, stats.received, stats.changed, stats.deactivated) == ("success", 3, 3, 0)
    assert await count_vacancies(db_session) == 3
    passed = await db_session.scalars(
        select(Vacancy.external_id)
        .join(VacancyFilterResult, VacancyFilterResult.vacancy_id == Vacancy.id)
        .where(VacancyFilterResult.passed)
    )
    assert list(passed) == ["1"]
    first = await vacancy_by_external_id(db_session, "1")
    assert queue.details == [first.id]
    assert stats.details_queued == 1

    source = await get_source(db_session)
    assert source.last_run_status == "success"
    assert source.last_run_stats == {
        "received": 3,
        "changed": 3,
        "deactivated": 0,
        "deactivation_skipped": False,
        "details_queued": 1,
    }


async def test_repeated_run_does_not_duplicate(db_session: AsyncSession) -> None:
    adapter = FakeAdapter(pages=[[vacancy("1"), vacancy("2")]])
    await collector(db_session, adapter).collect()

    stats = await collector(db_session, adapter).collect()

    assert stats.changed == 0
    assert await count_vacancies(db_session) == 2


async def test_lost_description_tasks_are_requeued(
    db_session: AsyncSession, profile: SearchProfile
) -> None:
    """Если задачи на описание потерялись, следующий сбор поставит их снова."""
    adapter = FakeAdapter(pages=[[vacancy("1")]])
    await collector(db_session, adapter).collect()

    queue = FakeTaskQueue()
    stats = await collector(db_session, adapter, queue).collect()

    assert stats.changed == 0
    assert stats.details_queued == 1
    assert queue.details == [(await vacancy_by_external_id(db_session, "1")).id]


async def test_vacancies_with_description_are_not_requeued(
    db_session: AsyncSession, profile: SearchProfile
) -> None:
    adapter = FakeAdapter(pages=[[vacancy("1")]])
    await collector(db_session, adapter).collect()
    await db_session.execute(update(Vacancy).values(description_fetched_at=func.now()))
    await db_session.commit()

    queue = FakeTaskQueue()
    await collector(db_session, adapter, queue).collect()

    assert queue.details == []


async def test_duplicates_inside_one_run_are_merged(db_session: AsyncSession) -> None:
    adapter = FakeAdapter(pages=[[vacancy("1")], [vacancy("1", title="Python Lead")]])

    stats = await collector(db_session, adapter).collect()

    assert (stats.received, stats.changed) == (1, 1)
    assert (await vacancy_by_external_id(db_session, "1")).title == "Python Lead"


async def test_changed_vacancy_is_updated_and_description_reset(
    db_session: AsyncSession,
) -> None:
    await collector(db_session, FakeAdapter(pages=[[vacancy("1")]])).collect()
    stored = await vacancy_by_external_id(db_session, "1")
    stored.description = "старое описание"
    await db_session.commit()

    stats = await collector(
        db_session, FakeAdapter(pages=[[vacancy("1", salary_to=300_000)]])
    ).collect()

    assert stats.changed == 1
    updated = await vacancy_by_external_id(db_session, "1")
    assert updated.salary_to == 300_000
    assert updated.description is None


async def test_missing_vacancy_is_deactivated_and_comes_back(db_session: AsyncSession) -> None:
    five = [vacancy(str(i)) for i in range(5)]
    await collector(db_session, FakeAdapter(pages=[five])).collect()

    stats = await collector(db_session, FakeAdapter(pages=[five[:4]])).collect()
    assert stats.deactivated == 1
    assert not (await vacancy_by_external_id(db_session, "4")).is_active

    stats = await collector(db_session, FakeAdapter(pages=[five])).collect()
    assert stats.changed == 1
    assert (await vacancy_by_external_id(db_session, "4")).is_active


async def test_incomplete_crawl_does_not_deactivate(db_session: AsyncSession) -> None:
    ten = [vacancy(str(i)) for i in range(10)]
    await collector(db_session, FakeAdapter(pages=[ten])).collect()

    stats = await collector(db_session, FakeAdapter(pages=[ten[:5]])).collect()

    assert stats.deactivated == 0
    assert stats.deactivation_skipped
    assert await count_vacancies(db_session, active=True) == 10


async def test_empty_response_does_not_deactivate_everything(db_session: AsyncSession) -> None:
    await collector(db_session, FakeAdapter(pages=[[vacancy("1")]])).collect()

    stats = await collector(db_session, FakeAdapter(pages=[])).collect()

    assert stats.deactivated == 0
    assert await count_vacancies(db_session, active=True) == 1


async def test_source_failure_is_recorded(db_session: AsyncSession) -> None:
    adapter = FakeAdapter(
        pages=[[vacancy("1")]], error=TransientExternalError("getmatch: HTTP 503")
    )

    with pytest.raises(TransientExternalError):
        await collector(db_session, adapter).collect()

    # Частично загруженные страницы не записываются: сбор либо целиком, либо никак.
    assert await count_vacancies(db_session) == 0
    source = await get_source(db_session)
    assert (source.last_run_status, source.last_error) == ("failed", "getmatch: HTTP 503")


async def test_disabled_source_is_skipped(db_session: AsyncSession) -> None:
    source = await get_source(db_session)
    source.is_enabled = False
    await db_session.commit()

    stats = await collector(db_session, FakeAdapter(pages=[[vacancy("1")]])).collect()

    assert stats.status == "disabled"
    assert await count_vacancies(db_session) == 0


async def test_concurrent_run_is_skipped(db_session: AsyncSession, engine: AsyncEngine) -> None:
    async with engine.connect() as other:
        await other.begin()
        await other.execute(text("SELECT pg_advisory_xact_lock(hashtext('collect:getmatch'))"))

        stats = await collector(db_session, FakeAdapter(pages=[[vacancy("1")]])).collect()

    assert stats.status == "skipped"
    assert await count_vacancies(db_session) == 0

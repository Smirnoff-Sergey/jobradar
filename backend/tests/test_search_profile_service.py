from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, VacancyFilterResult
from app.domain.filtering import SearchCriteria
from app.services.search_profiles import SearchProfileService
from tests.fakes import FakeAdapter, FakeTaskQueue, collector, vacancy


async def test_new_profile_queues_refilter(db_session: AsyncSession, user: User) -> None:
    queue = FakeTaskQueue()
    service = SearchProfileService(db_session, queue)

    await service.get_or_create(user.id)
    await service.get_or_create(user.id)

    assert queue.refiltered == [user.id]


async def test_profile_created_after_collect_sees_vacancies(
    db_session: AsyncSession, user: User
) -> None:
    """Сценарий из README: сначала собрали вакансии, потом пользователь открыл профиль."""
    await collector(
        db_session, FakeAdapter(pages=[[vacancy("1"), vacancy("2", title="Go Developer")]])
    ).collect()
    queue = FakeTaskQueue()
    service = SearchProfileService(db_session, queue)
    await service.get_or_create(user.id)

    queued = await service.refilter(user.id)

    passed = await db_session.scalars(
        select(VacancyFilterResult.passed).where(VacancyFilterResult.user_id == user.id)
    )
    assert sorted(passed) == [True, True]  # профиль по умолчанию пропускает обе удалённые
    assert queued == 2
    assert len(queue.details) == 2


async def test_update_applies_new_criteria_on_refilter(
    db_session: AsyncSession, user: User
) -> None:
    await collector(
        db_session, FakeAdapter(pages=[[vacancy("1"), vacancy("2", title="Go Developer")]])
    ).collect()
    queue = FakeTaskQueue()
    service = SearchProfileService(db_session, queue)

    profile, task_id = await service.update(user.id, SearchCriteria(title_keywords=["python"]))
    await service.refilter(user.id)

    assert profile.title_keywords == ["python"]
    assert task_id == "refilter-2"  # первая перефильтрация — от создания профиля
    rejected = await db_session.scalars(
        select(VacancyFilterResult.reasons).where(VacancyFilterResult.passed.is_(False))
    )
    assert list(rejected) == [["в названии нет ключевых слов"]]


async def test_refilter_without_profile(db_session: AsyncSession, user: User) -> None:
    assert await SearchProfileService(db_session, FakeTaskQueue()).refilter(user.id) == 0

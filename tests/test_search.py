from __future__ import annotations

from app.database.repositories.users import UserRepository


async def _seed_users(session) -> None:
    repo = UserRepository(session)
    await repo.upsert_from_telegram(
        telegram_id=123456, username="ivanov", first_name="Иван", last_name="Иванов"
    )
    await repo.upsert_from_telegram(
        telegram_id=654321, username="alina_p", first_name="Алина", last_name="Петрова"
    )
    await repo.upsert_from_telegram(
        telegram_id=999999, username=None, first_name="Без", last_name="Юзернейма"
    )
    await session.commit()


async def test_search_by_first_name(session):
    await _seed_users(session)
    results = await UserRepository(session).search("Иван")
    assert any(u.telegram_id == 123456 for u in results)


async def test_search_by_last_name(session):
    await _seed_users(session)
    results = await UserRepository(session).search("Петрова")
    assert any(u.telegram_id == 654321 for u in results)


async def test_search_by_username(session):
    await _seed_users(session)
    results = await UserRepository(session).search("alina_p")
    assert any(u.telegram_id == 654321 for u in results)


async def test_search_by_telegram_id(session):
    await _seed_users(session)
    results = await UserRepository(session).search("999999")
    assert len(results) == 1
    assert results[0].telegram_id == 999999


async def test_search_no_match_returns_empty(session):
    await _seed_users(session)
    results = await UserRepository(session).search("НетТакогоЧеловека")
    assert results == []


async def test_upsert_refreshes_changed_username(session):
    repo = UserRepository(session)
    user = await repo.upsert_from_telegram(
        telegram_id=42, username="old_name", first_name="Тест", last_name=None
    )
    assert user.username == "old_name"

    updated = await repo.upsert_from_telegram(
        telegram_id=42, username="new_name", first_name="Тест", last_name=None
    )
    assert updated.id == user.id
    assert updated.username == "new_name"

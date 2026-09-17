from __future__ import annotations

from datetime import datetime, timezone

from app.database.repositories.events import EventRepository
from app.services.participants import ParticipantsService
from app.services.statistics import StatisticsService


async def _make_event(session):
    return await EventRepository(session).create(
        title="Statистика-тест",
        description=None,
        start_time=datetime(2026, 12, 1, 19, 0, tzinfo=timezone.utc),
        location="Зал",
    )


async def test_statistics_counts_and_rates(session):
    event = await _make_event(session)
    service = ParticipantsService(session)

    going_users = []
    for i in range(3):
        user = await service.get_or_create_user(
            telegram_id=1000 + i, username=None, first_name=f"Going{i}", last_name=None
        )
        reg = await service.set_decision(user=user, event_id=event.id, going=True)
        going_users.append(reg)

    for i in range(2):
        user = await service.get_or_create_user(
            telegram_id=2000 + i, username=None, first_name=f"NotGoing{i}", last_name=None
        )
        await service.set_decision(user=user, event_id=event.id, going=False)

    # Один "пришедший" из тех, кто шёл.
    await service.checkin(going_users[0])

    stats = await StatisticsService(session).get_event_statistics(event.id)

    assert stats.total == 5
    assert stats.going == 2  # один из трёх перешёл в CHECKED_IN
    assert stats.not_going == 2
    assert stats.pending == 0
    assert stats.checked_in == 1

    # confirmation_rate считает "подтвердивших" = GOING + CHECKED_IN (кто
    # пришёл, тот заведомо и подтверждал участие), поэтому здесь confirmed=3.
    assert stats.confirmed == 3
    assert stats.confirmation_rate == round(3 / 5 * 100, 1)
    # attendance_rate = доля подтвердивших, которые реально дошли (checked_in).
    assert stats.attendance_rate == round(1 / 3 * 100, 1)


async def test_statistics_empty_event_has_zero_rates(session):
    event = await _make_event(session)
    stats = await StatisticsService(session).get_event_statistics(event.id)

    assert stats.total == 0
    assert stats.confirmation_rate == 0.0
    assert stats.attendance_rate == 0.0

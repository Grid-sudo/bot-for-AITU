from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.database.models import Event, Registration, RegistrationStatus
from app.database.repositories.events import EventRepository
from app.services.participants import ParticipantsService
from app.services.participants import EventCapacityReached


async def _make_event(session) -> Event:
    return await EventRepository(session).create(
        title="Тестовый киновечер",
        description=None,
        start_time=datetime(2026, 12, 1, 19, 0, tzinfo=timezone.utc),
        location="Актовый зал",
    )


async def test_user_can_register_as_going(session):
    event = await _make_event(session)
    service = ParticipantsService(session)
    user = await service.get_or_create_user(
        telegram_id=111, username="ivan", first_name="Иван", last_name="Иванов"
    )

    registration = await service.set_decision(user=user, event_id=event.id, going=True)

    assert registration.status == RegistrationStatus.GOING
    assert registration.user_id == user.id
    assert registration.event_id == event.id


async def test_repeated_registration_does_not_duplicate(session):
    event = await _make_event(session)
    service = ParticipantsService(session)
    user = await service.get_or_create_user(
        telegram_id=222, username=None, first_name="Алина", last_name=None
    )

    await service.set_decision(user=user, event_id=event.id, going=True)
    await service.set_decision(user=user, event_id=event.id, going=True)
    await service.set_decision(user=user, event_id=event.id, going=False)

    result = await session.execute(
        select(Registration).where(Registration.user_id == user.id, Registration.event_id == event.id)
    )
    rows = result.scalars().all()

    assert len(rows) == 1
    assert rows[0].status == RegistrationStatus.NOT_GOING


async def test_user_can_change_decision(session):
    event = await _make_event(session)
    service = ParticipantsService(session)
    user = await service.get_or_create_user(telegram_id=333, username=None, first_name="Петя", last_name=None)

    await service.set_decision(user=user, event_id=event.id, going=False)
    registration = await service.get_registration(user.id, event.id)
    assert registration.status == RegistrationStatus.NOT_GOING

    await service.set_decision(user=user, event_id=event.id, going=True)
    registration = await service.get_registration(user.id, event.id)
    assert registration.status == RegistrationStatus.GOING


async def test_admin_checkin_updates_status(session):
    event = await _make_event(session)
    service = ParticipantsService(session)
    user = await service.get_or_create_user(telegram_id=444, username=None, first_name="Настя", last_name=None)

    registration = await service.set_decision(user=user, event_id=event.id, going=True)
    checked_in = await service.checkin(registration)

    assert checked_in.status == RegistrationStatus.CHECKED_IN
    assert checked_in.checked_in_at is not None


async def test_registration_deleted_by_admin(session):
    event = await _make_event(session)
    service = ParticipantsService(session)
    user = await service.get_or_create_user(telegram_id=555, username=None, first_name="Олег", last_name=None)
    registration = await service.set_decision(user=user, event_id=event.id, going=True)

    await service.delete_registration(registration)

    remaining = await service.get_registration(user.id, event.id)
    assert remaining is None


async def test_event_photo_can_be_saved(session):
    event = await EventRepository(session).create(
        title="С фоткой",
        description="Описание",
        start_time=datetime(2026, 11, 5, 18, 30, tzinfo=timezone.utc),
        location="Кинотеатр",
        photo_file_id="file_id_123",
    )

    saved = await session.get(Event, event.id)
    assert saved is not None
    assert saved.photo_file_id == "file_id_123"


async def test_event_capacity_blocks_new_registration(session):
    event = await EventRepository(session).create(
        title="С ограничением",
        description=None,
        start_time=datetime(2026, 12, 1, 19, 0, tzinfo=timezone.utc),
        location="Актовый зал",
        max_participants=1,
    )
    service = ParticipantsService(session)
    first = await service.get_or_create_user(
        telegram_id=666, username=None, first_name="Первый", last_name=None
    )
    second = await service.get_or_create_user(
        telegram_id=777, username=None, first_name="Второй", last_name=None
    )

    await service.set_decision(user=first, event_id=event.id, going=True)

    try:
        await service.set_decision(user=second, event_id=event.id, going=True)
    except EventCapacityReached:
        pass
    else:
        raise AssertionError("registration should be rejected when event capacity is full")

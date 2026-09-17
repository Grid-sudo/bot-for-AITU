"""Data-access layer for `Event` rows."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event


class EventRepository:
    """Encapsulates all SQL touching the `events` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, event_id: int) -> Event | None:
        return await self._session.get(Event, event_id)

    async def list_active(self) -> list[Event]:
        stmt = select(Event).where(Event.is_active.is_(True)).order_by(Event.start_time)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self, *, limit: int = 50, offset: int = 0) -> list[Event]:
        stmt = select(Event).order_by(Event.start_time.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        *,
        title: str,
        description: str | None,
        start_time: datetime,
        location: str,
        is_active: bool = True,
        photo_file_id: str | None = None,
        max_participants: int | None = None,
    ) -> Event:
        event = Event(
            title=title,
            description=description,
            photo_file_id=photo_file_id,
            max_participants=max_participants,
            start_time=start_time,
            location=location,
            is_active=is_active,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def update(
        self,
        event: Event,
        *,
        title: str | None = None,
        description: str | None = None,
        start_time: datetime | None = None,
        location: str | None = None,
        photo_file_id: str | None = None,
        clear_photo: bool = False,
        max_participants: int | None = None,
    ) -> Event:
        if title is not None:
            event.title = title
        if description is not None:
            event.description = description
        if start_time is not None:
            event.start_time = start_time
        if location is not None:
            event.location = location
        if photo_file_id is not None:
            event.photo_file_id = photo_file_id
        if clear_photo:
            event.photo_file_id = None
        if max_participants is not None:
            event.max_participants = max_participants
        await self._session.flush()
        return event

    async def set_active(self, event: Event, is_active: bool) -> Event:
        event.is_active = is_active
        await self._session.flush()
        return event

    async def delete(self, event: Event) -> None:
        await self._session.delete(event)
        await self._session.flush()

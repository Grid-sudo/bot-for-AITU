"""Data-access layer for `Registration` rows.

Not explicitly listed in the original spec's repository folder (which only
named `users.py` and `events.py`), but a `Registration` repository is added
here for the same reason those two exist: keeping raw SQL out of the
services/handlers layer.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Registration, RegistrationStatus, User


class RegistrationRepository:
    """Encapsulates all SQL touching the `registrations` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, registration_id: int) -> Registration | None:
        stmt = (
            select(Registration)
            .where(Registration.id == registration_id)
            .options(selectinload(Registration.user), selectinload(Registration.event))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> list[Registration]:
        """All of one user's registrations, across every event — used by the
        `/profile` handler. Eager-loads `event` since the profile view always
        needs the event's title/date/location alongside the status.
        """
        stmt = (
            select(Registration)
            .where(Registration.user_id == user_id)
            .options(selectinload(Registration.event))
            .order_by(Registration.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_user_event(self, user_id: int, event_id: int) -> Registration | None:
        stmt = select(Registration).where(
            Registration.user_id == user_id, Registration.event_id == event_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_or_update_status(
        self, *, user_id: int, event_id: int, status: RegistrationStatus
    ) -> Registration:
        """Idempotent upsert: never creates a second row for the same pair.

        Relies on the `uq_registration_user_event` unique constraint as a
        last line of defence against races; the ordinary path is a plain
        SELECT-then-UPDATE/INSERT since Telegram callbacks are effectively
        serialized per chat.
        """
        registration = await self.get_for_user_event(user_id, event_id)
        if registration is None:
            registration = Registration(user_id=user_id, event_id=event_id, status=status)
            self._session.add(registration)
        else:
            registration.status = status
        await self._session.flush()
        return registration

    async def set_status(self, registration: Registration, status: RegistrationStatus) -> Registration:
        registration.status = status
        await self._session.flush()
        return registration

    async def mark_checked_in(self, registration: Registration) -> Registration:
        from datetime import datetime, timezone

        registration.status = RegistrationStatus.CHECKED_IN
        registration.checked_in_at = datetime.now(timezone.utc)
        await self._session.flush()
        return registration

    async def delete(self, registration: Registration) -> None:
        await self._session.delete(registration)
        await self._session.flush()

    async def list_for_event(
        self,
        event_id: int,
        *,
        status: RegistrationStatus | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Registration]:
        stmt = (
            select(Registration)
            .where(Registration.event_id == event_id)
            .options(selectinload(Registration.user))
            .order_by(Registration.registered_at)
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(Registration.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search_for_event(self, event_id: int, query: str, *, limit: int = 20) -> list[Registration]:
        query = query.strip()
        like = f"%{query}%"
        conditions = [User.first_name.ilike(like), User.last_name.ilike(like), User.username.ilike(like)]
        stmt = (
            select(Registration)
            .join(User, Registration.user_id == User.id)
            .where(Registration.event_id == event_id)
            .options(selectinload(Registration.user))
            .limit(limit)
        )
        from sqlalchemy import or_

        if query.lstrip("-").isdigit():
            conditions.append(User.telegram_id == int(query))
        stmt = stmt.where(or_(*conditions))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_event(self, event_id: int, *, status: RegistrationStatus | None = None) -> int:
        stmt = select(func.count(Registration.id)).where(Registration.event_id == event_id)
        if status is not None:
            stmt = stmt.where(Registration.status == status)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def counts_by_status(self, event_id: int) -> dict[RegistrationStatus, int]:
        stmt = (
            select(Registration.status, func.count(Registration.id))
            .where(Registration.event_id == event_id)
            .group_by(Registration.status)
        )
        result = await self._session.execute(stmt)
        counts = {status: 0 for status in RegistrationStatus}
        for status, count in result.all():
            counts[status] = count
        return counts

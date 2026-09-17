"""Business logic for user registration / admin participant management.

Handlers call into this service instead of touching repositories directly,
so the "what does it mean to register someone" rule lives in exactly one
place regardless of whether it was triggered by a user tapping a button or
an admin editing a participant card.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, Registration, RegistrationStatus, User, UserStatus
from app.database.repositories.registrations import RegistrationRepository
from app.database.repositories.users import UserRepository
from app.utils.pagination import Page

logger = logging.getLogger(__name__)


class EventCapacityReached(Exception):
    """Raised when a new positive decision would exceed an event's limit."""


class ParticipantsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.users = UserRepository(session)
        self.registrations = RegistrationRepository(session)

    async def get_or_create_user(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> User:
        return await self.users.upsert_from_telegram(
            telegram_id=telegram_id, username=username, first_name=first_name, last_name=last_name
        )

    async def get_registration(self, user_id: int, event_id: int) -> Registration | None:
        return await self.registrations.get_for_user_event(user_id, event_id)

    async def set_decision(self, *, user: User, event_id: int, going: bool) -> Registration:
        """Record (or update) a user's own "Пойду"/"Не пойду" decision.

        This is idempotent by design: re-tapping the same button, or the
        user's own QR link a second time, never creates a duplicate row —
        it only (re)writes the status on the existing registration, thanks
        to the unique (user_id, event_id) constraint honoured by the
        repository's upsert.
        """
        status = RegistrationStatus.GOING if going else RegistrationStatus.NOT_GOING
        event = await self._session.get(Event, event_id)
        existing = await self.registrations.get_for_user_event(user.id, event_id)
        if going and event and event.max_participants is not None:
            is_new_positive_decision = existing is None or existing.status not in {
                RegistrationStatus.GOING,
                RegistrationStatus.CHECKED_IN,
            }
            if is_new_positive_decision:
                result = await self._session.execute(
                    select(func.count(Registration.id)).where(
                        Registration.event_id == event_id,
                        Registration.status.in_((RegistrationStatus.GOING, RegistrationStatus.CHECKED_IN)),
                    )
                )
                if result.scalar_one() >= event.max_participants:
                    raise EventCapacityReached
        registration = await self.registrations.create_or_update_status(
            user_id=user.id, event_id=event_id, status=status
        )
        # Mirror the decision onto the cached User.status (CHECKED_IN has no
        # UserStatus equivalent, so GOING is the closest accurate summary).
        user.status = UserStatus.GOING if going else UserStatus.NOT_GOING
        logger.info(
            "user %s set decision %s for event %s", user.telegram_id, status.value, event_id
        )
        return registration

    async def admin_set_status(self, registration: Registration, status: RegistrationStatus) -> Registration:
        updated = await self.registrations.set_status(registration, status)
        logger.info(
            "admin set registration %s (event %s) to %s",
            registration.id,
            registration.event_id,
            status.value,
        )
        return updated

    async def checkin(self, registration: Registration) -> Registration:
        updated = await self.registrations.mark_checked_in(registration)
        logger.info("registration %s checked in", registration.id)
        return updated

    async def delete_registration(self, registration: Registration) -> None:
        logger.info("registration %s deleted by admin", registration.id)
        await self.registrations.delete(registration)

    async def list_participants(
        self,
        *,
        event_id: int,
        status_filter: str,
        page_number: int,
        page_size: int,
    ) -> tuple[list[Registration], Page]:
        status = None if status_filter == "ALL" else RegistrationStatus(status_filter)
        total = await self.registrations.count_for_event(event_id, status=status)
        page = Page(page=page_number, page_size=page_size, total_items=total).clamped
        items = await self.registrations.list_for_event(
            event_id, status=status, limit=page.page_size, offset=page.offset
        )
        return items, page

    async def search_participants(self, *, event_id: int, query: str) -> list[Registration]:
        return await self.registrations.search_for_event(event_id, query)

    async def counts_by_status(self, event_id: int) -> dict[RegistrationStatus, int]:
        return await self.registrations.counts_by_status(event_id)

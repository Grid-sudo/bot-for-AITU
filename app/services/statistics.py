"""Aggregated statistics for a single event."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import RegistrationStatus
from app.database.repositories.registrations import RegistrationRepository


@dataclass(frozen=True, slots=True)
class EventStatistics:
    total: int
    going: int
    not_going: int
    pending: int
    checked_in: int

    @property
    def confirmed(self) -> int:
        """Everyone who said "Пойду" at some point — including those who
        have since checked in. `checked_in` is a *subset* of "confirmed",
        not a separate population, since a person can only check in after
        first confirming they were coming.
        """
        return self.going + self.checked_in

    @property
    def confirmation_rate(self) -> float:
        """% of everyone with a registration row who confirmed "Пойду"
        (whether or not they have checked in yet)."""
        if self.total == 0:
            return 0.0
        return round(self.confirmed / self.total * 100, 1)

    @property
    def attendance_rate(self) -> float:
        """% of those who confirmed "Пойду" who actually checked in."""
        if self.confirmed == 0:
            return 0.0
        return round(self.checked_in / self.confirmed * 100, 1)


class StatisticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._registrations = RegistrationRepository(session)

    async def get_event_statistics(self, event_id: int) -> EventStatistics:
        counts = await self._registrations.counts_by_status(event_id)
        total = sum(counts.values())
        return EventStatistics(
            total=total,
            going=counts[RegistrationStatus.GOING],
            not_going=counts[RegistrationStatus.NOT_GOING],
            pending=counts[RegistrationStatus.PENDING],
            checked_in=counts[RegistrationStatus.CHECKED_IN],
        )

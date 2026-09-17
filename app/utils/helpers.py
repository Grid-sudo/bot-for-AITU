"""Small formatting / mapping helpers shared across handlers and services."""
from __future__ import annotations

from datetime import datetime

from app.database.models import RegistrationStatus

STATUS_EMOJI: dict[RegistrationStatus, str] = {
    RegistrationStatus.PENDING: "⏳",
    RegistrationStatus.GOING: "✅",
    RegistrationStatus.NOT_GOING: "❌",
    RegistrationStatus.CHECKED_IN: "🎟",
}

STATUS_LABEL_RU: dict[RegistrationStatus, str] = {
    RegistrationStatus.PENDING: "Не ответил(а)",
    RegistrationStatus.GOING: "Иду",
    RegistrationStatus.NOT_GOING: "Не иду",
    RegistrationStatus.CHECKED_IN: "Пришёл(а)",
}


def status_display(status: RegistrationStatus) -> str:
    """Return "✅ Иду"-style combined emoji+label for a status."""
    return f"{STATUS_EMOJI[status]} {STATUS_LABEL_RU[status]}"


def format_datetime(value: datetime) -> str:
    return value.strftime("%d.%m.%Y %H:%M")


def format_date(value: datetime) -> str:
    return value.strftime("%d.%m.%Y")


def format_time(value: datetime) -> str:
    return value.strftime("%H:%M")


def user_display_name(*, first_name: str | None, last_name: str | None, username: str | None) -> str:
    parts = [p for p in (first_name, last_name) if p]
    name = " ".join(parts)
    return name or (f"@{username}" if username else "Без имени")


def deep_link(bot_username: str, event_id: int) -> str:
    return f"https://t.me/{bot_username}?start=event_{event_id}"


def parse_event_deep_link(payload: str) -> int | None:
    """Parse the `/start` payload of the form `event_123` into an event id."""
    if not payload:
        return None
    prefix = "event_"
    if not payload.startswith(prefix):
        return None
    tail = payload[len(prefix) :]
    return int(tail) if tail.isdigit() else None

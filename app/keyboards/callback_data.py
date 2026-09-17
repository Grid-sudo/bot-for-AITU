"""Structured callback data factories.

Using `aiogram.filters.callback_data.CallbackData` instead of hand-rolled
string parsing gives us type validation for free: aiogram rejects malformed
payloads before they ever reach a handler, so handlers can trust the parsed
object instead of re-validating `callback_data` strings themselves.
"""
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class EventDecision(CallbackData, prefix="event"):
    """event:join:123 / event:decline:123 / event:change:123"""

    action: str  # "join" | "decline" | "change"
    event_id: int


class LanguageChoice(CallbackData, prefix="language"):
    language: str  # "kk" | "ru" | "en"
    event_id: int = 0


class AdminMenu(CallbackData, prefix="adminmenu"):
    """Top-level admin panel navigation, e.g. adminmenu:events"""

    section: str  # "events" | "participants" | "stats" | "broadcast" | "root"


class AdminEvent(CallbackData, prefix="adminevent"):
    """admin:event:123 style actions on a single event."""

    action: str  # "open" | "edit" | "delete" | "activate" | "deactivate" | "qr" | "list" | "create"
    event_id: int = 0


class AdminEventPicker(CallbackData, prefix="eventpicker"):
    """Used when a cross-section admin action (stats / broadcast) needs the
    admin to first pick *which* event it applies to.
    """

    purpose: str  # "stats" | "broadcast" | "participants"
    event_id: int


class AdminEventEditField(CallbackData, prefix="admineventfield"):
    """Which field of an event is being edited (drives the FSM)."""

    field: str  # "title" | "description" | "date" | "time" | "location" | "photo"
    event_id: int


class AdminParticipants(CallbackData, prefix="adminpart"):
    """admin:participants:123 with an optional status filter + page."""

    action: str  # "list" | "search" | "export" | "menu"
    event_id: int
    status_filter: str = "ALL"  # "ALL" | "GOING" | "NOT_GOING" | "PENDING" | "CHECKED_IN"
    page: int = 0


class ParticipantCard(CallbackData, prefix="participant"):
    """participant:123 style actions on a single registration."""

    action: str  # "open" | "set_going" | "set_declined" | "delete" | "checkin" | "message"
    registration_id: int
    event_id: int = 0
    page: int = 0
    status_filter: str = "ALL"


class ExportFormat(CallbackData, prefix="export"):
    fmt: str  # "csv" | "xlsx"
    event_id: int


class BroadcastTarget(CallbackData, prefix="broadcast_target"):
    target: str  # "all" | "going" | "checked_in"


class BroadcastConfirm(CallbackData, prefix="broadcast_confirm"):
    confirm: bool

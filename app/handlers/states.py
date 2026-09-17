"""FSM state groups used by admin multi-step flows."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CreateEvent(StatesGroup):
    """Sequential prompts for creating a new event."""

    title = State()
    description = State()
    date = State()
    time = State()
    location = State()
    photo = State()
    max_participants = State()


class EditEvent(StatesGroup):
    """A single free-text prompt; which field it edits is stored in FSM data."""

    value = State()


class SearchParticipant(StatesGroup):
    query = State()


class MessageParticipant(StatesGroup):
    """Admin composing a direct message to one participant."""

    text = State()


class Broadcast(StatesGroup):
    message = State()
    confirm = State()

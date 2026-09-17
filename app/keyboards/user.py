"""Inline keyboards shown to ordinary (non-admin) users."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.callback_data import EventDecision, LanguageChoice


def language_keyboard(event_id: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Қазақша", callback_data=LanguageChoice(language="kk", event_id=event_id))
    builder.button(text="Русский", callback_data=LanguageChoice(language="ru", event_id=event_id))
    builder.button(text="English", callback_data=LanguageChoice(language="en", event_id=event_id))
    builder.adjust(3)
    return builder.as_markup()


def event_decision_keyboard(event_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    """Initial "Пойду / Не пойду" choice, shown before any decision exists."""
    builder = InlineKeyboardBuilder()
    labels = {"kk": ("✅ Барамын", "❌ Бармаймын"), "en": ("✅ I will go", "❌ I won't go")}
    going, declining = labels.get(language, ("✅ Пойду", "❌ Не пойду"))
    builder.button(text=going, callback_data=EventDecision(action="join", event_id=event_id))
    builder.button(text=declining, callback_data=EventDecision(action="decline", event_id=event_id))
    builder.adjust(2)
    return builder.as_markup()


def change_decision_keyboard(event_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    """Shown once a decision is already recorded, so the user can flip it."""
    builder = InlineKeyboardBuilder()
    labels = {"kk": "🔄 Шешімді өзгерту", "en": "🔄 Change decision"}
    builder.button(text=labels.get(language, "🔄 Изменить решение"), callback_data=EventDecision(action="change", event_id=event_id))
    builder.adjust(1)
    return builder.as_markup()


def events_list_keyboard(events: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """Shown when several active events exist and the user must pick one.

    `events` is a list of (event_id, title) tuples.
    """
    builder = InlineKeyboardBuilder()
    for event_id, title in events:
        builder.button(text=f"🎬 {title}", callback_data=EventDecision(action="view", event_id=event_id))
    builder.adjust(1)
    return builder.as_markup()


def profile_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👤 Моя регистрация", callback_data="profile:open")]]
    )

"""`/profile` (👤 Моя регистрация) — shows the user's own registration status."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.registrations import RegistrationRepository
from app.database.repositories.users import UserRepository
from app.keyboards.user import change_decision_keyboard
from app.utils.helpers import format_date, format_time, status_display

router = Router(name="profile")


PROFILE_TEXT = {
    "ru": ("👤 Моя регистрация", "Дата", "Время", "Место", "Статус", "У тебя пока нет регистраций ни на одно мероприятие. Найди активный киновечер через /start."),
    "kk": ("👤 Менің тіркелуім", "Күні", "Уақыты", "Өтетін орны", "Мәртебесі", "Сізде әзірге тіркелу жоқ. Белсенді кино кешін /start арқылы табыңыз."),
    "en": ("👤 My registration", "Date", "Time", "Location", "Status", "You have no registrations yet. Find an active movie night with /start."),
}

STATUS_TEXT = {
    "ru": {"GOING": "Иду", "NOT_GOING": "Не иду", "PENDING": "Нет решения", "CHECKED_IN": "Пришёл"},
    "kk": {"GOING": "Барамын", "NOT_GOING": "Бармаймын", "PENDING": "Шешім жоқ", "CHECKED_IN": "Келді"},
    "en": {"GOING": "Going", "NOT_GOING": "Not going", "PENDING": "No decision", "CHECKED_IN": "Checked in"},
}


async def _render_profile(session: AsyncSession, telegram_id: int) -> tuple[str, object | None, str]:
    users = UserRepository(session)
    user = await users.get_by_telegram_id(telegram_id)
    language = user.language if user and user.language in PROFILE_TEXT else "ru"
    labels = PROFILE_TEXT[language]
    if user is None:
        return labels[5], None, language

    # Explicitly (eager-)loaded, rather than lazy-accessing `user.registrations`,
    # which would trigger an implicit sync-style lazy load on an AsyncSession.
    registrations = await RegistrationRepository(session).list_for_user(user.id)
    if not registrations:
        return labels[5], None, language

    latest = registrations[0]  # already ordered by updated_at desc
    event = latest.event

    text = (
        f"{labels[0]}\n\n"
        f"🎬 {event.title}\n"
        f"📅 {labels[1]}: {format_date(event.start_time)}\n"
        f"🕐 {labels[2]}: {format_time(event.start_time)}\n"
        f"📍 {labels[3]}: {event.location}\n\n"
        f"{labels[4]}: {STATUS_TEXT[language].get(latest.status.value, status_display(latest.status))}"
    )
    return text, latest, language


@router.message(Command("profile"))
async def profile_command(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    text, registration, language = await _render_profile(session, message.from_user.id)
    markup = change_decision_keyboard(registration.event_id, language) if registration else None
    await message.answer(text, reply_markup=markup)


@router.callback_query(lambda c: c.data == "profile:open")
async def profile_button(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None:
        return
    text, registration, language = await _render_profile(session, callback.from_user.id)
    markup = change_decision_keyboard(registration.event_id, language) if registration else None
    await callback.message.answer(text, reply_markup=markup)
    await callback.answer()

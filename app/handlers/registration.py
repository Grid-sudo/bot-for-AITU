"""Handlers for the ✅ Пойду / ❌ Не пойду / 🔄 Изменить решение callbacks."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.events import EventRepository
from app.keyboards.callback_data import EventDecision
from app.keyboards.user import change_decision_keyboard, event_decision_keyboard
from app.services.participants import ParticipantsService
from app.services.participants import EventCapacityReached
from app.utils.helpers import format_date, format_time

logger = logging.getLogger(__name__)
router = Router(name="registration")


MESSAGES = {
    "ru": {
        "joined": "🎉 Отлично!\n\nТы зарегистрирован(а) на киновечер.",
        "wait": "Ждём тебя!",
        "declined": "Хорошо, мы записали твой ответ.\n\nЕсли передумаешь, ты сможешь изменить решение.",
        "confirmed": "Регистрация подтверждена ✅",
        "saved": "Ответ сохранён",
        "full": "К сожалению, все места уже заняты.",
        "choose": "Выбери новый вариант:",
    },
    "kk": {
        "joined": "🎉 Керемет!\n\nСіз кино кешіне тіркелдіңіз.",
        "wait": "Сізді күтеміз!",
        "declined": "Жауабыңыз сақталды.\n\nОйыңызды өзгерте аласыз.",
        "confirmed": "Тіркелу расталды ✅",
        "saved": "Жауап сақталды",
        "full": "Өкінішке қарай, барлық орын бос емес.",
        "choose": "Жаңа нұсқаны таңдаңыз:",
    },
    "en": {
        "joined": "🎉 Great!\n\nYou are registered for the movie night.",
        "wait": "We are looking forward to seeing you!",
        "declined": "Your answer has been saved.\n\nYou can change your decision later.",
        "confirmed": "Registration confirmed ✅",
        "saved": "Answer saved",
        "full": "Unfortunately, all places are already taken.",
        "choose": "Choose a new option:",
    },
}


def _messages(language: str) -> dict[str, str]:
    return MESSAGES.get(language, MESSAGES["ru"])


async def _safe_callback_answer(callback: CallbackQuery, *args, **kwargs) -> None:
    try:
        await callback.answer(*args, **kwargs)
    except TelegramBadRequest:
        pass


async def _safe_edit_or_answer(callback: CallbackQuery, text: str, *, reply_markup=None) -> None:
    message = callback.message
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return
    except TelegramBadRequest as exc:
        if "there is no text in the message to edit" not in str(exc) and "message to edit" not in str(exc):
            raise

    if message.photo or getattr(message, "caption", None) is not None:
        try:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
            return
        except TelegramBadRequest:
            pass

    await message.answer(text, reply_markup=reply_markup)


async def _load_active_event(session: AsyncSession, event_id: int, callback: CallbackQuery):
    events = EventRepository(session)
    event = await events.get_by_id(event_id)
    if event is None:
        await _safe_callback_answer(callback, "Это мероприятие больше не существует.", show_alert=True)
        return None
    if not event.is_active:
        await _safe_callback_answer(callback, "Это мероприятие сейчас неактивно.", show_alert=True)
        return None
    return event


@router.callback_query(EventDecision.filter(F.action == "join"))
async def join_event(callback: CallbackQuery, callback_data: EventDecision, session: AsyncSession) -> None:
    event = await _load_active_event(session, callback_data.event_id, callback)
    if event is None:
        return

    service = ParticipantsService(session)
    tg_user = callback.from_user
    user = await service.get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )
    language = user.language or "ru"
    messages = _messages(language)
    try:
        await service.set_decision(user=user, event_id=event.id, going=True)
    except EventCapacityReached:
        await _safe_callback_answer(callback, messages["full"], show_alert=True)
        return

    text = (
        f"{messages['joined']}\n\n"
        f"📅 {format_date(event.start_time)}\n"
        f"🕐 {format_time(event.start_time)}\n"
        f"📍 {event.location}\n\n"
        f"{messages['wait']}"
    )
    await _safe_edit_or_answer(callback, text, reply_markup=change_decision_keyboard(event.id, language))
    await _safe_callback_answer(callback, messages["confirmed"])


@router.callback_query(EventDecision.filter(F.action == "decline"))
async def decline_event(callback: CallbackQuery, callback_data: EventDecision, session: AsyncSession) -> None:
    event = await _load_active_event(session, callback_data.event_id, callback)
    if event is None:
        return

    service = ParticipantsService(session)
    tg_user = callback.from_user
    user = await service.get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )
    language = user.language or "ru"
    messages = _messages(language)
    await service.set_decision(user=user, event_id=event.id, going=False)

    await _safe_edit_or_answer(callback, messages["declined"], reply_markup=change_decision_keyboard(event.id, language))
    await _safe_callback_answer(callback, messages["saved"])


@router.callback_query(EventDecision.filter(F.action == "change"))
async def change_decision(callback: CallbackQuery, callback_data: EventDecision, session: AsyncSession) -> None:
    event = await _load_active_event(session, callback_data.event_id, callback)
    if event is None:
        return

    service = ParticipantsService(session)
    tg_user = callback.from_user
    user = await service.get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )
    language = user.language or "ru"
    messages = _messages(language)
    text = (
        "🎬 Movie night\n\n" if language == "en" else "🎬 Кино кеші\n\n" if language == "kk" else "🎬 Киновечер\n\n"
    ) + (
        f"Название: {event.title}\n"
        f"📅 Дата: {format_date(event.start_time)}\n"
        f"🕐 Время: {format_time(event.start_time)}\n"
        f"📍 Место: {event.location}\n\n"
        f"{messages['choose']}"
    )
    await _safe_edit_or_answer(callback, text, reply_markup=event_decision_keyboard(event.id, language))
    await _safe_callback_answer(callback)

"""`/start` entry point: QR deep links land here, as does a bare `/start`."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, RegistrationStatus, User
from app.database.repositories.events import EventRepository
from app.database.repositories.users import UserRepository
from app.keyboards.callback_data import AdminMenu, EventDecision, LanguageChoice
from app.keyboards.user import (
    change_decision_keyboard,
    event_decision_keyboard,
    events_list_keyboard,
    language_keyboard,
)
from app.services.participants import ParticipantsService
from app.utils.helpers import (
    format_date,
    format_time,
    parse_event_deep_link,
    status_display,
)

logger = logging.getLogger(__name__)
router = Router(name="start")


def _event_card_text(
    event: Event, *, intro: str = "🎬 Киновечер", going_count: int = 0, language: str = "ru"
) -> str:
    labels = {
        "kk": ("🎬 Кино кеші", "Атауы", "Қатысушылар", "Күні", "Уақыты", "Өтетін орны", "Қатысасыз ба?"),
        "en": ("🎬 Movie night", "Title", "Going", "Date", "Time", "Location", "Will you participate?"),
    }
    intro, title_label, going_label, date_label, time_label, location_label, question = labels.get(
        language, (intro, "Название", "Участников идут", "Дата", "Время", "Место", "Будешь участвовать?")
    )
    description = f"\n{event.description}\n" if event.description else ""
    participants_line = (
        f"👥 {going_label}: {going_count} / {event.max_participants}"
        if event.max_participants
        else f"👥 {going_label}: {going_count}"
    )
    return (
        f"{intro}\n\n"
        f"{title_label}: {event.title}\n"
        f"{participants_line}\n\n"
        f"{description}"
        f"📅 {date_label}: {format_date(event.start_time)}\n"
        f"🕐 {time_label}: {format_time(event.start_time)}\n"
        f"📍 {location_label}: {event.location}\n\n"
        f"{question}"
    )


def _fit_photo_caption(text: str) -> str:
    if len(text) <= 1024:
        return text
    return text[:1000].rstrip() + "..."


async def _send_event_card(message: Message, event: Event, *, text: str, reply_markup) -> None:
    if event.photo_file_id:
        await message.answer_photo(
            photo=event.photo_file_id,
            caption=_fit_photo_caption(text),
            reply_markup=reply_markup,
        )
        return
    await message.answer(text, reply_markup=reply_markup)


async def _send_admin_button_if_admin(message: Message, is_admin: bool) -> None:
    """A tiny nudge so admins don't need to remember the `/admin` command,
    without cluttering the plain student experience.
    """
    if not is_admin:
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="⚙️ Админ-панель", callback_data=AdminMenu(section="root"))
    await message.answer("Вы вошли как администратор.", reply_markup=builder.as_markup())


def _language_prompt(language: str = "ru") -> str:
    return {
        "kk": "Тілді таңдаңыз:",
        "en": "Choose your language:",
        "ru": "Выберите язык:",
    }[language]


async def _ask_language(message: Message, event_id: int = 0) -> None:
    await message.answer(_language_prompt(), reply_markup=language_keyboard(event_id))


async def _show_event_with_decision(message: Message, user: User, event: Event, service: ParticipantsService) -> None:
    language = user.language or "ru"
    existing = await service.get_registration(user.id, event.id)
    counts = await service.counts_by_status(event.id)
    going_count = counts.get(RegistrationStatus.GOING, 0) + counts.get(RegistrationStatus.CHECKED_IN, 0)
    if existing is not None and existing.status != RegistrationStatus.PENDING:
        text = (
            f"{_event_card_text(event, going_count=going_count, language=language)}\n\n"
            f"Ты уже зарегистрирован(а).\n"
            f"Текущий статус: {status_display(existing.status)}"
        )
        await _send_event_card(
            message,
            event,
            text=text,
            reply_markup=change_decision_keyboard(event.id, language),
        )
        return

    await _send_event_card(
        message,
        event,
        text=_event_card_text(event, going_count=going_count, language=language),
        reply_markup=event_decision_keyboard(event.id, language),
    )


@router.message(CommandStart(deep_link=True))
async def start_with_deep_link(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    settings: Settings,
    is_admin: bool,
) -> None:
    tg_user = message.from_user
    if tg_user is None:
        return

    service = ParticipantsService(session)
    user = await service.get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )

    event_id = parse_event_deep_link(command.args or "")
    if event_id is None:
        logger.warning("received malformed start payload %r from %s", command.args, tg_user.id)
        await message.answer("Ссылка недействительна. Попробуйте отсканировать QR-код ещё раз.")
        await _send_admin_button_if_admin(message, is_admin)
        return

    if user.language is None:
        await _ask_language(message, event_id)
        return

    events = EventRepository(session)
    event = await events.get_by_id(event_id)

    if event is None:
        await message.answer("Это мероприятие больше не существует.")
        await _send_admin_button_if_admin(message, is_admin)
        return

    if not event.is_active:
        await message.answer(
            f"«{event.title}» сейчас неактивно. Свяжитесь с организаторами, если это ошибка."
        )
        await _send_admin_button_if_admin(message, is_admin)
        return

    await _show_event_with_decision(message, user, event, service)
    await _send_admin_button_if_admin(message, is_admin)


@router.message(CommandStart())
async def start_plain(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    is_admin: bool,
) -> None:
    tg_user = message.from_user
    if tg_user is None:
        return

    service = ParticipantsService(session)
    user = await service.get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )

    if user.language is None:
        await _ask_language(message)
        return

    events = EventRepository(session)
    active_events = await events.list_active()
    language = user.language or "ru"

    if not active_events:
        empty_text = {
            "kk": "🎬 Қазір белсенді кино кештері жоқ.\n\nКейінірек кіріп көріңіз!",
            "en": "🎬 There are no active movie nights right now.\n\nPlease check back later!",
        }.get(language, "🎬 Сейчас нет активных киновечеров.\n\nЗагляни попозже — организаторы скоро всё объявят!")
        await message.answer(empty_text)
        await _send_admin_button_if_admin(message, is_admin)
        return

    if len(active_events) == 1:
        await _show_event_with_decision(message, user, active_events[0], service)
    else:
        list_text = {
            "kk": "🎬 Бірнеше кино кеші өтіп жатыр.\nҚайсысы туралы білгіңіз келеді?",
            "en": "🎬 Several movie nights are active.\nChoose one to learn more:",
        }.get(language, "🎬 Сейчас проходит несколько киновечеров.\nВыбери, о каком хочешь узнать подробнее:")
        await message.answer(list_text, reply_markup=events_list_keyboard([(e.id, e.title) for e in active_events]))

    await _send_admin_button_if_admin(message, is_admin)


@router.callback_query(LanguageChoice.filter())
async def choose_language(
    callback, callback_data: LanguageChoice, session: AsyncSession, is_admin: bool
) -> None:
    tg_user = callback.from_user
    if tg_user is None:
        return
    service = ParticipantsService(session)
    user = await service.get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )
    await UserRepository(session).set_language(user, callback_data.language)
    await callback.answer("Язык сохранён ✅")

    if callback_data.event_id:
        event = await EventRepository(session).get_by_id(callback_data.event_id)
        if event is not None and event.is_active:
            await _show_event_with_decision(callback.message, user, event, service)
            await _send_admin_button_if_admin(callback.message, is_admin)
            return

    active_events = await EventRepository(session).list_active()
    if not active_events:
        await callback.message.answer("🎬 Сейчас нет активных киновечеров.")
    elif len(active_events) == 1:
        await _show_event_with_decision(callback.message, user, active_events[0], service)
    else:
        await callback.message.answer(
            "🎬 Выберите мероприятие:",
            reply_markup=events_list_keyboard([(event.id, event.title) for event in active_events]),
        )
    await _send_admin_button_if_admin(callback.message, is_admin)


@router.callback_query(EventDecision.filter(F.action == "view"))
async def view_event_from_list(
    callback,
    callback_data: EventDecision,
    session: AsyncSession,
) -> None:
    """User tapped one event out of a multi-event list."""
    events = EventRepository(session)
    event = await events.get_by_id(callback_data.event_id)
    if event is None or not event.is_active:
        await callback.answer("Это мероприятие недоступно.", show_alert=True)
        return

    service = ParticipantsService(session)
    tg_user = callback.from_user
    user = await service.get_or_create_user(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )
    await _show_event_with_decision(callback.message, user, event, service)
    await callback.answer()

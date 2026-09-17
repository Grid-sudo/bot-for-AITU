"""The in-bot admin panel: events, participants, statistics, broadcast.

Every handler in this router is reached only after `AdminAccessGuard`
(registered on this router in `bot.py`) has confirmed `is_admin` — see
`app/middlewares/admin.py`. Handlers below still never trust the *content*
of incoming callback_data beyond what aiogram's `CallbackData` parsing
already validated (e.g. an `event_id` that no longer exists is handled
gracefully, never assumed valid).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.models import Event, RegistrationStatus
from app.database.repositories.events import EventRepository
from app.database.repositories.registrations import RegistrationRepository
from app.handlers.states import Broadcast, CreateEvent, EditEvent, MessageParticipant, SearchParticipant
from app.keyboards.admin import (
    admin_events_menu,
    admin_main_menu,
    admin_participants_menu,
    back_to_admin_menu_button,
    broadcast_confirm_keyboard,
    broadcast_target_keyboard,
    event_actions_keyboard,
    event_delete_confirm_keyboard,
    event_picker_keyboard,
    events_list_keyboard,
    export_format_keyboard,
    participant_card_keyboard,
    participants_list_keyboard,
)
from app.keyboards.callback_data import (
    AdminEvent,
    AdminEventEditField,
    AdminEventPicker,
    AdminMenu,
    AdminParticipants,
    BroadcastConfirm,
    BroadcastTarget,
    ExportFormat,
    ParticipantCard,
)
from app.services.export import build_csv, build_xlsx
from app.services.participants import ParticipantsService
from app.services.qr import build_qr_png
from app.services.statistics import StatisticsService
from app.utils.helpers import (
    deep_link,
    format_date,
    format_datetime,
    format_time,
    status_display,
    user_display_name,
)
from app.utils.pagination import Page

logger = logging.getLogger(__name__)
router = Router(name="admin")

ADMIN_MENU_TEXT = "⚙️ Админ-панель\n\nВыберите раздел:"

EDIT_FIELD_LABELS = {
    "title": "Название",
    "description": "Описание",
    "date": "Дату",
    "time": "Время",
    "location": "Место",
    "photo": "Фото",
}


# --------------------------------------------------------------------------- #
# Root menu
# --------------------------------------------------------------------------- #


@router.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(ADMIN_MENU_TEXT, reply_markup=admin_main_menu())


@router.callback_query(AdminMenu.filter(F.section == "root"))
async def admin_root(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _safe_edit_or_answer(callback, ADMIN_MENU_TEXT, reply_markup=admin_main_menu())
    await _safe_callback_answer(callback)


@router.callback_query(AdminMenu.filter(F.section == "events"))
async def admin_events_section(callback: CallbackQuery) -> None:
    await _safe_edit_or_answer(callback, "🎬 Мероприятия", reply_markup=admin_events_menu())
    await _safe_callback_answer(callback)


@router.callback_query(AdminMenu.filter(F.section.in_({"participants", "stats", "broadcast"})))
async def admin_pick_event_for_section(
    callback: CallbackQuery, callback_data: AdminMenu, session: AsyncSession
) -> None:
    events = await EventRepository(session).list_all()
    if not events:
        await _safe_edit_or_answer(
            callback,
            "Пока нет ни одного мероприятия. Сначала создайте его в разделе «🎬 Мероприятия».",
            reply_markup=back_to_admin_menu_button(),
        )
        await _safe_callback_answer(callback)
        return

    labels = {"participants": "👥 Участники", "stats": "📊 Статистика", "broadcast": "📢 Рассылка"}
    await _safe_edit_or_answer(
        callback,
        f"{labels[callback_data.section]}\n\nВыберите мероприятие:",
        reply_markup=event_picker_keyboard(events, purpose=callback_data.section),
    )
    await _safe_callback_answer(callback)


# --------------------------------------------------------------------------- #
# Events: list / view / activate / delete
# --------------------------------------------------------------------------- #


def _event_card_text(event: Event, *, going_count: int = 0) -> str:
    description = f"\n{event.description}\n" if event.description else ""
    state_label = "🟢 Активно" if event.is_active else "🔴 Неактивно"
    participants_line = (
        f"👥 Идут: {going_count} / {event.max_participants}"
        if event.max_participants
        else f"👥 Идут: {going_count}"
    )
    return (
        f"🎬 {event.title}\n"
        f"{participants_line}\n"
        f"{description}\n"
        f"📅 Дата: {format_date(event.start_time)}\n"
        f"🕐 Время: {format_time(event.start_time)}\n"
        f"📍 Место: {event.location}\n"
        f"Статус: {state_label}\n"
        f"ID: {event.id}"
    )


async def _event_card_text_with_counts(session: AsyncSession, event: Event) -> str:
    counts = await ParticipantsService(session).counts_by_status(event.id)
    going_count = counts.get(RegistrationStatus.GOING, 0) + counts.get(RegistrationStatus.CHECKED_IN, 0)
    return _event_card_text(event, going_count=going_count)


def _fit_photo_caption(text: str) -> str:
    if len(text) <= 1024:
        return text
    return text[:1000].rstrip() + "..."


async def _answer_event_card(message: Message, event: Event, text: str) -> None:
    if event.photo_file_id:
        await message.answer_photo(
            photo=event.photo_file_id,
            caption=_fit_photo_caption(text),
            reply_markup=event_actions_keyboard(event),
        )
        return
    await message.answer(text, reply_markup=event_actions_keyboard(event))


async def _safe_edit_or_answer(
    callback: CallbackQuery,
    text: str,
    *,
    reply_markup=None,
    is_caption: bool = False,
) -> None:
    message = callback.message
    try:
        if is_caption:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
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


async def _safe_callback_answer(callback: CallbackQuery, *args, **kwargs) -> None:
    try:
        await callback.answer(*args, **kwargs)
    except TelegramBadRequest:
        pass


@router.callback_query(AdminEvent.filter(F.action == "list"))
async def admin_events_list(callback: CallbackQuery, session: AsyncSession) -> None:
    events = await EventRepository(session).list_all()
    if not events:
        await _safe_edit_or_answer(callback, "Мероприятий пока нет.", reply_markup=admin_events_menu())
        await _safe_callback_answer(callback)
        return
    await _safe_edit_or_answer(callback, "📋 Мероприятия:", reply_markup=events_list_keyboard(events))
    await _safe_callback_answer(callback)


@router.callback_query(AdminEvent.filter(F.action == "open"))
async def admin_event_open(callback: CallbackQuery, callback_data: AdminEvent, session: AsyncSession) -> None:
    event = await EventRepository(session).get_by_id(callback_data.event_id)
    if event is None:
        await _safe_callback_answer(callback, "Мероприятие не найдено — возможно, оно уже удалено.", show_alert=True)
        return
    text = await _event_card_text_with_counts(session, event)
    await _safe_edit_or_answer(callback, text, reply_markup=event_actions_keyboard(event))
    await _safe_callback_answer(callback)


@router.callback_query(AdminEvent.filter(F.action.in_({"activate", "deactivate"})))
async def admin_event_toggle_active(
    callback: CallbackQuery, callback_data: AdminEvent, session: AsyncSession
) -> None:
    events = EventRepository(session)
    event = await events.get_by_id(callback_data.event_id)
    if event is None:
        await _safe_callback_answer(callback, "Мероприятие не найдено.", show_alert=True)
        return
    await events.set_active(event, callback_data.action == "activate")
    logger.info("event %s active=%s (admin %s)", event.id, event.is_active, callback.from_user.id)
    text = await _event_card_text_with_counts(session, event)
    await _safe_edit_or_answer(callback, text, reply_markup=event_actions_keyboard(event))
    await _safe_callback_answer(callback, "Статус обновлён")


@router.callback_query(AdminEvent.filter(F.action == "delete"))
async def admin_event_delete_prompt(callback: CallbackQuery, callback_data: AdminEvent) -> None:
    await _safe_edit_or_answer(
        callback,
        "Удалить это мероприятие вместе со всеми регистрациями? Это необратимо.",
        reply_markup=event_delete_confirm_keyboard(callback_data.event_id),
    )
    await _safe_callback_answer(callback)


@router.callback_query(AdminEvent.filter(F.action == "delete_confirm"))
async def admin_event_delete_confirm(
    callback: CallbackQuery, callback_data: AdminEvent, session: AsyncSession
) -> None:
    events = EventRepository(session)
    event = await events.get_by_id(callback_data.event_id)
    if event is None:
        await _safe_callback_answer(callback, "Мероприятие уже удалено.", show_alert=True)
        return
    await events.delete(event)
    logger.info("event %s deleted by admin %s", callback_data.event_id, callback.from_user.id)
    await _safe_edit_or_answer(callback, "Мероприятие удалено.", reply_markup=admin_events_menu())
    await _safe_callback_answer(callback)


@router.callback_query(AdminEvent.filter(F.action == "qr"))
async def admin_event_qr(
    callback: CallbackQuery, callback_data: AdminEvent, session: AsyncSession, settings: Settings, bot: Bot
) -> None:
    event = await EventRepository(session).get_by_id(callback_data.event_id)
    if event is None:
        await _safe_callback_answer(callback, "Мероприятие не найдено.", show_alert=True)
        return
    if not settings.bot_username:
        await _safe_callback_answer(
            callback,
            "Не задан BOT_USERNAME в .env — ссылка не может быть сформирована.", show_alert=True
        )
        return

    link = deep_link(settings.bot_username, event.id)
    qr_buffer = build_qr_png(link)
    photo = BufferedInputFile(qr_buffer.read(), filename=f"event_{event.id}_qr.png")
    await bot.send_photo(
        chat_id=callback.from_user.id,
        photo=photo,
        caption=f"🔗 Ссылка на регистрацию:\n{link}\n\nQR-код можно скачать и распечатать.",
    )
    await _safe_callback_answer(callback)


# --------------------------------------------------------------------------- #
# Events: create (FSM)
# --------------------------------------------------------------------------- #


@router.callback_query(AdminEvent.filter(F.action == "create"))
async def admin_event_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateEvent.title)
    await _safe_edit_or_answer(callback, "➕ Создание мероприятия\n\nВведите название:")
    await _safe_callback_answer(callback)


@router.message(CreateEvent.title)
async def admin_event_create_title(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip():
        await message.answer("Название не может быть пустым. Введите название:")
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(CreateEvent.description)
    await message.answer("Введите описание (или отправьте «-», чтобы пропустить):")


@router.message(CreateEvent.description)
async def admin_event_create_description(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    await state.update_data(description=None if text == "-" else text)
    await state.set_state(CreateEvent.date)
    await message.answer("Введите дату в формате ДД.ММ.ГГГГ, например 20.10.2026:")


def _parse_date(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def _parse_time(text: str) -> time | None:
    normalized = text.strip().replace(".", ":")
    try:
        return datetime.strptime(normalized, "%H:%M").time()
    except ValueError:
        return None


@router.message(CreateEvent.date)
async def admin_event_create_date(message: Message, state: FSMContext) -> None:
    parsed = _parse_date(message.text or "")
    if parsed is None:
        await message.answer("Не удалось распознать дату. Формат: ДД.ММ.ГГГГ, например 20.10.2026:")
        return
    await state.update_data(date=parsed.isoformat())
    await state.set_state(CreateEvent.time)
    await message.answer("Введите время в формате ЧЧ:ММ, например 19:30:")


@router.message(CreateEvent.time)
async def admin_event_create_time(message: Message, state: FSMContext) -> None:
    parsed = _parse_time(message.text or "")
    if parsed is None:
        await message.answer("Не удалось распознать время. Формат: ЧЧ:ММ, например 19:30:")
        return
    await state.update_data(time=parsed.isoformat())
    await state.set_state(CreateEvent.location)
    await message.answer("Введите место проведения:")


@router.message(CreateEvent.location)
async def admin_event_create_location(message: Message, state: FSMContext) -> None:
    location = (message.text or "").strip()
    if not location:
        await message.answer("Место не может быть пустым. Введите место проведения:")
        return

    await state.update_data(location=location)
    await state.set_state(CreateEvent.photo)
    await message.answer("Добавьте фото мероприятия (отправьте фото) или напишите '-' для пропуска:")


@router.message(CreateEvent.photo)
async def admin_event_create_photo(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    if message.photo:
        photo_file_id = message.photo[-1].file_id
    elif (message.text or "").strip() == "-":
        photo_file_id = None
    else:
        await message.answer("Отправьте фото или напишите '-' чтобы пропустить:")
        return

    await state.update_data(photo_file_id=photo_file_id)
    await state.set_state(CreateEvent.max_participants)
    await message.answer("Введите максимальное количество участников или '-' без ограничений:")


@router.message(CreateEvent.max_participants)
async def admin_event_create_max_participants(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    value = (message.text or "").strip()
    if value == "-":
        max_participants = None
    else:
        try:
            max_participants = int(value)
        except ValueError:
            await message.answer("Введите целое положительное число или '-' без ограничений:")
            return
        if max_participants < 1:
            await message.answer("Количество участников должно быть больше нуля:")
            return

    data = await state.get_data()
    start_time = datetime.combine(date.fromisoformat(data["date"]), time.fromisoformat(data["time"]))

    event = await EventRepository(session).create(
        title=data["title"],
        description=data.get("description"),
        start_time=start_time,
        location=data["location"],
        photo_file_id=data.get("photo_file_id"),
        max_participants=max_participants,
    )
    await state.clear()
    logger.info("event %s created by admin %s", event.id, message.from_user.id)

    text = f"✅ Мероприятие создано!\n\n{_event_card_text(event, going_count=0)}"
    if settings.bot_username:
        text += f"\n\nСсылка для регистрации:\n{deep_link(settings.bot_username, event.id)}"

    await _answer_event_card(message, event, text)


# --------------------------------------------------------------------------- #
# Events: edit (FSM, one field at a time)
# --------------------------------------------------------------------------- #


@router.callback_query(AdminEvent.filter(F.action == "edit"))
async def admin_event_edit_menu(callback: CallbackQuery, callback_data: AdminEvent) -> None:
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    for field, label in EDIT_FIELD_LABELS.items():
        builder.button(
            text=label, callback_data=AdminEventEditField(field=field, event_id=callback_data.event_id)
        )
    builder.button(text="🔙 Назад", callback_data=AdminEvent(action="open", event_id=callback_data.event_id))
    builder.adjust(2, 2, 1, 1)
    await _safe_edit_or_answer(callback, "✏️ Что изменить?", reply_markup=builder.as_markup())
    await _safe_callback_answer(callback)


@router.callback_query(AdminEventEditField.filter())
async def admin_event_edit_field_start(
    callback: CallbackQuery, callback_data: AdminEventEditField, state: FSMContext
) -> None:
    await state.set_state(EditEvent.value)
    await state.update_data(field=callback_data.field, event_id=callback_data.event_id)
    prompts = {
        "title": "Введите новое название:",
        "description": "Введите новое описание (или «-», чтобы очистить):",
        "date": "Введите новую дату (ДД.ММ.ГГГГ):",
        "time": "Введите новое время (ЧЧ:ММ):",
        "location": "Введите новое место проведения:",
        "photo": "Отправьте новое фото (или '-' чтобы удалить текущее):",
    }
    await _safe_edit_or_answer(callback, prompts[callback_data.field])
    await _safe_callback_answer(callback)


@router.message(EditEvent.value)
async def admin_event_edit_field_apply(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    field: str = data["field"]
    event_id: int = data["event_id"]
    events = EventRepository(session)
    event = await events.get_by_id(event_id)
    if event is None:
        await state.clear()
        await message.answer("Мероприятие больше не существует.", reply_markup=admin_events_menu())
        return

    text = (message.text or "").strip()
    if field == "title":
        if not text:
            await message.answer("Название не может быть пустым. Попробуйте снова:")
            return
        await events.update(event, title=text)
    elif field == "description":
        await events.update(event, description=None if text == "-" else text)
    elif field == "date":
        parsed_date = _parse_date(text)
        if parsed_date is None:
            await message.answer("Не удалось распознать дату. Формат: ДД.ММ.ГГГГ:")
            return
        new_start = datetime.combine(
            parsed_date,
            event.start_time.timetz().replace(tzinfo=event.start_time.tzinfo),
        )
        await events.update(event, start_time=new_start)
    elif field == "time":
        parsed_time = _parse_time(text)
        if parsed_time is None:
            await message.answer("Не удалось распознать время. Формат: ЧЧ:ММ:")
            return
        new_start = datetime.combine(
            event.start_time.date(), parsed_time.replace(tzinfo=event.start_time.tzinfo)
        )
        await events.update(event, start_time=new_start)
    elif field == "location":
        if not text:
            await message.answer("Место не может быть пустым. Попробуйте снова:")
            return
        await events.update(event, location=text)
    elif field == "photo":
        if message.photo:
            await events.update(event, photo_file_id=message.photo[-1].file_id)
        elif text == "-":
            await events.update(event, clear_photo=True)
        else:
            await message.answer("Отправьте фото или '-' чтобы удалить текущее фото:")
            return

    await state.clear()
    logger.info("event %s field %s updated by admin %s", event_id, field, message.from_user.id)
    text = await _event_card_text_with_counts(session, event)
    await _answer_event_card(message, event, f"✅ Обновлено.\n\n{text}")


# --------------------------------------------------------------------------- #
# Participants: menu / list / search / export
# --------------------------------------------------------------------------- #


async def _participants_menu_text(session: AsyncSession, event: Event) -> str:
    counts = await ParticipantsService(session).counts_by_status(event.id)
    total = sum(counts.values())
    return (
        f"👥 Участники\n\n"
        f"🎬 {event.title}\n\n"
        f"✅ Идут: {counts[RegistrationStatus.GOING]}\n"
        f"❌ Не идут: {counts[RegistrationStatus.NOT_GOING]}\n"
        f"⏳ Не ответили: {counts[RegistrationStatus.PENDING]}\n"
        f"🎟 Пришли: {counts[RegistrationStatus.CHECKED_IN]}\n\n"
        f"Всего: {total}"
    )


@router.callback_query(AdminEventPicker.filter(F.purpose == "participants"))
async def admin_participants_from_picker(
    callback: CallbackQuery, callback_data: AdminEventPicker, session: AsyncSession
) -> None:
    event = await EventRepository(session).get_by_id(callback_data.event_id)
    if event is None:
        await _safe_callback_answer(callback, "Мероприятие не найдено.", show_alert=True)
        return
    text = await _participants_menu_text(session, event)
    await _safe_edit_or_answer(callback, text, reply_markup=admin_participants_menu(event.id))
    await _safe_callback_answer(callback)


@router.callback_query(AdminParticipants.filter(F.action == "menu"))
async def admin_participants_menu_handler(
    callback: CallbackQuery, callback_data: AdminParticipants, session: AsyncSession
) -> None:
    event = await EventRepository(session).get_by_id(callback_data.event_id)
    if event is None:
        await _safe_callback_answer(callback, "Мероприятие не найдено.", show_alert=True)
        return
    text = await _participants_menu_text(session, event)
    await _safe_edit_or_answer(callback, text, reply_markup=admin_participants_menu(event.id))
    await _safe_callback_answer(callback)


@router.callback_query(AdminParticipants.filter(F.action == "list"))
async def admin_participants_list(
    callback: CallbackQuery, callback_data: AdminParticipants, session: AsyncSession, settings: Settings
) -> None:
    service = ParticipantsService(session)
    items, page = await service.list_participants(
        event_id=callback_data.event_id,
        status_filter=callback_data.status_filter,
        page_number=callback_data.page,
        page_size=settings.participants_page_size,
    )
    if not items:
        await _safe_edit_or_answer(
            callback,
            "По этому фильтру участников нет.",
            reply_markup=admin_participants_menu(callback_data.event_id),
        )
        await _safe_callback_answer(callback)
        return

    header = f"👥 Участники — {page.header()}"
    await _safe_edit_or_answer(
        callback,
        header,
        reply_markup=participants_list_keyboard(
            items, event_id=callback_data.event_id, status_filter=callback_data.status_filter, page=page
        ),
    )
    await _safe_callback_answer(callback)


@router.callback_query(AdminParticipants.filter(F.action == "search"))
async def admin_participants_search_start(
    callback: CallbackQuery, callback_data: AdminParticipants, state: FSMContext
) -> None:
    await state.set_state(SearchParticipant.query)
    await state.update_data(event_id=callback_data.event_id)
    await _safe_edit_or_answer(callback, "🔍 Введите имя, username или Telegram ID участника:")
    await _safe_callback_answer(callback)


@router.message(SearchParticipant.query)
async def admin_participants_search_run(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    event_id: int = data["event_id"]
    query = (message.text or "").strip()
    await state.clear()

    if not query:
        await message.answer("Пустой запрос.", reply_markup=admin_participants_menu(event_id))
        return

    service = ParticipantsService(session)
    results = await service.search_participants(event_id=event_id, query=query)
    if not results:
        await message.answer("Никого не найдено.", reply_markup=admin_participants_menu(event_id))
        return

    fake_page = Page(page=0, page_size=len(results), total_items=len(results))
    await message.answer(
        f"🔍 Результаты поиска «{query}»:",
        reply_markup=participants_list_keyboard(
            results, event_id=event_id, status_filter="ALL", page=fake_page
        ),
    )


@router.callback_query(AdminParticipants.filter(F.action == "export"))
async def admin_participants_export_menu(callback: CallbackQuery, callback_data: AdminParticipants) -> None:
    await _safe_edit_or_answer(
        callback,
        "📥 Экспорт участников\n\nВыберите формат:",
        reply_markup=export_format_keyboard(callback_data.event_id),
    )
    await _safe_callback_answer(callback)


@router.callback_query(ExportFormat.filter())
async def admin_export_run(
    callback: CallbackQuery, callback_data: ExportFormat, session: AsyncSession, bot: Bot
) -> None:
    registrations = await RegistrationRepository(session).list_for_event(
        callback_data.event_id, limit=10_000, offset=0
    )
    event = await EventRepository(session).get_by_id(callback_data.event_id)
    event_title = event.title if event else str(callback_data.event_id)

    if callback_data.fmt == "csv":
        buffer = build_csv(registrations)
        filename = f"participants_{callback_data.event_id}.csv"
    else:
        buffer = build_xlsx(registrations)
        filename = f"participants_{callback_data.event_id}.xlsx"

    document = BufferedInputFile(buffer.read(), filename=filename)
    await bot.send_document(chat_id=callback.from_user.id, document=document, caption=f"Экспорт: {event_title}")
    logger.info("admin %s exported participants of event %s as %s", callback.from_user.id, event.id if event else "?", callback_data.fmt)
    await _safe_callback_answer(callback, "Файл отправлен")


# --------------------------------------------------------------------------- #
# Participant card
# --------------------------------------------------------------------------- #


def _participant_card_text(registration) -> str:
    user = registration.user
    name = user_display_name(
        first_name=user.first_name, last_name=user.last_name, username=user.username
    )
    username_line = f"Username: @{user.username}\n" if user.username else ""
    return (
        "👤 Участник\n\n"
        f"Имя: {name}\n"
        f"{username_line}"
        f"Telegram ID: {user.telegram_id}\n\n"
        f"Статус: {status_display(registration.status)}\n\n"
        f"Зарегистрирован:\n{format_datetime(registration.registered_at)}"
    )


@router.callback_query(ParticipantCard.filter(F.action == "open"))
async def participant_card_open(
    callback: CallbackQuery, callback_data: ParticipantCard, session: AsyncSession
) -> None:
    registration = await RegistrationRepository(session).get_by_id(callback_data.registration_id)
    if registration is None:
        await _safe_callback_answer(callback, "Регистрация не найдена — возможно, была удалена.", show_alert=True)
        return
    await _safe_edit_or_answer(
        callback,
        _participant_card_text(registration),
        reply_markup=participant_card_keyboard(
            registration, page=callback_data.page, status_filter=callback_data.status_filter
        ),
    )
    await _safe_callback_answer(callback)


@router.callback_query(ParticipantCard.filter(F.action.in_({"set_going", "set_declined"})))
async def participant_card_set_status(
    callback: CallbackQuery, callback_data: ParticipantCard, session: AsyncSession
) -> None:
    repo = RegistrationRepository(session)
    registration = await repo.get_by_id(callback_data.registration_id)
    if registration is None:
        await _safe_callback_answer(callback, "Регистрация не найдена.", show_alert=True)
        return
    new_status = RegistrationStatus.GOING if callback_data.action == "set_going" else RegistrationStatus.NOT_GOING
    await ParticipantsService(session).admin_set_status(registration, new_status)
    await _safe_edit_or_answer(
        callback,
        _participant_card_text(registration),
        reply_markup=participant_card_keyboard(
            registration, page=callback_data.page, status_filter=callback_data.status_filter
        ),
    )
    await _safe_callback_answer(callback, "Статус обновлён")


@router.callback_query(ParticipantCard.filter(F.action == "checkin"))
async def participant_card_checkin(
    callback: CallbackQuery, callback_data: ParticipantCard, session: AsyncSession
) -> None:
    repo = RegistrationRepository(session)
    registration = await repo.get_by_id(callback_data.registration_id)
    if registration is None:
        await _safe_callback_answer(callback, "Регистрация не найдена.", show_alert=True)
        return
    await ParticipantsService(session).checkin(registration)
    await _safe_edit_or_answer(
        callback,
        _participant_card_text(registration),
        reply_markup=participant_card_keyboard(
            registration, page=callback_data.page, status_filter=callback_data.status_filter
        ),
    )
    await _safe_callback_answer(callback, "Отмечен как пришедший 🎟")


@router.callback_query(ParticipantCard.filter(F.action == "delete"))
async def participant_card_delete(
    callback: CallbackQuery, callback_data: ParticipantCard, session: AsyncSession
) -> None:
    repo = RegistrationRepository(session)
    registration = await repo.get_by_id(callback_data.registration_id)
    if registration is None:
        await _safe_callback_answer(callback, "Регистрация уже удалена.", show_alert=True)
        return
    await ParticipantsService(session).delete_registration(registration)
    await _safe_edit_or_answer(
        callback,
        "Регистрация удалена.",
        reply_markup=admin_participants_menu(callback_data.event_id),
    )
    await _safe_callback_answer(callback)


@router.callback_query(ParticipantCard.filter(F.action == "message"))
async def participant_card_message_start(
    callback: CallbackQuery, callback_data: ParticipantCard, state: FSMContext, session: AsyncSession
) -> None:
    registration = await RegistrationRepository(session).get_by_id(callback_data.registration_id)
    if registration is None:
        await _safe_callback_answer(callback, "Регистрация не найдена.", show_alert=True)
        return
    await state.set_state(MessageParticipant.text)
    await state.update_data(
        telegram_id=registration.user.telegram_id,
        registration_id=registration.id,
        event_id=callback_data.event_id,
        page=callback_data.page,
        status_filter=callback_data.status_filter,
    )
    await _safe_edit_or_answer(callback, "📩 Введите сообщение для участника:")
    await _safe_callback_answer(callback)


@router.message(MessageParticipant.text)
async def participant_card_message_send(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пустое сообщение не отправлено.")
        return
    try:
        await bot.send_message(chat_id=data["telegram_id"], text=f"✉️ Сообщение от организаторов:\n\n{text}")
    except TelegramForbiddenError:
        await message.answer("⚠️ Не удалось отправить: пользователь заблокировал бота.")
        return
    except TelegramBadRequest as exc:
        logger.warning("failed to message participant %s: %s", data["telegram_id"], exc)
        await message.answer("⚠️ Не удалось отправить сообщение.")
        return
    await message.answer("✅ Сообщение отправлено.")


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #


@router.callback_query(AdminEventPicker.filter(F.purpose == "stats"))
async def admin_stats_show(callback: CallbackQuery, callback_data: AdminEventPicker, session: AsyncSession) -> None:
    event = await EventRepository(session).get_by_id(callback_data.event_id)
    if event is None:
        await _safe_callback_answer(callback, "Мероприятие не найдено.", show_alert=True)
        return
    stats = await StatisticsService(session).get_event_statistics(event.id)
    text = (
        f"📊 Статистика мероприятия\n\n"
        f"🎬 {event.title}\n\n"
        f"👥 Всего зарегистрировано: {stats.total}\n\n"
        f"✅ Идут: {stats.going}\n"
        f"❌ Не идут: {stats.not_going}\n"
        f"⏳ Без ответа: {stats.pending}\n\n"
        f"🎟 Пришли: {stats.checked_in}\n\n"
        f"📈 Процент подтверждения: {stats.confirmation_rate}%\n"
        f"📈 Процент явки: {stats.attendance_rate}%"
    )
    await _safe_edit_or_answer(callback, text, reply_markup=back_to_admin_menu_button())
    await _safe_callback_answer(callback)


# --------------------------------------------------------------------------- #
# Broadcast
# --------------------------------------------------------------------------- #


@router.callback_query(AdminEventPicker.filter(F.purpose == "broadcast"))
async def admin_broadcast_pick_target(
    callback: CallbackQuery, callback_data: AdminEventPicker, state: FSMContext
) -> None:
    await state.update_data(event_id=callback_data.event_id)
    await _safe_edit_or_answer(
        callback,
        "📢 Рассылка\n\nКому отправить сообщение?",
        reply_markup=broadcast_target_keyboard(),
    )
    await _safe_callback_answer(callback)


@router.callback_query(BroadcastTarget.filter())
async def admin_broadcast_set_target(
    callback: CallbackQuery, callback_data: BroadcastTarget, state: FSMContext
) -> None:
    await state.update_data(target=callback_data.target)
    await state.set_state(Broadcast.message)
    await _safe_edit_or_answer(callback, "Введите текст сообщения для рассылки:")
    await _safe_callback_answer(callback)


_TARGET_TO_STATUS = {
    "going": RegistrationStatus.GOING,
    "checked_in": RegistrationStatus.CHECKED_IN,
}


async def _resolve_recipients(session: AsyncSession, event_id: int, target: str) -> list[int]:
    repo = RegistrationRepository(session)
    status = _TARGET_TO_STATUS.get(target)  # None means "all"
    registrations = await repo.list_for_event(event_id, status=status, limit=100_000, offset=0)
    return [r.user.telegram_id for r in registrations]


@router.message(Broadcast.message)
async def admin_broadcast_preview(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Сообщение не может быть пустым. Введите текст:")
        return

    data = await state.get_data()
    recipients = await _resolve_recipients(session, data["event_id"], data["target"])
    await state.update_data(text=text, recipient_count=len(recipients))
    await state.set_state(Broadcast.confirm)

    preview = f"📢 Предпросмотр\n\n{text}\n\nПолучатели:\n{len(recipients)} человек\n\nОтправить?"
    await message.answer(preview, reply_markup=broadcast_confirm_keyboard())


@router.callback_query(BroadcastConfirm.filter(F.confirm == False))  # noqa: E712
async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _safe_edit_or_answer(callback, "Рассылка отменена.", reply_markup=back_to_admin_menu_button())
    await _safe_callback_answer(callback)


@router.callback_query(BroadcastConfirm.filter(F.confirm == True))  # noqa: E712
async def admin_broadcast_send(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings, bot: Bot
) -> None:
    data = await state.get_data()
    await state.clear()
    text: str = data["text"]
    recipients = await _resolve_recipients(session, data["event_id"], data["target"])

    await _safe_edit_or_answer(callback, f"📢 Отправка началась: 0/{len(recipients)}...")
    await _safe_callback_answer(callback)

    delay = 1.0 / max(settings.broadcast_messages_per_second, 1.0)
    sent, blocked, failed = 0, 0, 0

    for telegram_id in recipients:
        try:
            await bot.send_message(chat_id=telegram_id, text=text)
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await bot.send_message(chat_id=telegram_id, text=text)
                sent += 1
            except Exception:  # noqa: BLE001 - broadcast must keep going regardless of one failure
                failed += 1
        except TelegramBadRequest as exc:
            logger.warning("broadcast failed for %s: %s", telegram_id, exc)
            failed += 1
        await asyncio.sleep(delay)

    logger.info(
        "broadcast finished by admin %s: sent=%s blocked=%s failed=%s",
        callback.from_user.id,
        sent,
        blocked,
        failed,
    )
    summary = (
        f"📢 Рассылка завершена\n\n"
        f"✅ Отправлено: {sent}\n"
        f"🚫 Заблокировали бота: {blocked}\n"
        f"⚠️ Ошибки: {failed}"
    )
    await bot.send_message(chat_id=callback.from_user.id, text=summary, reply_markup=back_to_admin_menu_button())

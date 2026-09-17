"""Inline keyboards shown inside the in-bot admin panel."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import Event, Registration, RegistrationStatus
from app.keyboards.callback_data import (
    AdminEvent,
    AdminEventPicker,
    AdminMenu,
    AdminParticipants,
    BroadcastConfirm,
    BroadcastTarget,
    ExportFormat,
    ParticipantCard,
)
from app.utils.helpers import STATUS_EMOJI, user_display_name
from app.utils.pagination import Page


def admin_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎬 Мероприятия", callback_data=AdminMenu(section="events"))
    builder.button(text="👥 Участники", callback_data=AdminMenu(section="participants"))
    builder.button(text="📊 Статистика", callback_data=AdminMenu(section="stats"))
    builder.button(text="📢 Рассылка", callback_data=AdminMenu(section="broadcast"))
    builder.adjust(2, 2)
    return builder.as_markup()


def back_to_admin_menu_button() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В меню", callback_data=AdminMenu(section="root"))
    return builder.as_markup()


def admin_events_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать мероприятие", callback_data=AdminEvent(action="create"))
    builder.button(text="📋 Список мероприятий", callback_data=AdminEvent(action="list"))
    builder.button(text="🔙 В меню", callback_data=AdminMenu(section="root"))
    builder.adjust(1)
    return builder.as_markup()


def events_list_keyboard(events: list[Event]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for event in events:
        mark = "🟢" if event.is_active else "🔴"
        builder.button(
            text=f"{mark} {event.title}", callback_data=AdminEvent(action="open", event_id=event.id)
        )
    builder.button(text="🔙 В меню", callback_data=AdminMenu(section="events"))
    builder.adjust(1)
    return builder.as_markup()


def event_actions_keyboard(event: Event) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редактировать", callback_data=AdminEvent(action="edit", event_id=event.id))
    toggle_text = "🔴 Деактивировать" if event.is_active else "🟢 Активировать"
    toggle_action = "deactivate" if event.is_active else "activate"
    builder.button(text=toggle_text, callback_data=AdminEvent(action=toggle_action, event_id=event.id))
    builder.button(text="🔗 QR-ссылка", callback_data=AdminEvent(action="qr", event_id=event.id))
    builder.button(
        text="👥 Участники",
        callback_data=AdminParticipants(action="menu", event_id=event.id),
    )
    builder.button(text="🗑 Удалить", callback_data=AdminEvent(action="delete", event_id=event.id))
    builder.button(text="🔙 К списку", callback_data=AdminEvent(action="list"))
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def event_picker_keyboard(events: list[Event], *, purpose: str) -> InlineKeyboardMarkup:
    """Pick which event a cross-section action (📊 statistics, 📢 broadcast,
    👥 participants) should apply to.
    """
    builder = InlineKeyboardBuilder()
    for event in events:
        mark = "🟢" if event.is_active else "🔴"
        builder.button(
            text=f"{mark} {event.title}",
            callback_data=AdminEventPicker(purpose=purpose, event_id=event.id),
        )
    builder.button(text="🔙 В меню", callback_data=AdminMenu(section="root"))
    builder.adjust(1)
    return builder.as_markup()


def event_delete_confirm_keyboard(event_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Да, удалить", callback_data=AdminEvent(action="delete_confirm", event_id=event_id))
    builder.button(text="❌ Отмена", callback_data=AdminEvent(action="open", event_id=event_id))
    builder.adjust(2)
    return builder.as_markup()


def admin_participants_menu(event_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Идут",
        callback_data=AdminParticipants(action="list", event_id=event_id, status_filter="GOING"),
    )
    builder.button(
        text="❌ Не идут",
        callback_data=AdminParticipants(action="list", event_id=event_id, status_filter="NOT_GOING"),
    )
    builder.button(
        text="⏳ Без ответа",
        callback_data=AdminParticipants(action="list", event_id=event_id, status_filter="PENDING"),
    )
    builder.button(
        text="🎟 Пришли",
        callback_data=AdminParticipants(action="list", event_id=event_id, status_filter="CHECKED_IN"),
    )
    builder.button(
        text="👥 Все", callback_data=AdminParticipants(action="list", event_id=event_id, status_filter="ALL")
    )
    builder.button(text="🔍 Поиск", callback_data=AdminParticipants(action="search", event_id=event_id))
    builder.button(text="📥 Экспорт", callback_data=AdminParticipants(action="export", event_id=event_id))
    builder.button(text="🔙 К мероприятию", callback_data=AdminEvent(action="open", event_id=event_id))
    builder.adjust(2, 2, 1, 1, 1)
    return builder.as_markup()


def participants_list_keyboard(
    registrations: list[Registration], *, event_id: int, status_filter: str, page: Page
) -> InlineKeyboardMarkup:
    """One participant per row, then a nav row, then a "back to menu" row."""
    builder = InlineKeyboardBuilder()

    for registration in registrations:
        user = registration.user
        name = user_display_name(
            first_name=user.first_name, last_name=user.last_name, username=user.username
        )
        emoji = STATUS_EMOJI[registration.status]
        builder.row(
            InlineKeyboardButton(
                text=f"{emoji} {name}",
                callback_data=ParticipantCard(
                    action="open",
                    registration_id=registration.id,
                    event_id=event_id,
                    page=page.page,
                    status_filter=status_filter,
                ).pack(),
            )
        )

    nav_buttons: list[InlineKeyboardButton] = []
    if page.has_prev:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=AdminParticipants(
                    action="list", event_id=event_id, status_filter=status_filter, page=page.page - 1
                ).pack(),
            )
        )
    if page.has_next:
        nav_buttons.append(
            InlineKeyboardButton(
                text="➡️ Далее",
                callback_data=AdminParticipants(
                    action="list", event_id=event_id, status_filter=status_filter, page=page.page + 1
                ).pack(),
            )
        )
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(
            text="🔙 В меню",
            callback_data=AdminParticipants(action="menu", event_id=event_id).pack(),
        )
    )
    return builder.as_markup()


def participant_card_keyboard(
    registration: Registration, *, page: int, status_filter: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    reg_id = registration.id
    event_id = registration.event_id
    builder.button(
        text="✅ Отметить как «Иду»",
        callback_data=ParticipantCard(
            action="set_going", registration_id=reg_id, event_id=event_id, page=page, status_filter=status_filter
        ),
    )
    builder.button(
        text="❌ Отметить как «Не иду»",
        callback_data=ParticipantCard(
            action="set_declined", registration_id=reg_id, event_id=event_id, page=page, status_filter=status_filter
        ),
    )
    if registration.status != RegistrationStatus.CHECKED_IN:
        builder.button(
            text="🎟 Отметить пришедшим",
            callback_data=ParticipantCard(
                action="checkin", registration_id=reg_id, event_id=event_id, page=page, status_filter=status_filter
            ),
        )
    builder.button(
        text="🚫 Удалить регистрацию",
        callback_data=ParticipantCard(
            action="delete", registration_id=reg_id, event_id=event_id, page=page, status_filter=status_filter
        ),
    )
    builder.button(
        text="📩 Написать пользователю",
        callback_data=ParticipantCard(
            action="message", registration_id=reg_id, event_id=event_id, page=page, status_filter=status_filter
        ),
    )
    builder.button(
        text="🔙 Назад",
        callback_data=AdminParticipants(action="list", event_id=event_id, status_filter=status_filter, page=page),
    )
    builder.adjust(1)
    return builder.as_markup()


def export_format_keyboard(event_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📄 CSV", callback_data=ExportFormat(fmt="csv", event_id=event_id))
    builder.button(text="📊 Excel", callback_data=ExportFormat(fmt="xlsx", event_id=event_id))
    builder.adjust(2)
    return builder.as_markup()


def broadcast_target_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Все зарегистрированные", callback_data=BroadcastTarget(target="all"))
    builder.button(text="✅ Только те, кто идёт", callback_data=BroadcastTarget(target="going"))
    builder.button(text="🎟 Только пришедшие", callback_data=BroadcastTarget(target="checked_in"))
    builder.adjust(1)
    return builder.as_markup()


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить", callback_data=BroadcastConfirm(confirm=True))
    builder.button(text="❌ Отмена", callback_data=BroadcastConfirm(confirm=False))
    builder.adjust(2)
    return builder.as_markup()

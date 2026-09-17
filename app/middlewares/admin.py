"""Middleware that injects an `is_admin` flag into every handler's data.

Handlers never read `ADMIN_IDS` themselves — they only ever see the
already-computed boolean, so there is exactly one place in the codebase that
decides who is an administrator.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser

from app.config import Settings

logger = logging.getLogger(__name__)


class AdminMiddleware(BaseMiddleware):
    """Resolves `event.from_user` against `settings.admin_ids` and stores
    the result in `data["is_admin"]` for every update.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: TgUser | None = data.get("event_from_user")
        data["is_admin"] = bool(user and self._settings.is_admin(user.id))
        return await handler(event, data)


class AdminAccessGuard(BaseMiddleware):
    """Attached only to the admin router: refuses every event that reaches
    it unless `is_admin` (set earlier by `AdminMiddleware`) is True.

    This is the single choke point that satisfies "проверять права
    администратора перед каждой админской операцией" — every admin handler
    is reached exclusively through this router, so nothing downstream needs
    to re-check `is_admin` itself. Because `callback_data` from the user is
    never trusted, this check runs even for callbacks that could only have
    been produced by an admin keyboard in the first place.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not data.get("is_admin", False):
            logger.warning("blocked admin action from non-admin user")
            from aiogram.types import CallbackQuery, Message

            if isinstance(event, Message):
                await event.answer("⛔ У вас нет доступа.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ У вас нет доступа.", show_alert=True)
            return None
        return await handler(event, data)

"""Simple in-memory per-user rate limiting for Telegram updates."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser

from app.config import Settings


class AntiSpamMiddleware(BaseMiddleware):
    """Drop bursts of messages and callbacks from the same user.

    The limiter is intentionally process-local. It protects a single bot
    process from accidental button mashing without adding a database or
    external cache dependency.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._events: dict[int, deque[float]] = defaultdict(deque)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: TgUser | None = data.get("event_from_user")
        if user is None or self._settings.is_admin(user.id):
            return await handler(event, data)

        now = time.monotonic()
        history = self._events[user.id]
        cutoff = now - self._settings.antispam_window_seconds
        while history and history[0] <= cutoff:
            history.popleft()

        if len(history) >= self._settings.antispam_max_events:
            if isinstance(event, CallbackQuery):
                await event.answer("Слишком много запросов. Попробуйте через несколько секунд.")
            elif isinstance(event, Message):
                await event.answer("Слишком много сообщений. Попробуйте через несколько секунд.")
            return None

        history.append(now)
        return await handler(event, data)
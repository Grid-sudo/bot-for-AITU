"""Middleware that opens one DB session per update and injects it as `session`.

Not present in the originally sketched file tree (which only listed
`middlewares/admin.py`), but this is the standard aiogram 3 pattern for
giving every handler a ready-to-use `AsyncSession` via dependency injection
instead of each handler opening its own connection.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database.database import Database


class DatabaseMiddleware(BaseMiddleware):
    def __init__(self, database: Database) -> None:
        self._database = database

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._database.session() as session:
            data["session"] = session
            return await handler(event, data)

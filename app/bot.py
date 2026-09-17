"""Builds the `Bot` and `Dispatcher` instances and wires everything together."""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.config import Settings
from app.database.database import Database
from app.handlers import admin, profile, registration, start
from app.middlewares.admin import AdminAccessGuard, AdminMiddleware
from app.middlewares.antispam import AntiSpamMiddleware
from app.middlewares.db import DatabaseMiddleware

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(settings: Settings, database: Database) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Workflow data available to every handler by parameter name.
    dp["settings"] = settings

    # Global (dispatcher-level) middlewares run for every update, regardless
    # of which router eventually handles it.
    dp.message.middleware(DatabaseMiddleware(database))
    dp.callback_query.middleware(DatabaseMiddleware(database))
    dp.message.middleware(AdminMiddleware(settings))
    dp.callback_query.middleware(AdminMiddleware(settings))
    antispam = AntiSpamMiddleware(settings)
    dp.message.middleware(antispam)
    dp.callback_query.middleware(antispam)

    # Router-scoped guard: only the admin router requires `is_admin`.
    admin.router.message.middleware(AdminAccessGuard())
    admin.router.callback_query.middleware(AdminAccessGuard())

    dp.include_router(start.router)
    dp.include_router(registration.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)

    return dp


async def set_bot_commands(bot: Bot) -> None:
    """Only student-facing commands are advertised in the Telegram UI menu —
    `/admin` is intentionally left out so the average student never sees it.
    """
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать / информация о киновечере"),
            BotCommand(command="profile", description="Моя регистрация"),
        ]
    )

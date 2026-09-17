"""Entrypoint: `python main.py` starts long-polling with graceful shutdown."""
from __future__ import annotations

import asyncio
import logging
import signal

from app.bot import create_bot, create_dispatcher, set_bot_commands
from app.config import get_settings
from app.database.database import Database


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    # aiogram is fairly chatty on INFO for every update; keep it at WARNING
    # unless the operator explicitly asked for DEBUG.
    if level.upper() != "DEBUG":
        logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger("movie_bot")

    if not settings.admin_ids:
        logger.warning("ADMIN_IDS is empty — no one will be able to access the admin panel")

    database = Database(settings.database_url)
    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings, database)

    stop_event = asyncio.Event()

    def _handle_shutdown_signal() -> None:
        logger.info("shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_shutdown_signal)
        except NotImplementedError:
            # add_signal_handler is not available on Windows's default loop.
            pass

    await set_bot_commands(bot)
    logger.info("bot starting")

    polling_task = asyncio.create_task(dispatcher.start_polling(bot, handle_signals=False))
    stop_task = asyncio.create_task(stop_event.wait())

    try:
        await asyncio.wait({polling_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        logger.info("bot stopping")
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        await dispatcher.storage.close()
        await bot.session.close()
        await database.dispose()
        logger.info("bot stopped cleanly")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

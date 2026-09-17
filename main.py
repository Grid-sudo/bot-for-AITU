"""Entrypoint: `python main.py` starts long-polling with graceful shutdown."""
from __future__ import annotations

import asyncio
import logging
import signal

from aiohttp import web
from aiogram.types import Update

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

    webhook_url = (settings.webhook_url or settings.render_external_url).rstrip("/")
    polling_task: asyncio.Task | None = None

    try:
        if webhook_url:
            await _run_webhook(
                bot=bot,
                dispatcher=dispatcher,
                webhook_url=webhook_url,
                webhook_secret=settings.webhook_secret,
                port=settings.port,
                stop_event=stop_event,
            )
        else:
            polling_task = asyncio.create_task(dispatcher.start_polling(bot, handle_signals=False))
            stop_task = asyncio.create_task(stop_event.wait())
            await asyncio.wait({polling_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        logger.info("bot stopping")
        if polling_task is not None:
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
        await dispatcher.storage.close()
        await bot.session.close()
        await database.dispose()
        logger.info("bot stopped cleanly")


async def _run_webhook(
    *,
    bot,
    dispatcher,
    webhook_url: str,
    webhook_secret: str,
    port: int,
    stop_event: asyncio.Event,
) -> None:
    logger = logging.getLogger("movie_bot")

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def telegram_webhook(request: web.Request) -> web.Response:
        if webhook_secret and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != webhook_secret:
            raise web.HTTPForbidden(text="forbidden")
        payload = await request.json()
        update = Update.model_validate(payload)
        await dispatcher.feed_update(bot, update)
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/telegram/webhook", telegram_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    await bot.set_webhook(
        f"{webhook_url}/telegram/webhook",
        secret_token=webhook_secret or None,
        drop_pending_updates=False,
    )
    logger.info("webhook server started on port %s", port)

    try:
        await stop_event.wait()
    finally:
        await bot.delete_webhook(drop_pending_updates=False)
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

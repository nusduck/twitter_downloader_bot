import asyncio
import logging
from typing import Any, Dict, Optional

from aiohttp import web
from telegram.ext import Application

from app.bot.handlers import ChatReplyTarget, downloader, process_tweet_text
from app.core.config import config

logger = logging.getLogger(__name__)
_RUNNERS: Dict[int, web.AppRunner] = {}


def _authorized(request: web.Request) -> bool:
    if not config.SHORTCUT_TOKEN:
        return True

    auth_header = request.headers.get("Authorization", "")
    header_token = request.headers.get("X-Shortcut-Token")
    query_token = request.query.get("token")

    if auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip() == config.SHORTCUT_TOKEN
    return header_token == config.SHORTCUT_TOKEN or query_token == config.SHORTCUT_TOKEN


async def _read_payload(request: web.Request) -> Dict[str, Any]:
    if request.method == "GET":
        return dict(request.query)

    content_type = request.headers.get("Content-Type", "")
    if "application/json" in content_type:
        return await request.json()
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        data = await request.post()
        return dict(data)

    body = (await request.text()).strip()
    return {"text": body} if body else {}


def _chat_id_from_payload(payload: Dict[str, Any]) -> Optional[int]:
    raw_chat_id = payload.get("chat_id") or config.SHORTCUT_CHAT_ID
    if not raw_chat_id:
        return None
    try:
        return int(raw_chat_id)
    except (TypeError, ValueError):
        return None


async def _process_shortcut(application: Application, text: str, chat_id: int) -> None:
    try:
        logger.info("Shortcut job started chat_id=%s", chat_id)
        await process_tweet_text(
            text,
            ChatReplyTarget(application.bot, chat_id),
            application.bot_data,
            temp_id=f"shortcut_{chat_id}",
        )
        logger.info("Shortcut job finished chat_id=%s", chat_id)
    except Exception:
        logger.exception("Shortcut job failed chat_id=%s", chat_id)
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text="Shortcut processing failed unexpectedly.",
            )
        except Exception:
            logger.exception("Failed to notify shortcut target chat")


async def shortcut_handler(request: web.Request) -> web.Response:
    if not _authorized(request):
        logger.warning("Shortcut request rejected reason=unauthorized remote=%s", request.remote)
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    try:
        payload = await _read_payload(request)
    except Exception as exc:
        logger.warning("Shortcut request rejected reason=invalid_payload remote=%s error=%s", request.remote, exc)
        return web.json_response({"ok": False, "error": f"invalid payload: {exc}"}, status=400)

    text = (
        payload.get("url")
        or payload.get("text")
        or payload.get("tweet_url")
        or payload.get("share_url")
        or ""
    ).strip()
    if not text:
        logger.info("Shortcut request rejected reason=missing_text remote=%s", request.remote)
        return web.json_response({"ok": False, "error": "missing url or text"}, status=400)

    tweet_ids = downloader.extract_tweet_ids(text)
    if not tweet_ids:
        logger.info("Shortcut request rejected reason=no_supported_link remote=%s", request.remote)
        return web.json_response({"ok": False, "error": "no supported tweet link found"}, status=400)

    chat_id = _chat_id_from_payload(payload)
    if not chat_id:
        logger.info("Shortcut request rejected reason=missing_chat_id remote=%s", request.remote)
        return web.json_response({"ok": False, "error": "missing valid chat_id"}, status=400)

    application: Application = request.app["telegram_application"]
    logger.info(
        "Shortcut request accepted chat_id=%s tweet_ids=%s background=%s remote=%s",
        chat_id,
        ",".join(tweet_ids),
        config.SHORTCUT_BACKGROUND,
        request.remote,
    )
    if config.SHORTCUT_BACKGROUND:
        task = asyncio.create_task(_process_shortcut(application, text, chat_id))
        request.app["shortcut_tasks"].add(task)
        task.add_done_callback(request.app["shortcut_tasks"].discard)
        return web.json_response({"ok": True, "status": "accepted", "tweet_ids": tweet_ids}, status=202)

    processed = await process_tweet_text(
        text,
        ChatReplyTarget(application.bot, chat_id),
        application.bot_data,
        temp_id=f"shortcut_{chat_id}",
    )
    logger.info("Shortcut request completed chat_id=%s processed=%s", chat_id, processed)
    return web.json_response({"ok": True, "status": "completed", "processed": processed, "tweet_ids": tweet_ids})


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def start_shortcut_server(application: Application) -> None:
    if not config.SHORTCUT_ENABLED:
        return

    app = web.Application()
    app["telegram_application"] = application
    app["shortcut_tasks"] = set()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/shortcut", shortcut_handler)
    app.router.add_post("/shortcut", shortcut_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.SHORTCUT_HOST, config.SHORTCUT_PORT)
    await site.start()

    _RUNNERS[id(application)] = runner
    logger.info(
        "Shortcut server started host=%s port=%s auth=%s background=%s",
        config.SHORTCUT_HOST,
        config.SHORTCUT_PORT,
        "enabled" if config.SHORTCUT_TOKEN else "disabled",
        config.SHORTCUT_BACKGROUND,
    )


async def stop_shortcut_server(application: Application) -> None:
    runner = _RUNNERS.pop(id(application), None)
    if runner is not None:
        await runner.cleanup()
        logger.info("Shortcut server stopped")

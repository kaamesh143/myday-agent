"""Telegram bot that answers messages with Claude.

Only Telegram user IDs listed in ALLOWED_USER_IDS get a reply.
Anyone else is ignored, and their user ID is logged so you can
find your own ID on first run.
"""

import asyncio
import datetime
import functools
import logging

import anthropic
from telegram import Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.chat import answer
from app.config import load_settings
from app.gmail_source import DEFAULT_QUERY
from app.myday import MyDayConfig, build_myday_message
from app.trip import TripConfig, find_ticket_pdfs, trip_reply, trip_section_for_myday
from app.trip_agent import answer_with_tools

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
# httpx logs request URLs, and Telegram URLs contain the bot token. httpx2 is used by the Anthropic library.
for noisy in ("httpx", "httpx2"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("assistant")

HELP_TEXT = (
    "Hi! I'm your assistant (milestone 2: Claude chat).\n\n"
    "/help - show this message\n"
    "/myday - today's calendar and weather (and your trip, when one is coming up)\n"
    "/trip - your trip plan from booking emails in Gmail\n"
    "/trip refresh - search Gmail again now\n"
    "/trip <question> - ask about the trip, e.g. /trip when is my flight?\n"
    "/ticket <words> - send the booking PDF from Gmail, e.g. /ticket Scandic Rovaniemi\n"
    "Or just ask, e.g. 'what is my plan on 20 Nov?' or 'send my hotel booking'. "
    "I don't remember earlier messages yet."
)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


def _myday_text(bot_data: dict) -> str:
    trip_config = bot_data.get("trip_config")
    trip = None
    if trip_config is not None:
        trip = functools.partial(trip_section_for_myday, trip_config, bot_data["claude"])
    return build_myday_message(bot_data["myday_config"], trip)


async def myday_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # The weather request waits for the network, so run it in a thread.
    text = await asyncio.to_thread(_myday_text, context.bot_data)
    await update.message.reply_text(text)


async def trip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    argument = " ".join(context.args or [])
    await update.message.chat.send_action(ChatAction.TYPING)
    text = await asyncio.to_thread(
        trip_reply, context.bot_data["trip_config"], context.bot_data["claude"], argument
    )
    await update.message.reply_text(text[:4000])


async def ticket_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    words = " ".join(context.args or [])
    await update.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
    result = await asyncio.to_thread(find_ticket_pdfs, context.bot_data["trip_config"], words)
    if isinstance(result, str):
        await update.message.reply_text(result)
        return
    for pdf in result:
        caption = pdf.subject[:200]  # Telegram captions are short
        await update.message.reply_document(document=pdf.data, filename=pdf.filename, caption=caption)


async def send_daily_myday(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs once a day. Sends the same message as /myday to every allowed user."""
    text = await asyncio.to_thread(_myday_text, context.bot_data)
    for user_id in context.bot_data["allowed_user_ids"]:
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
        except TelegramError as exc:
            log.warning("Daily message could not be sent: %s", type(exc).__name__)


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    client = context.bot_data["claude"]
    await update.message.chat.send_action(ChatAction.TYPING)
    trip_config = context.bot_data.get("trip_config")
    if trip_config is None:
        # ask_claude waits for the network, so run it in a thread to keep the bot responsive.
        reply = await asyncio.to_thread(answer, client, update.message.text)
        await update.message.reply_text(reply)
        return
    # With trip tools, Claude can look up bookings and find PDFs from a normal message.
    result = await asyncio.to_thread(answer_with_tools, client, update.message.text, trip_config)
    await update.message.reply_text(result.text)
    for pdf in result.pdfs:
        await update.message.reply_document(
            document=pdf.data, filename=pdf.filename, caption=pdf.subject[:200]
        )


async def log_unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs for every update (group 1), so skip allowed users: they were already answered."""
    user = update.effective_user
    if user and user.id not in context.bot_data["allowed_user_ids"]:
        log.warning("Ignored message from unauthorized user id=%s username=%s", user.id, user.username)


def build_application(
    token: str,
    allowed_user_ids: frozenset[int],
    claude_client: anthropic.Anthropic,
    myday_time: datetime.time,
    myday_config: MyDayConfig,
    trip_config: TripConfig | None = None,
) -> Application:
    app = Application.builder().token(token).build()
    app.bot_data["claude"] = claude_client
    app.bot_data["allowed_user_ids"] = allowed_user_ids
    app.bot_data["myday_config"] = myday_config
    app.bot_data["trip_config"] = trip_config

    if allowed_user_ids:
        allowed = filters.User(user_id=allowed_user_ids)
        app.add_handler(CommandHandler(["start", "help"], help_cmd, filters=allowed))
        app.add_handler(CommandHandler("myday", myday_cmd, filters=allowed))
        if trip_config is not None:
            app.add_handler(CommandHandler("trip", trip_cmd, filters=allowed))
            app.add_handler(CommandHandler("ticket", ticket_cmd, filters=allowed))
        if app.job_queue is not None:
            app.job_queue.run_daily(send_daily_myday, time=myday_time, name="daily_myday")
        app.add_handler(MessageHandler(allowed & filters.TEXT & ~filters.COMMAND, chat))
    # Everything not handled above lands here and gets no reply.
    app.add_handler(MessageHandler(filters.ALL, log_unauthorized), group=1)
    return app


def main() -> None:
    settings = load_settings()
    if not settings.allowed_user_ids:
        log.warning(
            "ALLOWED_USER_IDS is empty: the bot will reply to nobody. "
            "Message the bot, copy your id from the log, add it to .env and restart."
        )
    claude_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    myday_config = MyDayConfig(
        timezone=settings.timezone,
        google_token_path=settings.google_token_path,
        calendar_ids=settings.calendar_ids,
        private_calendar_ids=settings.private_calendar_ids,
        weather_source=settings.weather_source,
    )
    trip_config = TripConfig(
        token_path=settings.google_token_path,
        cache_path=settings.trip_cache_path,
        timezone=settings.timezone,
        query=settings.trip_gmail_query or DEFAULT_QUERY,
        days_ahead=settings.trip_days_ahead,
    )
    app = build_application(
        settings.bot_token,
        settings.allowed_user_ids,
        claude_client,
        settings.myday_time,
        myday_config,
        trip_config,
    )
    log.info(
        "Daily /myday message scheduled at %s (%s)", settings.myday_time.strftime("%H:%M"), settings.timezone
    )
    log.info("Weather for /myday comes from: %s", settings.weather_source)
    log.info("Bot starting (polling). Allowed users: %s", sorted(settings.allowed_user_ids))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

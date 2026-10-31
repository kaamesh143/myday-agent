"""Telegram bot that answers messages with Claude.

Only Telegram user IDs listed in ALLOWED_USER_IDS get a reply.
Anyone else is ignored, and their user ID is logged so you can
find your own ID on first run.
"""

import asyncio
import logging

import anthropic
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.chat import answer
from app.config import load_settings

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
# httpx logs request URLs, and Telegram URLs contain the bot token. httpx2 is used by the Anthropic library.
for noisy in ("httpx", "httpx2"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("assistant")

HELP_TEXT = (
    "Hi! I'm your assistant (milestone 2: Claude chat).\n\n"
    "/help - show this message\n"
    "Send any text and Claude will answer. I don't remember earlier messages yet."
)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    client = context.bot_data["claude"]
    await update.message.chat.send_action(ChatAction.TYPING)
    # ask_claude waits for the network, so run it in a thread to keep the bot responsive.
    reply = await asyncio.to_thread(answer, client, update.message.text)
    await update.message.reply_text(reply)


async def log_unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs for every update (group 1), so skip allowed users: they were already answered."""
    user = update.effective_user
    if user and user.id not in context.bot_data["allowed_user_ids"]:
        log.warning("Ignored message from unauthorized user id=%s username=%s", user.id, user.username)


def build_application(
    token: str, allowed_user_ids: frozenset[int], claude_client: anthropic.Anthropic
) -> Application:
    app = Application.builder().token(token).build()
    app.bot_data["claude"] = claude_client
    app.bot_data["allowed_user_ids"] = allowed_user_ids

    if allowed_user_ids:
        allowed = filters.User(user_id=allowed_user_ids)
        app.add_handler(CommandHandler(["start", "help"], help_cmd, filters=allowed))
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
    app = build_application(settings.bot_token, settings.allowed_user_ids, claude_client)
    log.info("Bot starting (polling). Allowed users: %s", sorted(settings.allowed_user_ids))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

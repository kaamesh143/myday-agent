"""Milestone 1: secure echo bot.

Only Telegram user IDs listed in ALLOWED_USER_IDS get a reply.
Anyone else is ignored, and their user ID is logged so you can
find your own ID on first run.
"""

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import load_settings

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx logs URLs that contain the bot token
log = logging.getLogger("assistant")

HELP_TEXT = (
    "Hi! I'm your assistant (milestone 1: echo mode).\n\n"
    "/help - show this message\n"
    "Send any text and I'll echo it back."
)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"You said: {update.message.text}")


async def log_unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        log.warning("Ignored message from unauthorized user id=%s username=%s", user.id, user.username)


def build_application(token: str, allowed_user_ids: frozenset[int]) -> Application:
    app = Application.builder().token(token).build()

    if allowed_user_ids:
        allowed = filters.User(user_id=allowed_user_ids)
        app.add_handler(CommandHandler(["start", "help"], help_cmd, filters=allowed))
        app.add_handler(MessageHandler(allowed & filters.TEXT & ~filters.COMMAND, echo))
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
    app = build_application(settings.bot_token, settings.allowed_user_ids)
    log.info("Bot starting (polling). Allowed users: %s", sorted(settings.allowed_user_ids))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

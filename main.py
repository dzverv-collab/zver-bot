"""
Telegram Bot - main entry point.

Commands:
  /start   - Welcome message
  /help    - List available commands
  /echo    - Echo back your message
  /about   - About this bot
"""

import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when /start is issued."""
    user = update.effective_user
    keyboard = [
        [
            InlineKeyboardButton("Help 📖", callback_data="help"),
            InlineKeyboardButton("About ℹ️", callback_data="about"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_html(
        rf"Hi {user.mention_html()}! 👋"
        "\n\nI'm your Telegram bot. Use the buttons below or send me a message.",
        reply_markup=reply_markup,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help message when /help is issued."""
    help_text = (
        "Here's what I can do:\n\n"
        "/start  – Welcome message\n"
        "/help   – Show this help\n"
        "/echo   – Echo your text back\n"
        "/about  – About this bot\n\n"
        "You can also just send me any message and I'll reply!"
    )
    await update.message.reply_text(help_text)


async def echo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the text the user sent after /echo."""
    text = " ".join(context.args)
    if text:
        await update.message.reply_text(f"🔁 {text}")
    else:
        await update.message.reply_text("Usage: /echo <your message>")


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send info about the bot."""
    await update.message.reply_text(
        "🤖 *About this bot*\n\n"
        "Built with [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v21.\n\n"
        "Edit `main.py` to add your own commands and logic.",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# ---------------------------------------------------------------------------
# Callback query handler (inline keyboard buttons)
# ---------------------------------------------------------------------------


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    if query.data == "help":
        help_text = (
            "Here's what I can do:\n\n"
            "/start  – Welcome message\n"
            "/help   – Show this help\n"
            "/echo   – Echo your text back\n"
            "/about  – About this bot\n\n"
            "You can also just send me any message and I'll reply!"
        )
        await query.edit_message_text(help_text)

    elif query.data == "about":
        await query.edit_message_text(
            "🤖 Built with python-telegram-bot v21.\n\nEdit main.py to customise me!"
        )


# ---------------------------------------------------------------------------
# General message handler
# ---------------------------------------------------------------------------


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply to any plain text message."""
    user_text = update.message.text
    await update.message.reply_text(
        f"You said: {user_text}\n\nTry /help to see available commands."
    )


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors."""
    logger.error("Exception while handling an update:", exc_info=context.error)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN environment variable is not set. "
            "Add it as a secret in your project settings."
        )

    app = Application.builder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("echo", echo_command))
    app.add_handler(CommandHandler("about", about_command))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(button_handler))

    # Plain text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Errors
    app.add_error_handler(error_handler)

    logger.info("Bot is running. Press Ctrl-C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

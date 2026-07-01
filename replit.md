# Telegram Bot

A Python Telegram bot built with [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v21.

## Run & Operate

- **Start the bot:** the "Telegram Bot" workflow runs `python main.py`
- **Required secret:** `TELEGRAM_BOT_TOKEN` — set this in Replit Secrets before starting

## Stack

- Python 3
- python-telegram-bot 21.x (async, based on `asyncio`)

## Where things live

- `main.py` — all bot logic (commands, handlers, entry point)
- `requirements.txt` — Python dependencies

## Adding commands

1. Write an `async def my_command(update, context)` handler in `main.py`
2. Register it in `main()`:
   ```python
   app.add_handler(CommandHandler("mycommand", my_command))
   ```

## Architecture decisions

- Single-file layout (`main.py`) keeps the project easy to navigate for small bots; split into modules when handlers grow large.
- Uses long-polling (`run_polling`) — no webhook setup required, works out of the box on Replit.

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- The bot token must be set as the `TELEGRAM_BOT_TOKEN` secret before the workflow will start.
- Get a token from [@BotFather](https://t.me/BotFather) on Telegram.

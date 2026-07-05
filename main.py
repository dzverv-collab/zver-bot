"""
ZVER Store Bot v2 — stable Telegram buyback bot.

Что внутри:
- чистая анкета без перескоков шагов;
- "🏠 Главное меню" работает из любого места;
- "⬅️ Назад" работает по шагам;
- заявки уходят в ADMIN_CHAT_ID из .env;
- токен только из .env;
- фото собираются и отправляются в админ-группу;
- простая локальная CRM в JSON;
- админ-статусы под заявкой;
- без хардкода токенов и личных ID.

Required .env:
TELEGRAM_BOT_TOKEN=123456:ABC...
ADMIN_CHAT_ID=-1003984467292

Optional .env:
CHANNEL_URL=https://t.me/zver_store
CHANNEL_USERNAME=zver_store
REQUIRE_SUBSCRIPTION=false
MANAGER_USERNAME=zvertech
DATA_DIR=data
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ChatAction
from telegram.error import BadRequest, Forbidden, TimedOut, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# -----------------------------------------------------------------------------
# ENV / CONFIG
# -----------------------------------------------------------------------------

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/zver_store")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "zver_store").lstrip("@")
REQUIRE_SUBSCRIPTION = os.getenv("REQUIRE_SUBSCRIPTION", "false").lower() in {"1", "true", "yes", "on"}

MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "zvertech").lstrip("@")
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

WELCOME_IMAGE = Path("assets/welcome.png")
SUCCESS_IMAGE = Path("assets/success.png")

APPLICATIONS_FILE = DATA_DIR / "applications.json"
CUSTOMERS_FILE = DATA_DIR / "customers.json"
COUNTER_FILE = DATA_DIR / "counter.json"

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Add it to .env")

if not ADMIN_CHAT_ID:
    raise RuntimeError("ADMIN_CHAT_ID is missing. Add it to .env")

try:
    ADMIN_CHAT_ID_INT: int | str = int(ADMIN_CHAT_ID)
except ValueError:
    ADMIN_CHAT_ID_INT = ADMIN_CHAT_ID

# -----------------------------------------------------------------------------
# LOGGING
# -----------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("zver-bot-v2")

# -----------------------------------------------------------------------------
# STATES
# -----------------------------------------------------------------------------

(
    DEVICE,
    MODEL,
    MODEL_TEXT,
    MEMORY,
    BATTERY,
    COLOR,
    CONDITION,
    DEFECTS,
    DEFECTS_OTHER,
    PHOTOS,
    CITY,
    CITY_TEXT,
    CONTACT,
) = range(13)

TOTAL_STEPS = 10

# -----------------------------------------------------------------------------
# CONSTANTS / BUTTONS
# -----------------------------------------------------------------------------

HOME = "🏠 Главное меню"
BACK = "⬅️ Назад"
CANCEL = "❌ Отмена"

SELL = "📱 Продать устройство"
PRICE = "💰 Узнать стоимость"
MANAGER = "☎️ Связаться с менеджером"
CHANNEL = "📢 Канал ZVER"

DONE = "✅ Готово"

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [SELL, PRICE],
        [MANAGER, CHANNEL],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие…",
)

NAV_ROW = [BACK, HOME]

DEVICE_OPTIONS = {"iPhone", "iPad", "MacBook", "Apple Watch", "AirPods", "Другое"}
DEVICE_KB = ReplyKeyboardMarkup(
    [
        ["📱 iPhone", "📱 iPad"],
        ["💻 MacBook", "⌚ Apple Watch"],
        ["🎧 AirPods", "📦 Другое"],
        [HOME],
    ],
    resize_keyboard=True,
)

IPHONE_MODELS = [
    "iPhone X", "iPhone XR",
    "iPhone XS", "iPhone XS Max",
    "iPhone 11", "iPhone 11 Pro", "iPhone 11 Pro Max",
    "iPhone SE (2nd generation)",
    "iPhone 12 mini", "iPhone 12", "iPhone 12 Pro", "iPhone 12 Pro Max",
    "iPhone 13 mini", "iPhone 13", "iPhone 13 Pro", "iPhone 13 Pro Max",
    "iPhone SE (3rd generation)",
    "iPhone 14", "iPhone 14 Plus", "iPhone 14 Pro", "iPhone 14 Pro Max",
    "iPhone 15", "iPhone 15 Plus", "iPhone 15 Pro", "iPhone 15 Pro Max",
    "iPhone 16", "iPhone 16 Plus", "iPhone 16 Pro", "iPhone 16 Pro Max",
    "iPhone 17", "iPhone 17 Air", "iPhone 17 Pro", "iPhone 17 Pro Max",
    "✍️ Другая модель",
]
IPHONE_MODELS_KB = ReplyKeyboardMarkup(
    [
        ["iPhone X", "iPhone XR"],
        ["iPhone XS", "iPhone XS Max"],
        ["iPhone 11", "iPhone 11 Pro"],
        ["iPhone 11 Pro Max"],
        ["iPhone SE (2nd generation)"],
        ["iPhone 12 mini", "iPhone 12"],
        ["iPhone 12 Pro", "iPhone 12 Pro Max"],
        ["iPhone 13 mini", "iPhone 13"],
        ["iPhone 13 Pro", "iPhone 13 Pro Max"],
        ["iPhone SE (3rd generation)"],
        ["iPhone 14", "iPhone 14 Plus"],
        ["iPhone 14 Pro", "iPhone 14 Pro Max"],
        ["iPhone 15", "iPhone 15 Plus"],
        ["iPhone 15 Pro", "iPhone 15 Pro Max"],
        ["iPhone 16", "iPhone 16 Plus"],
        ["iPhone 16 Pro", "iPhone 16 Pro Max"],
        ["iPhone 17", "iPhone 17 Air"],
        ["iPhone 17 Pro", "iPhone 17 Pro Max"],
        ["✍️ Другая модель"],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

MEMORY_OPTIONS = {"64 GB", "128 GB", "256 GB", "512 GB", "1 TB", "Другая"}
MEMORY_KB = ReplyKeyboardMarkup(
    [
        ["💾 64 GB", "💿 128 GB", "📀 256 GB"],
        ["🚀 512 GB", "💎 1 TB", "🌈 Другая"],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

BATTERY_OPTIONS = {"100–95%", "94–90%", "89–85%", "84–80%", "Меньше 80%", "Не знаю"}
BATTERY_KB = ReplyKeyboardMarkup(
    [
        ["🔋 100–95%", "🔋 94–90%"],
        ["🔋 89–85%", "🔋 84–80%"],
        ["🔋 Меньше 80%", "❓ Не знаю"],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

COLOR_OPTIONS = {"Чёрный", "Белый", "Серый", "Синий", "Зелёный", "Золотой", "Фиолетовый", "Другой"}
COLOR_KB = ReplyKeyboardMarkup(
    [
        ["⚫ Чёрный", "⚪ Белый", "⚙️ Серый"],
        ["🔵 Синий", "🟢 Зелёный", "🟡 Золотой"],
        ["🟣 Фиолетовый", "🌈 Другой"],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

CONDITION_OPTIONS = {"Отличное", "Хорошее", "Среднее", "Плохое", "После ремонта", "Не включается"}
CONDITION_KB = ReplyKeyboardMarkup(
    [
        ["✨ Отличное", "👍 Хорошее"],
        ["😐 Среднее", "⚠️ Плохое"],
        ["🔧 После ремонта", "❌ Не включается"],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

DEFECT_OPTIONS = [
    "Нет дефектов",
    "Разбит экран",
    "Разбита задняя крышка",
    "Face ID не работает",
    "Камера не работает",
    "Не заряжается",
    "Динамик не работает",
    "Микрофон не работает",
    "Не ловит сеть / Wi‑Fi",
    "После воды",
    "Другие дефекты",
]
DEFECT_NONE_IDX = 0
DEFECT_OTHER_IDX = 10

DONE_PHOTO_KB = ReplyKeyboardMarkup(
    [
        [DONE],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

CITY_OPTIONS = {"Санкт-Петербург", "Москва", "Другой город"}
CITY_KB = ReplyKeyboardMarkup(
    [
        ["Санкт-Петербург", "Москва"],
        ["Другой город"],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

CONTACT_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📲 Отправить мой контакт", request_contact=True)],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

# Filters used by ConversationHandler.
HOME_RE = filters.Regex(r"^.*Главное меню.*$")
BACK_RE = filters.Regex(r"^.*Назад.*$")
PRIVATE_TEXT = filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND

# -----------------------------------------------------------------------------
# STORAGE
# -----------------------------------------------------------------------------

def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Could not read JSON file: %s", path)
        return default


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def next_app_id() -> str:
    data = _read_json(COUNTER_FILE, {"last": 0})
    data["last"] = int(data.get("last", 0)) + 1
    _write_json(COUNTER_FILE, data)
    return f"ZV-{data['last']:05d}"


def save_application(app: Dict[str, Any]) -> None:
    apps = _read_json(APPLICATIONS_FILE, [])
    apps.append(app)
    _write_json(APPLICATIONS_FILE, apps)


def get_application(app_id: str) -> Optional[Dict[str, Any]]:
    apps = _read_json(APPLICATIONS_FILE, [])
    for app in apps:
        if app.get("app_id") == app_id:
            return app
    return None


def patch_application(app_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    apps = _read_json(APPLICATIONS_FILE, [])
    updated_app = None
    for app in apps:
        if app.get("app_id") == app_id:
            app.update(updates)
            updated_app = app
            break
    _write_json(APPLICATIONS_FILE, apps)
    return updated_app


def update_application_status(app_id: str, status: str, price: Optional[str] = None) -> None:
    apps = _read_json(APPLICATIONS_FILE, [])
    for app in apps:
        if app.get("app_id") == app_id:
            app["status"] = status
            if price is not None:
                app["deal_price"] = price
            break
    _write_json(APPLICATIONS_FILE, apps)


def get_customer(user_id: int) -> Optional[Dict[str, Any]]:
    customers = _read_json(CUSTOMERS_FILE, {})
    return customers.get(str(user_id))


def upsert_customer(user_id: int, username: str, full_name: str, app_id: str, date: str, model: str) -> Dict[str, Any]:
    customers = _read_json(CUSTOMERS_FILE, {})
    key = str(user_id)
    customer = customers.get(key, {
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "app_count": 0,
        "first_app_date": date,
        "last_app_date": date,
        "models": [],
        "app_ids": [],
    })
    customer["username"] = username
    customer["full_name"] = full_name
    customer["app_count"] = int(customer.get("app_count", 0)) + 1
    customer["last_app_date"] = date
    customer.setdefault("models", []).append(model)
    customer.setdefault("app_ids", []).append(app_id)
    customers[key] = customer
    _write_json(CUSTOMERS_FILE, customers)
    return customer


def list_stats() -> Dict[str, Any]:
    apps = _read_json(APPLICATIONS_FILE, [])
    customers = _read_json(CUSTOMERS_FILE, {})
    statuses: Dict[str, int] = {}
    for app in apps:
        statuses[app.get("status", "unknown")] = statuses.get(app.get("status", "unknown"), 0) + 1
    return {
        "apps_total": len(apps),
        "customers_total": len(customers),
        "statuses": statuses,
    }

# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------

def esc(value: Any) -> str:
    return html.escape(str(value)) if value not in (None, "") else "—"


def step_text(n: int, title: str, question: str) -> str:
    screens = {
        "Тип устройства": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "📦 <b>Выберите устройство</b>\n\n"
            "Что хотите продать?\n\n"
            "💚 <b>Покупаем устройства Apple практически в любом состоянии.</b>\n\nМы регулярно покупаем:\n\n📱 модели прошлых лет (от iPhone X и новее);\n💥 с разбитым экраном;\n📱 с трещинами на корпусе или задней крышке;\n🔧 после ремонта;\n🔋 с любой ёмкостью аккумулятора;\n⚠️ с любыми неисправностями и дефектами.\n\n✨ Чем честнее вы опишете состояние устройства, тем точнее будет предварительная оценка.\n\n🤝 Даже если сомневаетесь, подходит ли ваше устройство — просто отправьте заявку. Мы обязательно её рассмотрим."
        ),
        "Модель iPhone": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "📱 <b>Модель iPhone</b>\n\n"
            "Выберите точную модель устройства.\n\n"
            "✅ В списке есть модели от <b>iPhone X</b> до <b>iPhone 17 Pro Max</b>.\n"
            "⚡ Модель сильнее всего влияет на стоимость."
        ),
        "Модель": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "📱 <b>Модель устройства</b>\n\n"
            "Напишите модель текстом.\n\n"
            "💡 Например: <b>MacBook Air M2</b>, <b>iPad Pro 12.9</b>, <b>Apple Watch Series 9</b>."
        ),
        "Память": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "💾 <b>Память</b>\n\n"
            "Сколько памяти у устройства?\n\n"
            "💡 Обычно чем больше память — тем выше оценка."
        ),
        "АКБ": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "🔋 <b>Аккумулятор</b>\n\n"
            "Какая максимальная ёмкость батареи?\n\n"
            "💡 Подойдёт любой вариант. Если не знаете — выберите <b>«❓ Не знаю»</b>."
        ),
        "Цвет": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "🎨 <b>Цвет корпуса</b>\n\n"
            "Какого цвета устройство?\n\n"
            "✨ Выберите вариант ниже."
        ),
        "Состояние": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "🛠 <b>Состояние</b>\n\n"
            "Оцените внешний вид устройства.\n\n"
            "🤝 Лучше указать честно — так менеджер быстрее даст реальную цену."
        ),
        "Дефекты": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "⚠️ <b>Дефекты</b>\n\n"
            "Отметьте всё, что есть.\n\n"
            "☑️ Можно выбрать несколько вариантов."
        ),
        "Фотографии": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "📸 <b>Фотографии</b>\n\n"
            "Для максимально точной оценки рекомендуем отправить:\n\n"
            "✅ экран;\n"
            "✅ заднюю крышку;\n"
            "✅ боковые грани;\n"
            "✅ места с повреждениями (если есть);\n"
            "✅ экран <b>«Об этом устройстве»</b>;\n"
            "✅ экран <b>«История деталей и обслуживания»</b>, если он есть.\n\n"
            "💡 Чем больше информации вы отправите, тем точнее будет предварительная оценка.\n\n"
            "ℹ️ Если не знаете, где находятся эти разделы — ничего страшного. Просто отправьте фотографии устройства.\n\n"
            "📎 После загрузки фотографий нажмите <b>«✅ Готово»</b>."
        ),
        "Город": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "📍 <b>Город</b>\n\n"
            "Где находится устройство?\n\n"
            "🚗 Это поможет выбрать удобный формат сделки."
        ),
        "Контакт": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "☎️ <b>Контакт для связи</b>\n\n"
            "Оставьте номер телефона или Telegram.\n\n"
            "👨‍💻 Менеджер свяжется с вами после проверки заявки."
        ),
    }
    return screens.get(title, f"🍏 <b>ZVER Store</b>\n\n📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n<b>{esc(title)}</b>\n\n{question}")


def channel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("📢 Перейти в канал", url=CHANNEL_URL)]])


def defects_kb(selected: set[int]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for i, opt in enumerate(DEFECT_OPTIONS):
        prefix = "✅ " if i in selected else ""
        rows.append([InlineKeyboardButton(f"{prefix}{opt}", callback_data=f"defect:{i}")])
    rows.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="defect:back"),
        InlineKeyboardButton("✅ Дефекты выбраны", callback_data="defect:done"),
    ])
    return InlineKeyboardMarkup(rows)


def admin_status_kb(app_id: str, username: str = "") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("💰 Предложить цену", callback_data=f"admin_hint:{app_id}:price"),
        ],
        [
            InlineKeyboardButton("📌 В работу", callback_data=f"status:{app_id}:working"),
            InlineKeyboardButton("✅ Выкуплено", callback_data=f"status:{app_id}:done"),
        ],
        [
            InlineKeyboardButton("❌ Отказ", callback_data=f"status:{app_id}:rejected"),
            InlineKeyboardButton("⏰ Напомнить позже", callback_data=f"status:{app_id}:remind"),
        ],
    ]
    if username:
        rows.append([InlineKeyboardButton("💬 Написать клиенту", url=f"https://t.me/{username}")])
    return InlineKeyboardMarkup(rows)


def status_label(status: str) -> str:
    return {
        "new": "🟢 Новая заявка",
        "working": "📌 В работе",
        "agreed": "💰 Цена согласована",
        "done": "✅ Выкуплено",
        "rejected": "❌ Отказ",
        "remind": "⏰ Напомнить позже",
        "price_sent": "💰 Цена предложена",
        "client_agreed": "✅ Клиент согласен",
        "client_discuss": "💬 Клиент хочет обсудить",
        "client_declined": "❌ Клиент отказался",
    }.get(status, status)


def admin_card(app: Dict[str, Any], customer_before: Optional[Dict[str, Any]]) -> str:
    user_block = (
        "🆕 <b>Новый клиент</b>"
        if not customer_before
        else (
            "🟢 <b>Уже обращался</b>\n"
            f"Обращений ранее: <b>{esc(customer_before.get('app_count', 0))}</b>\n"
            f"Последняя заявка: {esc(customer_before.get('last_app_date'))}"
        )
    )

    username = app.get("username") or ""
    username_text = f"@{esc(username)}" if username else "—"

    defects = app.get("defects") or []
    defects_text = "\n".join(f"• {esc(d)}" for d in defects) if defects else "• Нет"

    photos_count = len(app.get("photos") or [])

    return (
        f"<b>🟢 Новая заявка</b>\n\n"
        f"🆔 <b>{esc(app['app_id'])}</b>\n"
        f"🕒 {esc(app['date'])}\n\n"
        f"👤 <b>{esc(app.get('full_name'))}</b>\n"
        f"🔗 {username_text}\n"
        f"🧾 Telegram ID: <code>{esc(app.get('user_id'))}</code>\n\n"
        f"{user_block}\n\n"
        f"──────────────\n\n"
        f"📱 <b>Устройство:</b> {esc(app.get('device'))} {esc(app.get('model'))}\n"
        f"💾 <b>Память:</b> {esc(app.get('memory'))}\n"
        f"🔋 <b>АКБ:</b> {esc(app.get('battery'))}\n"
        f"🎨 <b>Цвет:</b> {esc(app.get('color'))}\n"
        f"⭐ <b>Состояние:</b> {esc(app.get('condition'))}\n\n"
        f"⚠️ <b>Дефекты:</b>\n{defects_text}\n\n"
        f"📷 <b>Фото:</b> {photos_count} шт.\n"
        f"📍 <b>Город:</b> {esc(app.get('city'))}\n"
        f"☎️ <b>Контакт:</b> {esc(app.get('contact'))}\n"
        f"💰 <b>Финальная цена:</b> {esc(app.get('final_price')) + ' ₽' if app.get('final_price') else '—'}\n\n"
        f"<b>Статус:</b> {status_label(app.get('status', 'new'))}"
    )


def clean_choice(text: str) -> str:
    """Remove leading emoji/pictogram from reply keyboard buttons."""
    text = text.strip()
    prefixes = [
        "📱 ", "📦 ", "💻 ", "⌚ ", "🎧 ",
        "💾 ", "💿 ", "📀 ", "🚀 ", "💎 ", "🌈 ",
        "🟢 ", "🟡 ", "🟠 ", "🔴 ", "⚠️ ", "❓ ", "🔋 ",
        "⚫ ", "⚪ ", "⚙️ ", "🔵 ", "🟣 ",
        "✨ ", "👍 ", "😐 ", "🔧 ",
    ]
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


async def safe_reply(update: Update, text: str, reply_markup=None, parse_mode: str = "HTML") -> None:
    if update.message:
        await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)


async def go_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()

    text = (
        "🍏 <b>ZVER Store</b>\n\n"
        "🏠 <b>Главное меню</b>\n\n"
        "💰 Продать устройство\n"
        "📸 Получить предварительную оценку по фото\n"
        "☎️ Связаться с менеджером\n"
        "📢 Перейти в канал ZVER\n\n"
        "👇 Выберите действие ниже."
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=MAIN_MENU,
        )
    elif update.message:
        if WELCOME_IMAGE.exists():
            await update.message.reply_photo(
                photo=WELCOME_IMAGE.open("rb"),
                caption=text,
                parse_mode="HTML",
                reply_markup=MAIN_MENU,
            )
        else:
            await safe_reply(update, text, reply_markup=MAIN_MENU)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await safe_reply(update, "❌ Действие отменено.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def is_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not REQUIRE_SUBSCRIPTION:
        return True
    if not CHANNEL_USERNAME:
        return True
    try:
        member = await context.bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in {"member", "administrator", "creator"}
    except (BadRequest, Forbidden) as e:
        logger.warning("Subscription check unavailable: %s. Allowing user.", e)
        return True
    except Exception:
        logger.exception("Subscription check failed. Allowing user.")
        return True


async def ensure_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False
    if await is_subscribed(user.id, context):
        return True
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL)],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_subscription")],
    ])
    await safe_reply(
        update,
        "📢 <b>Перед использованием подпишитесь на канал ZVER.</b>\n\nПосле подписки нажмите кнопку проверки.",
        reply_markup=kb,
    )
    return False

# -----------------------------------------------------------------------------
# STATIC HANDLERS
# -----------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if not await ensure_subscription(update, context):
        return

    caption = (
        "🍏 <b>ZVER Store</b>\n\n"
        "💰 <b>Быстрый выкуп техники Apple</b>\n\n"
        "⚡ Предварительная оценка за <b>5–15 минут</b>\n"
        "📱 Покупаем большинство устройств Apple — от <b>iPhone X</b> до последних моделей\n"
        "🤝 Вы сами решаете, подходит ли вам наше предложение.\n"
        "📸 Заполнение займёт около минуты.\n\n"
        "👇 Нажмите <b>«Продать устройство»</b>, чтобы начать."
    )

    if WELCOME_IMAGE.exists():
        await update.message.reply_photo(
            photo=WELCOME_IMAGE.open("rb"),
            caption=caption,
            parse_mode="HTML",
            reply_markup=MAIN_MENU,
        )
    else:
        await safe_reply(update, caption, reply_markup=MAIN_MENU)



async def price_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await safe_reply(
        update,
        "💰 <b>Узнать стоимость</b>\n\n"
        "Цена зависит от модели, памяти, состояния, АКБ, ремонта и рынка.\n\n"
        "📱 Заполните короткую анкету\n"
        "📸 Прикрепите фото\n"
        "👨‍💻 Менеджер даст предварительную оценку\n\n"
        "👇 Нажмите <b>«📱 Продать устройство»</b>, чтобы начать.",
        reply_markup=MAIN_MENU,
    )



async def contact_manager(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await safe_reply(
        update,
        f"☎️ <b>Связаться с менеджером</b>\n\n"
        f"Напишите: @{MANAGER_USERNAME}\n\n"
        f"💡 Если хотите продать устройство — лучше сначала заполнить анкету.\n"
        f"Так менеджер сразу увидит модель, состояние и фото.",
        reply_markup=MAIN_MENU,
    )



async def channel_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await safe_reply(
        update,
        "📢 <b>Канал ZVER</b>\n\n"
        "Там будут отзывы, кейсы, поступления устройств и развитие проекта.\n\n"
        "❤️ Можно подписаться и следить за нами.",
        reply_markup=channel_kb(),
    )



async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if await is_subscribed(update.effective_user.id, context):
        await q.message.reply_text("✅ Подписка подтверждена.", reply_markup=MAIN_MENU)
    else:
        await q.answer("Пока не вижу подписку.", show_alert=True)

# -----------------------------------------------------------------------------
# SELL FLOW: ASK FUNCTIONS
# -----------------------------------------------------------------------------

async def ask_device(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(
        update,
        step_text(1, "Тип устройства", "Что хотите продать?"),
        reply_markup=DEVICE_KB,
    )
    return DEVICE


async def ask_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(
        update,
        step_text(2, "Модель iPhone", "Выберите модель устройства:"),
        reply_markup=IPHONE_MODELS_KB,
    )
    return MODEL


async def ask_model_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    device = context.user_data.get("device", "устройство")
    await safe_reply(
        update,
        step_text(2, "Модель", f"Введите модель {esc(device)}.\n\nНапример: MacBook Air M2, iPad Pro 12.9, Apple Watch Series 9."),
        reply_markup=ReplyKeyboardMarkup([NAV_ROW], resize_keyboard=True),
    )
    return MODEL_TEXT


async def ask_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(
        update,
        step_text(3, "Память", "Выберите объём памяти:"),
        reply_markup=MEMORY_KB,
    )
    return MEMORY


async def ask_battery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(
        update,
        step_text(4, "АКБ", "Выберите текущую ёмкость аккумулятора.\nЕсли не знаете — нажмите «Не знаю»."),
        reply_markup=BATTERY_KB,
    )
    return BATTERY


async def ask_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(
        update,
        step_text(5, "Цвет", "Выберите цвет устройства:"),
        reply_markup=COLOR_KB,
    )
    return COLOR


async def ask_condition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(
        update,
        step_text(6, "Состояние", "Оцените внешний вид устройства:"),
        reply_markup=CONDITION_KB,
    )
    return CONDITION


async def ask_defects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected = context.user_data.setdefault("defects_selected_idx", set())
    if update.message:
        try:
            await update.message.reply_text("Выберите дефекты ниже:", reply_markup=ReplyKeyboardRemove())
        except Exception:
            pass
        await update.message.reply_text(
            step_text(7, "Дефекты", "Выберите все подходящие варианты и нажмите «✅ Дефекты выбраны»."),
            parse_mode="HTML",
            reply_markup=defects_kb(selected),
        )
    return DEFECTS


async def ask_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    count = len(context.user_data.get("photos", []))
    await safe_reply(
        update,
        step_text(8, "Фотографии", f"Пришлите фото устройства.\nМожно отправить несколько фото.\n\nУже загружено: <b>{count}</b>\n\nКогда закончите — нажмите «✅ Готово»."),
        reply_markup=DONE_PHOTO_KB,
    )
    return PHOTOS


async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(
        update,
        step_text(9, "Город", "Выберите город:"),
        reply_markup=CITY_KB,
    )
    return CITY


async def ask_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(
        update,
        step_text(10, "Контакт", "Введите номер телефона или Telegram для связи.\nМожно нажать кнопку и отправить контакт автоматически."),
        reply_markup=CONTACT_KB,
    )
    return CONTACT

# -----------------------------------------------------------------------------
# SELL FLOW: STEP FUNCTIONS
# -----------------------------------------------------------------------------

async def sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if not await ensure_subscription(update, context):
        return ConversationHandler.END
    return await ask_device(update, context)


async def step_device(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_choice(update.message.text)
    if text not in DEVICE_OPTIONS:
        await safe_reply(update, "Выберите тип устройства кнопкой ниже.", reply_markup=DEVICE_KB)
        return DEVICE

    context.user_data["device"] = text
    context.user_data.pop("model", None)

    if text == "iPhone":
        return await ask_model(update, context)
    return await ask_model_text(update, context)


async def step_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_device(update, context)
    if text == "✍️ Другая модель":
        return await ask_model_text(update, context)
    if text not in set(IPHONE_MODELS):
        await safe_reply(update, "Выберите модель кнопкой ниже или нажмите «✍️ Другая модель».", reply_markup=IPHONE_MODELS_KB)
        return MODEL

    context.user_data["model"] = text
    return await ask_memory(update, context)


async def step_model_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        if context.user_data.get("device") == "iPhone":
            return await ask_model(update, context)
        return await ask_device(update, context)

    if len(text) < 2:
        await safe_reply(update, "Введите модель текстом.", reply_markup=ReplyKeyboardMarkup([NAV_ROW], resize_keyboard=True))
        return MODEL_TEXT

    context.user_data["model"] = text
    return await ask_memory(update, context)


async def step_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_choice(update.message.text)
    if text == BACK:
        if context.user_data.get("device") == "iPhone":
            return await ask_model(update, context)
        return await ask_model_text(update, context)

    # "Другая" разрешаем как вариант.
    if text not in MEMORY_OPTIONS:
        await safe_reply(update, "Выберите память кнопкой ниже.", reply_markup=MEMORY_KB)
        return MEMORY

    context.user_data["memory"] = text
    return await ask_battery(update, context)


async def step_battery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_choice(update.message.text)
    if text == BACK:
        return await ask_memory(update, context)
    if text not in BATTERY_OPTIONS:
        await safe_reply(update, "Выберите уровень АКБ кнопкой ниже.", reply_markup=BATTERY_KB)
        return BATTERY

    context.user_data["battery"] = text
    return await ask_color(update, context)


async def step_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_choice(update.message.text)
    if text == BACK:
        return await ask_battery(update, context)
    if text not in COLOR_OPTIONS:
        await safe_reply(update, "Выберите цвет кнопкой ниже.", reply_markup=COLOR_KB)
        return COLOR

    context.user_data["color"] = text
    return await ask_condition(update, context)


async def step_condition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_choice(update.message.text)
    if text == BACK:
        return await ask_color(update, context)
    if text not in CONDITION_OPTIONS:
        await safe_reply(update, "Оцените состояние кнопкой ниже.", reply_markup=CONDITION_KB)
        return CONDITION

    display_condition = {
        "Отличное": "✨ Отличное",
        "Хорошее": "👍 Хорошее",
        "Среднее": "😐 Среднее",
        "Плохое": "⚠️ Плохое",
        "После ремонта": "🔧 После ремонта",
        "Не включается": "❌ Не включается",
    }.get(text, text)
    context.user_data["condition"] = display_condition
    context.user_data["defects_selected_idx"] = set()
    context.user_data["defects_custom"] = []
    return await ask_defects(update, context)


async def defect_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if not data.startswith("defect:"):
        return DEFECTS

    action = data.split(":", 1)[1]
    selected: set[int] = context.user_data.setdefault("defects_selected_idx", set())
    customs: List[str] = context.user_data.setdefault("defects_custom", [])

    if action == "back":
        context.user_data["defects_selected_idx"] = set()
        context.user_data["defects_custom"] = []
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await q.message.reply_text(
            step_text(6, "Состояние", "Оцените внешний вид устройства:"),
            parse_mode="HTML",
            reply_markup=CONDITION_KB,
        )
        return CONDITION

    if action == "done":
        if not selected and not customs:
            names = ["Нет дефектов"]
        elif DEFECT_NONE_IDX in selected and len(selected) == 1 and not customs:
            names = ["Нет дефектов"]
        else:
            names = [DEFECT_OPTIONS[i] for i in sorted(selected) if i not in {DEFECT_NONE_IDX, DEFECT_OTHER_IDX}]
            names.extend([f"Другие дефекты: {x}" for x in customs])
            if not names:
                names = ["Нет дефектов"]

        context.user_data["defects_selected"] = names
        context.user_data["photos"] = []
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await q.message.reply_text(
            step_text(8, "Фотографии", "Пришлите фото устройства.\nМожно отправить несколько фото.\n\nКогда закончите — нажмите «✅ Готово»."),
            parse_mode="HTML",
            reply_markup=DONE_PHOTO_KB,
        )
        return PHOTOS

    try:
        idx = int(action)
    except ValueError:
        return DEFECTS

    if idx == DEFECT_OTHER_IDX:
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await q.message.reply_text(
            "✏️ Опишите дефект подробнее:",
            reply_markup=ReplyKeyboardMarkup([[BACK, HOME]], resize_keyboard=True),
        )
        return DEFECTS_OTHER

    if idx == DEFECT_NONE_IDX:
        selected.clear()
        selected.add(DEFECT_NONE_IDX)
    else:
        selected.discard(DEFECT_NONE_IDX)
        if idx in selected:
            selected.remove(idx)
        else:
            selected.add(idx)

    context.user_data["defects_selected_idx"] = selected
    try:
        await q.edit_message_reply_markup(reply_markup=defects_kb(selected))
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise
    return DEFECTS


async def step_defects_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_defects(update, context)

    if len(text) < 2:
        await safe_reply(update, "Опишите дефект чуть подробнее.", reply_markup=ReplyKeyboardMarkup([[BACK, HOME]], resize_keyboard=True))
        return DEFECTS_OTHER

    context.user_data.setdefault("defects_custom", []).append(text)
    context.user_data.setdefault("defects_selected_idx", set()).add(DEFECT_OTHER_IDX)
    return await ask_defects(update, context)


async def step_photos_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    photo = update.message.photo[-1]
    context.user_data.setdefault("photos", []).append(photo.file_id)
    count = len(context.user_data["photos"])
    await safe_reply(update, f"✅ Фото {count} получено.\nПришлите ещё или нажмите «✅ Готово».", reply_markup=DONE_PHOTO_KB)
    return PHOTOS


async def step_photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await ask_city(update, context)


async def step_photos_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(update, "Пришлите фото или нажмите «✅ Готово».", reply_markup=DONE_PHOTO_KB)
    return PHOTOS


async def step_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_photos(update, context)
    if text not in CITY_OPTIONS:
        await safe_reply(update, "Выберите город кнопкой ниже.", reply_markup=CITY_KB)
        return CITY
    if text == "Другой город":
        await safe_reply(
            update,
            "Введите название города:",
            reply_markup=ReplyKeyboardMarkup([NAV_ROW], resize_keyboard=True),
        )
        return CITY_TEXT

    context.user_data["city"] = text
    return await ask_contact(update, context)


async def step_city_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_city(update, context)
    if len(text) < 2:
        await safe_reply(update, "Введите город текстом.", reply_markup=ReplyKeyboardMarkup([NAV_ROW], resize_keyboard=True))
        return CITY_TEXT

    context.user_data["city"] = text
    return await ask_contact(update, context)


async def step_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.contact:
        phone = update.message.contact.phone_number
        contact = phone if phone.startswith("+") else f"+{phone}"
    else:
        text = update.message.text.strip()
        if text == BACK:
            return await ask_city(update, context)
        if len(text) < 3:
            await safe_reply(update, "Введите номер телефона или Telegram для связи.", reply_markup=CONTACT_KB)
            return CONTACT
        contact = text

    context.user_data["contact"] = contact
    await submit_application(update, context)
    return ConversationHandler.END

# -----------------------------------------------------------------------------
# SUBMIT
# -----------------------------------------------------------------------------

async def submit_application(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ts = datetime.now().strftime("%d.%m.%Y %H:%M")
    app_id = next_app_id()

    device = context.user_data.get("device", "")
    model = context.user_data.get("model", "")
    full_model = f"{device} {model}".strip()

    photos = list(context.user_data.get("photos", []))
    defects = list(context.user_data.get("defects_selected", []))

    customer_before = get_customer(user.id)

    app_record = {
        "app_id": app_id,
        "date": ts,
        "user_id": user.id,
        "username": user.username or "",
        "full_name": user.full_name or "",
        "device": device,
        "model": model,
        "memory": context.user_data.get("memory", ""),
        "battery": context.user_data.get("battery", ""),
        "color": context.user_data.get("color", ""),
        "condition": context.user_data.get("condition", ""),
        "defects": defects,
        "photos": photos,
        "city": context.user_data.get("city", ""),
        "contact": context.user_data.get("contact", ""),
        "status": "new",
        "deal_price": None,
        "final_price": None,
    }

    # Clear first so user can restart even if admin notification is slow.
    context.user_data.clear()

    save_application(app_record)
    upsert_customer(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        app_id=app_id,
        date=ts,
        model=full_model,
    )

    success_caption = (
        f"🎉 <b>Заявка отправлена!</b>\n\n"
        f"🆔 Номер заявки: <b>{esc(app_id)}</b>\n\n"
        f"📨 Мы уже получили информацию об устройстве.\n"
        f"⏱ Обычно отвечаем в течение <b>5–15 минут</b>.\n\n"
        f"❤️ Спасибо, что выбрали <b>ZVER Store</b>."
    )

    if SUCCESS_IMAGE.exists():
        await update.message.reply_photo(
            photo=SUCCESS_IMAGE.open("rb"),
            caption=success_caption,
            parse_mode="HTML",
            reply_markup=MAIN_MENU,
        )
    else:
        await update.message.reply_text(
            success_caption,
            parse_mode="HTML",
            reply_markup=MAIN_MENU,
        )

    await notify_admin(context, app_record, customer_before)


def client_offer_kb(app_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, подходит", callback_data=f"client_offer:{app_id}:agree"),
        ],
        [
            InlineKeyboardButton("💬 Хочу обсудить", callback_data=f"client_offer:{app_id}:discuss"),
            InlineKeyboardButton("❌ Не подходит", callback_data=f"client_offer:{app_id}:decline"),
        ],
        [
            InlineKeyboardButton("☎️ Связаться с менеджером", url=f"https://t.me/{MANAGER_USERNAME}"),
        ],
    ])


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, app: Dict[str, Any], customer_before: Optional[Dict[str, Any]]) -> None:
    text = admin_card(app, customer_before)
    username = app.get("username") or ""

    try:
        if app.get("photos"):
            # Send photos as album first.
            media = []
            from telegram import InputMediaPhoto
            for i, file_id in enumerate(app["photos"][:10]):
                if i == 0:
                    media.append(InputMediaPhoto(media=file_id, caption=f"📷 Фото по заявке {app['app_id']}", parse_mode="HTML"))
                else:
                    media.append(InputMediaPhoto(media=file_id))
            await context.bot.send_media_group(chat_id=ADMIN_CHAT_ID_INT, media=media)

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID_INT,
            text=text,
            parse_mode="HTML",
            reply_markup=admin_status_kb(app["app_id"], username=username),
        )
    except Exception:
        logger.exception("Failed to send admin notification for %s", app.get("app_id"))


async def remind_unprocessed_application(context: ContextTypes.DEFAULT_TYPE) -> None:
    job_data = context.job.data or {}
    app_id = job_data.get("app_id")
    if not app_id:
        return

    app = get_application(app_id)
    if not app:
        return

    if app.get("status") not in {"new", "remind"}:
        return

    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID_INT,
            text=(
                f"⏰ <b>Напоминание по заявке</b>\n\n"
                f"🆔 <b>{esc(app_id)}</b>\n"
                f"Статус: {status_label(app.get('status', 'new'))}\n\n"
                f"Заявка висит уже 30 минут без обработки."
            ),
            parse_mode="HTML",
            reply_markup=admin_status_kb(app_id, username=app.get("username") or ""),
        )
    except Exception:
        logger.exception("Could not send reminder for %s", app_id)


# -----------------------------------------------------------------------------
# ADMIN HANDLERS
# -----------------------------------------------------------------------------

async def admin_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    parts = (q.data or "").split(":")
    if len(parts) != 3:
        return

    _, app_id, status = parts

    if status == "done":
        app_record = get_application(app_id)
        if not app_record:
            await q.answer("Заявка не найдена", show_alert=True)
            return

        context.bot_data.setdefault("pending_done_price_requests", {})[q.from_user.id] = app_id
        await q.message.reply_text(
            f"💰 <b>За какую сумму выкуплено устройство?</b>\n\n"
            f"Заявка: <b>{esc(app_id)}</b>\n\n"
            f"Например:\n"
            f"<code>35000</code>\n"
            f"<code>35000-38000</code>",
            parse_mode="HTML",
        )
        return

    app_record = patch_application(app_id, {"status": status})
    if not app_record:
        await q.answer("Заявка не найдена", show_alert=True)
        return

    try:
        old = q.message.text_html or q.message.text or ""
        marker = "<b>Статус:</b>"
        if marker in old:
            before = old.split(marker)[0]
            new_text = f"{before}<b>Статус:</b> {status_label(status)}"
        else:
            new_text = old + f"\n\n<b>Статус:</b> {status_label(status)}"

        await q.edit_message_text(
            text=new_text,
            parse_mode="HTML",
            reply_markup=admin_status_kb(app_id, username=app_record.get("username") or ""),
        )
    except Exception:
        logger.exception("Could not edit status message")

    user_id = app_record.get("user_id")

    # Notify client only on final/meaningful actions.
    if user_id and status == "working":
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"📌 <b>Заявка {esc(app_id)} в работе</b>\n\n"
                    f"Менеджер уже смотрит данные устройства.\n"
                    f"Скоро вернёмся с ответом."
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Could not notify client for %s", app_id)

    elif user_id and status == "rejected":
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"❌ <b>Заявка {esc(app_id)} отклонена</b>\n\n"
                    f"К сожалению, сейчас мы не готовы выкупить это устройство по заявленным данным.\n\n"
                    f"Если хотите уточнить детали — напишите менеджеру: @{MANAGER_USERNAME}"
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Could not notify client for %s", app_id)

    elif user_id and status == "done":
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ <b>Заявка {esc(app_id)} закрыта</b>\n\n"
                    f"Спасибо, что выбрали <b>ZVER Store</b> ❤️"
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Could not notify client for %s", app_id)

    elif status == "remind":
        try:
            context.job_queue.run_once(
                remind_unprocessed_application,
                when=30 * 60,
                data={"app_id": app_id},
                name=f"manual_reminder_{app_id}",
            )
        except Exception:
            logger.exception("Could not schedule manual reminder for %s", app_id)

    await q.answer(f"Статус: {status_label(status)}", show_alert=False)


def parse_price_offer(raw: str) -> Optional[str]:
    text = raw.strip().replace("—", "-").replace("–", "-").replace(" ", "")
    text = text.lower().replace("руб", "").replace("₽", "")

    multiplier = 1
    if "тыс" in text or "k" in text:
        multiplier = 1000
        text = text.replace("тыс.", "").replace("тыс", "").replace("k", "")

    if "-" in text:
        parts = [p for p in text.split("-") if p]
        if len(parts) != 2:
            return None
        try:
            a = int(float(parts[0].replace(",", ".")) * multiplier)
            b = int(float(parts[1].replace(",", ".")) * multiplier)
        except ValueError:
            return None
        if a < 1000 or b < 1000 or b < a:
            return None
        return f"{a:,}–{b:,}".replace(",", " ")

    try:
        value = int(float(text.replace(",", ".")) * multiplier)
    except ValueError:
        return None

    if value < 1000:
        return None

    return f"{value:,}".replace(",", " ")


async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "💰 Как предложить цену:\n\n"
            "<code>/price ZV-00001 35000</code>\n"
            "<code>/price ZV-00001 35000-40000</code>",
            parse_mode="HTML",
        )
        return

    app_id = context.args[0].strip()
    raw_price = " ".join(context.args[1:]).strip()
    price = parse_price_offer(raw_price)
    if not price:
        await update.message.reply_text("Введите сумму от 1 000 ₽. Например: 35000 или 35000-38000")
        return

    app_record = patch_application(app_id, {"status": "price_sent", "deal_price": price})
    if not app_record:
        await update.message.reply_text("❌ Заявка не найдена.")
        return

    user_id = app_record.get("user_id")
    if not user_id:
        await update.message.reply_text("❌ У заявки нет user_id.")
        return

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"💰 <b>Предварительная оценка по заявке {esc(app_id)}</b>\n\n"
                f"По информации и фотографиям мы готовы предложить:\n"
                f"<b>{esc(price)} ₽</b>\n\n"
                f"💡 Мы ценим честность и всегда стараемся сохранить предварительную оценку. "
                f"Если устройство соответствует описанию и фотографиям, стоимость, как правило, остаётся без изменений.\n\n"
                f"Подходит ли вам такая предварительная оценка?"
            ),
            parse_mode="HTML",
            reply_markup=client_offer_kb(app_id),
        )
        await update.message.reply_text(f"✅ Предложение отправлено клиенту: {app_id} — {price} ₽")
    except Exception:
        logger.exception("Could not send price offer for %s", app_id)
        await update.message.reply_text("❌ Не удалось отправить предложение клиенту.")


async def admin_hint_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    parts = (q.data or "").split(":")
    if len(parts) != 3:
        return

    _, app_id, action = parts
    if action == "price":
        context.bot_data.setdefault("pending_price_requests", {})[q.from_user.id] = app_id
        await q.message.reply_text(
            f"💰 <b>Введите сумму или диапазон по заявке {esc(app_id)}</b>\n\n"
            f"Можно написать так:\n"
            f"<code>35000</code>\n"
            f"<code>35000-38000</code>\n"
            f"<code>35-38 тыс</code>\n\n"
            f"Минимальная сумма — <b>от 1 000 ₽</b>.",
            parse_mode="HTML",
        )


async def admin_done_price_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    pending = context.bot_data.setdefault("pending_done_price_requests", {})
    app_id = pending.get(update.effective_user.id)

    if not app_id:
        return False

    raw = update.message.text.strip()
    price = parse_price_offer(raw)

    if not price:
        await update.message.reply_text(
            "Введите сумму от 1 000 ₽.\n\n"
            "Например:\n"
            "<code>35000</code>\n"
            "<code>35000-38000</code>",
            parse_mode="HTML",
        )
        return True

    pending.pop(update.effective_user.id, None)

    app_record = patch_application(app_id, {"status": "done", "final_price": price})
    if not app_record:
        await update.message.reply_text("❌ Заявка не найдена.")
        return True

    await update.message.reply_text(
        f"✅ <b>Заявка закрыта как выкупленная</b>\n\n"
        f"🆔 <b>{esc(app_id)}</b>\n"
        f"💰 Финальная цена: <b>{esc(price)} ₽</b>",
        parse_mode="HTML",
    )

    user_id = app_record.get("user_id")
    if user_id:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ <b>Сделка по заявке {esc(app_id)} завершена</b>\n\n"
                    f"Спасибо, что выбрали <b>ZVER Store</b> ❤️"
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Could not notify client about done status for %s", app_id)

    return True


async def admin_price_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await admin_done_price_text_handler(update, context):
        return

    pending = context.bot_data.setdefault("pending_price_requests", {})
    app_id = pending.get(update.effective_user.id)

    if not app_id:
        return

    raw = update.message.text.strip()
    price = parse_price_offer(raw)

    if not price:
        await update.message.reply_text(
            "Введите сумму от 1 000 ₽.\n\n"
            "Например:\n"
            "<code>35000</code>\n"
            "<code>35000-38000</code>\n"
            "<code>35-38 тыс</code>",
            parse_mode="HTML",
        )
        return

    pending.pop(update.effective_user.id, None)

    app_record = patch_application(app_id, {"status": "price_sent", "deal_price": price})
    if not app_record:
        await update.message.reply_text("❌ Заявка не найдена.")
        return

    user_id = app_record.get("user_id")
    if not user_id:
        await update.message.reply_text("❌ У заявки нет user_id.")
        return

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"💰 <b>Предварительная оценка по заявке {esc(app_id)}</b>\n\n"
                f"По информации и фотографиям мы готовы предложить:\n"
                f"<b>{esc(price)} ₽</b>\n\n"
                f"💡 Мы ценим честность и всегда стараемся сохранить предварительную оценку. "
                f"Если устройство соответствует описанию и фотографиям, стоимость, как правило, остаётся без изменений.\n\n"
                f"Подходит ли вам такая предварительная оценка?"
            ),
            parse_mode="HTML",
            reply_markup=client_offer_kb(app_id),
        )
        await update.message.reply_text(f"✅ Предложение отправлено клиенту: {app_id} — {price} ₽")
    except Exception:
        logger.exception("Could not send price offer for %s", app_id)
        await update.message.reply_text("❌ Не удалось отправить предложение клиенту.")


async def client_offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    parts = (q.data or "").split(":")
    if len(parts) != 3:
        return

    _, app_id, action = parts
    status_map = {
        "agree": "client_agreed",
        "discuss": "client_discuss",
        "decline": "client_declined",
    }
    status = status_map.get(action, "client_declined")
    app_record = patch_application(app_id, {"status": status})

    if action == "agree":
        await q.edit_message_text(
            f"✅ <b>Спасибо!</b>\n\n"
            f"Вы согласились с предварительной оценкой по заявке <b>{esc(app_id)}</b>.\n"
            f"Менеджер скоро свяжется с вами для согласования деталей.",
            parse_mode="HTML",
        )
    elif action == "discuss":
        await q.edit_message_text(
            f"💬 <b>Хорошо, обсудим</b>\n\n"
            f"Менеджер получил ваш ответ по заявке <b>{esc(app_id)}</b> и свяжется с вами, чтобы обсудить стоимость.",
            parse_mode="HTML",
        )
    else:
        await q.edit_message_text(
            f"❌ <b>Поняли</b>\n\n"
            f"Вы отказались от предварительной оценки по заявке <b>{esc(app_id)}</b>.\n"
            f"Если захотите обсудить условия — напишите менеджеру: @{MANAGER_USERNAME}",
            parse_mode="HTML",
        )

    if app_record:
        icon = "✅" if action == "agree" else "💬" if action == "discuss" else "❌"
        title = "Клиент согласился" if action == "agree" else "Клиент хочет обсудить" if action == "discuss" else "Клиент отказался"
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID_INT,
                text=(
                    f"{icon} <b>{title}</b>\n\n"
                    f"🆔 <b>{esc(app_id)}</b>\n"
                    f"Статус: {status_label(status)}\n"
                    f"Предложение: <b>{esc(app_record.get('deal_price'))} ₽</b>"
                ),
                parse_mode="HTML",
                reply_markup=admin_status_kb(app_id, username=app_record.get("username") or ""),
            )
        except Exception:
            logger.exception("Could not notify admin about client response %s", app_id)


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats = list_stats()
    statuses = stats["statuses"]
    status_lines = "\n".join(f"• {status_label(k)}: {v}" for k, v in statuses.items()) or "—"

    await safe_reply(
        update,
        f"📊 <b>Статистика ZVER</b>\n\n"
        f"Заявок всего: <b>{stats['apps_total']}</b>\n"
        f"Клиентов всего: <b>{stats['customers_total']}</b>\n\n"
        f"<b>По статусам:</b>\n{status_lines}",
        reply_markup=MAIN_MENU if update.effective_chat.type == "private" else None,
    )


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"Chat ID: <code>{esc(update.effective_chat.id)}</code>\n"
        f"User ID: <code>{esc(update.effective_user.id)}</code>",
        parse_mode="HTML",
    )

# -----------------------------------------------------------------------------
# ERRORS
# -----------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception", exc_info=context.error)

# -----------------------------------------------------------------------------
# APPLICATION
# -----------------------------------------------------------------------------

def build_app() -> Application:
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^.*Продать устройство.*$"), sell_start),
        ],
        states={
            DEVICE: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(PRIVATE_TEXT, step_device),
            ],
            MODEL: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(PRIVATE_TEXT, step_model),
            ],
            MODEL_TEXT: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(PRIVATE_TEXT, step_model_text),
            ],
            MEMORY: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(PRIVATE_TEXT, step_memory),
            ],
            BATTERY: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(PRIVATE_TEXT, step_battery),
            ],
            COLOR: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(PRIVATE_TEXT, step_color),
            ],
            CONDITION: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(PRIVATE_TEXT, step_condition),
            ],
            DEFECTS: [
                CallbackQueryHandler(defect_callback, pattern=r"^defect:"),
                MessageHandler(HOME_RE, go_home),
                MessageHandler(BACK_RE, lambda u, c: ask_condition(u, c)),
            ],
            DEFECTS_OTHER: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(PRIVATE_TEXT, step_defects_other),
            ],
            PHOTOS: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(filters.ChatType.PRIVATE & filters.PHOTO, step_photos_receive),
                MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^✅ Готово$"), step_photos_done),
                MessageHandler(BACK_RE, lambda u, c: ask_defects(u, c)),
                MessageHandler(filters.ChatType.PRIVATE & filters.ALL, step_photos_invalid),
            ],
            CITY: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(PRIVATE_TEXT, step_city),
            ],
            CITY_TEXT: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(PRIVATE_TEXT, step_city_text),
            ],
            CONTACT: [
                MessageHandler(HOME_RE, go_home),
                MessageHandler(filters.ChatType.PRIVATE & filters.CONTACT, step_contact),
                MessageHandler(PRIVATE_TEXT, step_contact),
            ],
        },
        fallbacks=[
            MessageHandler(HOME_RE, go_home),
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
        name="sell_conversation",
        persistent=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern=r"^check_subscription$"))
    app.add_handler(CallbackQueryHandler(admin_status_callback, pattern=r"^status:"))
    app.add_handler(CallbackQueryHandler(admin_hint_callback, pattern=r"^admin_hint:"))
    app.add_handler(CallbackQueryHandler(client_offer_callback, pattern=r"^client_offer:"))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, admin_price_text_handler))

    app.add_handler(conv)

    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^.*Узнать стоимость.*$"), price_info))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^.*Связаться с менеджером.*$"), contact_manager))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^.*Канал ZVER.*$"), channel_info))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & HOME_RE, go_home))

    app.add_error_handler(error_handler)
    return app


def main() -> None:
    logger.info("Starting ZVER Store Bot v2...")
    logger.info("Admin chat: %s", ADMIN_CHAT_ID)
    application = build_app()
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()

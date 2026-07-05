"""
ZVER Store — Telegram buyback bot.

ENV:
  TELEGRAM_BOT_TOKEN=...
  ADMIN_CHAT_ID=...
Optional:
  CHANNEL_USERNAME=zver_channel_without_at
  CHANNEL_ID=@zver_channel_or_numeric_id
  MANAGER_USERNAME=username_without_at

Files:
  assets/welcome.png
  assets/success.png
"""

from __future__ import annotations

import html
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, Forbidden, TelegramError
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
# CONFIG
# -----------------------------------------------------------------------------

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TOKEN") or ""
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
CHANNEL_USERNAME = (os.getenv("CHANNEL_USERNAME") or "zverstore").strip().lstrip("@")
CHANNEL_ID = (os.getenv("CHANNEL_ID") or f"@{CHANNEL_USERNAME}").strip()
MANAGER_USERNAME = (os.getenv("MANAGER_USERNAME") or "zverstore").strip().lstrip("@")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is empty. Add it to .env")

try:
    ADMIN_CHAT_ID_INT = int(ADMIN_CHAT_ID)
except Exception as exc:
    raise RuntimeError("ADMIN_CHAT_ID must be numeric, for example -1001234567890") from exc

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

APPLICATIONS_FILE = DATA_DIR / "applications.json"
CUSTOMERS_FILE = DATA_DIR / "customers.json"
COUNTER_FILE = DATA_DIR / "counter.json"

WELCOME_IMAGE = ASSETS_DIR / "welcome.png"
SUCCESS_IMAGE = ASSETS_DIR / "success.png"

logging.basicConfig(
    format="%(asctime)s,%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("zver-bot-v1-final")

# -----------------------------------------------------------------------------
# STATES
# -----------------------------------------------------------------------------

(
    DEVICE,
    MODEL_IPHONE,
    MODEL_TEXT,
    MEMORY,
    BATTERY,
    COLOR,
    CONDITION,
    DEFECTS,
    PHOTOS,
    CITY,
    CONTACT,
) = range(11)

TOTAL_STEPS = 10
BACK = "⬅️ Назад"
HOME = "🏠 Главное меню"

DEVICE_OPTIONS = {"iPhone", "iPad", "MacBook", "Apple Watch", "AirPods", "Другое"}
MEMORY_OPTIONS = {"64 GB", "128 GB", "256 GB", "512 GB", "1 TB", "Другая"}
BATTERY_OPTIONS = {"100–95%", "94–90%", "89–85%", "84–80%", "Меньше 80%", "Не знаю"}
COLOR_OPTIONS = {"Чёрный", "Белый", "Серый", "Синий", "Зелёный", "Золотой", "Фиолетовый", "Другой"}
CONDITION_OPTIONS = {"Отличное", "Хорошее", "Среднее", "Плохое", "После ремонта", "Не включается"}

IPHONE_MODELS = [
    "iPhone X", "iPhone XR", "iPhone XS", "iPhone XS Max",
    "iPhone 11", "iPhone 11 Pro", "iPhone 11 Pro Max",
    "iPhone 12", "iPhone 12 mini", "iPhone 12 Pro", "iPhone 12 Pro Max",
    "iPhone 13", "iPhone 13 mini", "iPhone 13 Pro", "iPhone 13 Pro Max",
    "iPhone 14", "iPhone 14 Plus", "iPhone 14 Pro", "iPhone 14 Pro Max",
    "iPhone 15", "iPhone 15 Plus", "iPhone 15 Pro", "iPhone 15 Pro Max",
    "iPhone 16", "iPhone 16 Plus", "iPhone 16 Pro", "iPhone 16 Pro Max",
    "iPhone 17", "iPhone 17 Plus", "iPhone 17 Pro", "iPhone 17 Pro Max",
    "Другая модель",
]

DEFECT_OPTIONS = [
    "✅ Дефектов нет",
    "💥 Разбит экран",
    "📱 Разбита задняя крышка",
    "🧱 Сколы/вмятины корпуса",
    "🟦 Пятна/полосы на экране",
    "👆 Не работает Face ID / Touch ID",
    "📷 Камера не работает",
    "🔊 Динамик/микрофон не работает",
    "🔌 Не заряжается",
    "📶 Проблемы с сетью/Wi‑Fi",
    "💧 После воды",
    "🔧 После ремонта",
    "⚠️ Другое",
]

# -----------------------------------------------------------------------------
# STORAGE
# -----------------------------------------------------------------------------

def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Could not read JSON: %s", path)
        return default


def write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def next_app_id() -> str:
    data = read_json(COUNTER_FILE, {"last": 0})
    last = int(data.get("last", 0)) + 1
    write_json(COUNTER_FILE, {"last": last})
    return f"ZV-{last:05d}"


def save_customer(user: Any) -> None:
    customers = read_json(CUSTOMERS_FILE, {})
    uid = str(user.id)
    customers[uid] = {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_json(CUSTOMERS_FILE, customers)


def save_application(app: Dict[str, Any]) -> None:
    apps = read_json(APPLICATIONS_FILE, [])
    apps.append(app)
    write_json(APPLICATIONS_FILE, apps)


def get_application(app_id: str) -> Optional[Dict[str, Any]]:
    apps = read_json(APPLICATIONS_FILE, [])
    for app in apps:
        if app.get("app_id") == app_id:
            return app
    return None


def patch_application(app_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    apps = read_json(APPLICATIONS_FILE, [])
    updated = None
    for app in apps:
        if app.get("app_id") == app_id:
            app.update(updates)
            updated = app
            break
    write_json(APPLICATIONS_FILE, apps)
    return updated


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


# -----------------------------------------------------------------------------
# KEYBOARDS
# -----------------------------------------------------------------------------

def reply_kb(rows: List[List[str]], resize: bool = True) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(rows, resize_keyboard=resize)


MAIN_MENU = reply_kb([
    ["📱 Продать устройство", "💰 Узнать стоимость"],
    ["☎️ Связаться с менеджером", "📢 Канал ZVER"],
])

NAV_ROW = [BACK, HOME]

DEVICE_KB = reply_kb([
    ["📱 iPhone", "📱 iPad"],
    ["💻 MacBook", "⌚ Apple Watch"],
    ["🎧 AirPods", "📦 Другое"],
    [HOME],
])

IPHONE_MODEL_KB = reply_kb([
    ["iPhone X", "iPhone XR"],
    ["iPhone XS", "iPhone XS Max"],
    ["iPhone 11", "iPhone 11 Pro"],
    ["iPhone 11 Pro Max", "iPhone 12"],
    ["iPhone 12 Pro", "iPhone 12 Pro Max"],
    ["iPhone 13", "iPhone 13 Pro"],
    ["iPhone 13 Pro Max", "iPhone 14"],
    ["iPhone 14 Pro", "iPhone 14 Pro Max"],
    ["iPhone 15", "iPhone 15 Pro"],
    ["iPhone 15 Pro Max", "iPhone 16"],
    ["iPhone 16 Pro", "iPhone 16 Pro Max"],
    ["iPhone 17", "iPhone 17 Pro"],
    ["iPhone 17 Pro Max", "Другая модель"],
    NAV_ROW,
])

MEMORY_KB = reply_kb([
    ["💾 64 GB", "💿 128 GB", "📀 256 GB"],
    ["🚀 512 GB", "💎 1 TB", "🌈 Другая"],
    NAV_ROW,
])

BATTERY_KB = reply_kb([
    ["🔋 100–95%", "🔋 94–90%"],
    ["🔋 89–85%", "🔋 84–80%"],
    ["🔋 Меньше 80%", "❓ Не знаю"],
    NAV_ROW,
])

COLOR_KB = reply_kb([
    ["⚫ Чёрный", "⚪ Белый", "⚙️ Серый"],
    ["🔵 Синий", "🟢 Зелёный", "🟡 Золотой"],
    ["🟣 Фиолетовый", "🌈 Другой"],
    NAV_ROW,
])

CONDITION_KB = reply_kb([
    ["✨ Отличное", "👍 Хорошее"],
    ["😐 Среднее", "⚠️ Плохое"],
    ["🔧 После ремонта", "❌ Не включается"],
    NAV_ROW,
])

PHOTO_KB = reply_kb([
    ["✅ Готово"],
    NAV_ROW,
])

CONTACT_KB = ReplyKeyboardMarkup([
    [KeyboardButton("📲 Отправить мой контакт", request_contact=True)],
    NAV_ROW,
], resize_keyboard=True)

def defect_kb(selected: Set[int]) -> ReplyKeyboardMarkup:
    rows: List[List[str]] = []
    for idx, item in enumerate(DEFECT_OPTIONS):
        mark = "☑️ " if idx in selected else ""
        rows.append([mark + item])
    rows.append(["✅ Готово"])
    rows.append(NAV_ROW)
    return reply_kb(rows)


def channel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")],
    ])


def admin_status_kb(app_id: str, username: str = "") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("💰 Предложить цену", callback_data=f"admin_hint:{app_id}:price")],
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


def client_offer_kb(app_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, подходит", callback_data=f"client_offer:{app_id}:agree")],
        [
            InlineKeyboardButton("💬 Хочу обсудить", callback_data=f"client_offer:{app_id}:discuss"),
            InlineKeyboardButton("❌ Не подходит", callback_data=f"client_offer:{app_id}:decline"),
        ],
        [InlineKeyboardButton("☎️ Связаться с менеджером", url=f"https://t.me/{MANAGER_USERNAME}")],
    ])


# -----------------------------------------------------------------------------
# TEXT HELPERS
# -----------------------------------------------------------------------------

def clean_choice(text: str) -> str:
    prefixes = [
        "📱 ", "📦 ", "💻 ", "⌚ ", "🎧 ",
        "💾 ", "💿 ", "📀 ", "🚀 ", "💎 ", "🌈 ",
        "🔋 ", "❓ ", "⚫ ", "⚪ ", "⚙️ ", "🔵 ", "🟢 ", "🟡 ", "🟣 ",
        "✨ ", "👍 ", "😐 ", "⚠️ ", "🔧 ", "❌ ",
    ]
    text = text.strip()
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def status_label(status: str) -> str:
    return {
        "new": "🟢 Новая заявка",
        "working": "📌 В работе",
        "done": "✅ Выкуплено",
        "rejected": "❌ Отказ",
        "remind": "⏰ Напомнить позже",
        "price_sent": "💰 Цена предложена",
        "client_agreed": "✅ Клиент согласен",
        "client_discuss": "💬 Клиент хочет обсудить",
        "client_declined": "❌ Клиент отказался",
    }.get(status, status)


def step_text(n: int, title: str, question: str) -> str:
    screens = {
        "Тип устройства": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "💚 <b>Покупаем устройства Apple практически в любом состоянии.</b>\n\n"
            "Мы регулярно покупаем:\n\n"
            "📱 модели прошлых лет (от iPhone X и новее);\n"
            "💥 с разбитым экраном;\n"
            "📱 с трещинами на корпусе или задней крышке;\n"
            "🔧 после ремонта;\n"
            "🔋 с любой ёмкостью аккумулятора;\n"
            "⚠️ с любыми неисправностями и дефектами.\n\n"
            "✨ Чем честнее вы опишете состояние устройства, тем точнее будет предварительная оценка.\n\n"
            "🤝 Даже если сомневаетесь, подходит ли ваше устройство — просто отправьте заявку. Мы обязательно её рассмотрим.\n\n"
            "👇 Выберите устройство ниже."
        ),
        "Модель iPhone": (
            f"🍏 <b>ZVER Store</b>\n\n"
            f"📍 <b>Шаг {n}/{TOTAL_STEPS}</b>\n\n"
            "📱 <b>Модель iPhone</b>\n\n"
            "Выберите точную модель устройства.\n\n"
            "✅ В списке есть модели от <b>iPhone X</b> до <b>iPhone 17 Pro Max</b>."
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


async def safe_reply(update: Update, text: str, reply_markup: Any = None) -> None:
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    elif update.callback_query and update.callback_query.message:
        await update.callback_query.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def ask_device(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(update, step_text(1, "Тип устройства", ""), DEVICE_KB)
    return DEVICE


async def ask_iphone_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(update, step_text(2, "Модель iPhone", ""), IPHONE_MODEL_KB)
    return MODEL_IPHONE


async def ask_model_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(update, step_text(2, "Модель", ""), reply_kb([NAV_ROW]))
    return MODEL_TEXT


async def ask_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(update, step_text(3, "Память", ""), MEMORY_KB)
    return MEMORY


async def ask_battery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(update, step_text(4, "АКБ", ""), BATTERY_KB)
    return BATTERY


async def ask_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(update, step_text(5, "Цвет", ""), COLOR_KB)
    return COLOR


async def ask_condition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(update, step_text(6, "Состояние", ""), CONDITION_KB)
    return CONDITION


async def ask_defects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected = context.user_data.setdefault("defects_selected_idx", set())
    await safe_reply(update, step_text(7, "Дефекты", ""), defect_kb(selected))
    return DEFECTS


async def ask_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.setdefault("photos", [])
    await safe_reply(update, step_text(8, "Фотографии", ""), PHOTO_KB)
    return PHOTOS


async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(update, step_text(9, "Город", ""), reply_kb([NAV_ROW]))
    return CITY


async def ask_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_reply(update, step_text(10, "Контакт", ""), CONTACT_KB)
    return CONTACT


# -----------------------------------------------------------------------------
# SUBSCRIPTION
# -----------------------------------------------------------------------------

async def is_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not CHANNEL_ID:
        return True
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }
    except (BadRequest, Forbidden) as exc:
        logger.warning("Subscription check failed: %s", exc)
        return True
    except TelegramError:
        logger.exception("Subscription check error")
        return True


async def ensure_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False
    if await is_subscribed(user.id, context):
        return True

    text = (
        "📢 Для подачи заявки подпишитесь на канал ZVER.\n\n"
        "После подписки нажмите кнопку проверки."
    )
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=channel_kb())
    else:
        await update.message.reply_text(text, reply_markup=channel_kb())
    return False


async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if await is_subscribed(q.from_user.id, context):
        await q.message.reply_text("✅ Подписка подтверждена.", reply_markup=MAIN_MENU)
    else:
        await q.message.reply_text("Пока не вижу подписку. Подпишитесь и нажмите проверку ещё раз.", reply_markup=channel_kb())


# -----------------------------------------------------------------------------
# CLIENT HANDLERS
# -----------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if not await ensure_subscription(update, context):
        return
    if update.effective_user:
        save_customer(update.effective_user)

    caption = (
        "🍏 <b>ZVER Store</b>\n\n"
        "💰 <b>Быстрый выкуп техники Apple</b>\n\n"
        "⚡ Предварительная оценка за <b>5–15 минут</b>\n"
        "📱 Покупаем большинство устройств Apple — от <b>iPhone X</b> до последних моделей\n"
        "🤝 Вы сами решаете, подходит ли вам наше предложение\n"
        "📸 Заполнение займёт около минуты\n\n"
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
        await update.message.reply_text(caption, parse_mode="HTML", reply_markup=MAIN_MENU)


async def price_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await safe_reply(
        update,
        "💰 <b>Узнать стоимость</b>\n\n"
        "Для предварительной оценки заполните короткую анкету и прикрепите фото устройства.\n\n"
        "⚡ Обычно отвечаем за <b>5–15 минут</b>.\n"
        "🤝 Решение о продаже всегда остаётся за вами.",
        MAIN_MENU,
    )


async def contact_manager(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await safe_reply(
        update,
        f"☎️ <b>Связаться с менеджером</b>\n\n"
        f"Напишите: @{MANAGER_USERNAME}\n\n"
        f"💡 Если хотите продать устройство — лучше сначала заполнить анкету. Так менеджер сразу увидит данные и фото.",
        MAIN_MENU,
    )


async def channel_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await safe_reply(
        update,
        "📢 <b>Канал ZVER</b>\n\n"
        "Там будут отзывы, кейсы, поступления устройств и развитие проекта.",
        MAIN_MENU,
    )


async def begin_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if not await ensure_subscription(update, context):
        return ConversationHandler.END
    context.user_data["started_at"] = datetime.now().isoformat(timespec="seconds")
    return await ask_device(update, context)


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
    await safe_reply(update, text, MAIN_MENU)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await safe_reply(update, "Ок, заявка отменена.", MAIN_MENU)
    return ConversationHandler.END


async def back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    stack = context.user_data.get("state_stack", [])
    if stack:
        prev = stack.pop()
        context.user_data["state_stack"] = stack
    else:
        prev = DEVICE

    if prev == DEVICE:
        return await ask_device(update, context)
    if prev == MODEL_IPHONE:
        return await ask_iphone_model(update, context)
    if prev == MODEL_TEXT:
        return await ask_model_text(update, context)
    if prev == MEMORY:
        return await ask_memory(update, context)
    if prev == BATTERY:
        return await ask_battery(update, context)
    if prev == COLOR:
        return await ask_color(update, context)
    if prev == CONDITION:
        return await ask_condition(update, context)
    if prev == DEFECTS:
        return await ask_defects(update, context)
    if prev == PHOTOS:
        return await ask_photos(update, context)
    if prev == CITY:
        return await ask_city(update, context)
    return await ask_device(update, context)


def push_state(context: ContextTypes.DEFAULT_TYPE, state: int) -> None:
    context.user_data.setdefault("state_stack", []).append(state)


async def step_device(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_choice(update.message.text)
    if text == HOME:
        return await go_home(update, context)

    if text not in DEVICE_OPTIONS:
        await safe_reply(update, "Выберите устройство кнопкой ниже.", DEVICE_KB)
        return DEVICE

    context.user_data["device_type"] = text
    push_state(context, DEVICE)
    if text == "iPhone":
        return await ask_iphone_model(update, context)
    return await ask_model_text(update, context)


async def step_iphone_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == HOME:
        return await go_home(update, context)
    if text == BACK:
        return await back(update, context)

    if text not in IPHONE_MODELS:
        await safe_reply(update, "Выберите модель кнопкой ниже.", IPHONE_MODEL_KB)
        return MODEL_IPHONE

    if text == "Другая модель":
        push_state(context, MODEL_IPHONE)
        return await ask_model_text(update, context)

    context.user_data["model"] = text
    push_state(context, MODEL_IPHONE)
    return await ask_memory(update, context)


async def step_model_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == HOME:
        return await go_home(update, context)
    if text == BACK:
        return await back(update, context)
    if len(text) < 2:
        await safe_reply(update, "Введите модель текстом.", reply_kb([NAV_ROW]))
        return MODEL_TEXT

    context.user_data["model"] = text
    push_state(context, MODEL_TEXT)
    return await ask_memory(update, context)


async def step_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_choice(update.message.text)
    if text == HOME:
        return await go_home(update, context)
    if text == BACK:
        return await back(update, context)
    if text not in MEMORY_OPTIONS:
        await safe_reply(update, "Выберите память кнопкой ниже.", MEMORY_KB)
        return MEMORY
    context.user_data["memory"] = text
    push_state(context, MEMORY)
    return await ask_battery(update, context)


async def step_battery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_choice(update.message.text)
    if text == HOME:
        return await go_home(update, context)
    if text == BACK:
        return await back(update, context)
    if text not in BATTERY_OPTIONS:
        await safe_reply(update, "Выберите вариант АКБ кнопкой ниже.", BATTERY_KB)
        return BATTERY
    context.user_data["battery"] = text
    push_state(context, BATTERY)
    return await ask_color(update, context)


async def step_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_choice(update.message.text)
    if text == HOME:
        return await go_home(update, context)
    if text == BACK:
        return await back(update, context)
    if text not in COLOR_OPTIONS:
        await safe_reply(update, "Выберите цвет кнопкой ниже.", COLOR_KB)
        return COLOR
    context.user_data["color"] = text
    push_state(context, COLOR)
    return await ask_condition(update, context)


async def step_condition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clean_choice(update.message.text)
    if text == HOME:
        return await go_home(update, context)
    if text == BACK:
        return await back(update, context)
    if text not in CONDITION_OPTIONS:
        await safe_reply(update, "Выберите состояние кнопкой ниже.", CONDITION_KB)
        return CONDITION
    display = {
        "Отличное": "✨ Отличное",
        "Хорошее": "👍 Хорошее",
        "Среднее": "😐 Среднее",
        "Плохое": "⚠️ Плохое",
        "После ремонта": "🔧 После ремонта",
        "Не включается": "❌ Не включается",
    }[text]
    context.user_data["condition"] = display
    context.user_data["defects_selected_idx"] = set()
    push_state(context, CONDITION)
    return await ask_defects(update, context)


async def step_defects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == HOME:
        return await go_home(update, context)
    if raw == BACK:
        return await back(update, context)
    selected: Set[int] = context.user_data.setdefault("defects_selected_idx", set())

    if raw == "✅ Готово":
        context.user_data["defects"] = [DEFECT_OPTIONS[i] for i in sorted(selected)] or ["Не указано"]
        push_state(context, DEFECTS)
        return await ask_photos(update, context)

    cleaned = raw.replace("☑️ ", "", 1).strip()
    if cleaned not in DEFECT_OPTIONS:
        await safe_reply(update, "Выберите вариант из списка или нажмите «✅ Готово».", defect_kb(selected))
        return DEFECTS

    idx = DEFECT_OPTIONS.index(cleaned)
    if idx == 0:
        selected.clear()
        selected.add(0)
    else:
        selected.discard(0)
        if idx in selected:
            selected.remove(idx)
        else:
            selected.add(idx)

    context.user_data["defects_selected_idx"] = selected
    await safe_reply(update, "Отметьте всё, что есть.\n\n☑️ Можно выбрать несколько вариантов.", defect_kb(selected))
    return DEFECTS


async def step_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text:
        text = update.message.text.strip()
        if text == HOME:
            return await go_home(update, context)
        if text == BACK:
            return await back(update, context)
        if text == "✅ Готово":
            push_state(context, PHOTOS)
            return await ask_city(update, context)
        await safe_reply(update, "Загрузите фото или нажмите «✅ Готово».", PHOTO_KB)
        return PHOTOS

    if update.message.photo:
        photo = update.message.photo[-1]
        context.user_data.setdefault("photos", []).append(photo.file_id)
        await safe_reply(update, f"📸 Фото добавлено. Всего: {len(context.user_data['photos'])}\n\nКогда закончите — нажмите «✅ Готово».", PHOTO_KB)
        return PHOTOS

    await safe_reply(update, "Загрузите фото или нажмите «✅ Готово».", PHOTO_KB)
    return PHOTOS


async def step_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == HOME:
        return await go_home(update, context)
    if text == BACK:
        return await back(update, context)
    if len(text) < 2:
        await safe_reply(update, "Введите город текстом.", reply_kb([NAV_ROW]))
        return CITY

    context.user_data["city"] = text
    push_state(context, CITY)
    return await ask_contact(update, context)


async def step_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.contact:
        phone = update.message.contact.phone_number
        contact = phone if phone.startswith("+") else f"+{phone}"
    else:
        text = update.message.text.strip()
        if text == HOME:
            return await go_home(update, context)
        if text == BACK:
            return await back(update, context)
        contact = text

    if len(contact) < 3:
        await safe_reply(update, "Оставьте номер телефона или Telegram.", CONTACT_KB)
        return CONTACT

    context.user_data["contact"] = contact
    await submit_application(update, context)
    context.user_data.clear()
    return ConversationHandler.END


# -----------------------------------------------------------------------------
# APPLICATION SUBMIT / ADMIN
# -----------------------------------------------------------------------------

def admin_application_text(app: Dict[str, Any]) -> str:
    defects = app.get("defects") or []
    defects_text = "\n".join(f"• {esc(d)}" for d in defects) if defects else "• Не указано"

    lines = [
        f"🍏 <b>ZVER Store</b>",
        "",
        f"🟢 <b>Новая заявка</b> 🆔 <b>{esc(app.get('app_id'))}</b>",
        f"🕘 {esc(app.get('created_at'))}",
        "",
        f"📱 <b>Устройство:</b> {esc(app.get('model') or app.get('device_type'))}",
        f"💾 <b>Память:</b> {esc(app.get('memory'))}",
        f"🔋 <b>АКБ:</b> {esc(app.get('battery'))}",
        f"🎨 <b>Цвет:</b> {esc(app.get('color'))}",
        f"⭐ <b>Состояние:</b> {esc(app.get('condition'))}",
        "",
        f"⚠️ <b>Дефекты:</b>",
        defects_text,
        "",
        f"📸 <b>Фото:</b> {len(app.get('photos') or [])} шт.",
        f"📍 <b>Город:</b> {esc(app.get('city'))}",
        f"☎️ <b>Контакт:</b> {esc(app.get('contact'))}",
    ]
    if app.get("username"):
        lines.append(f"💬 <b>Telegram:</b> @{esc(app.get('username'))}")
    if app.get("deal_price"):
        lines.append(f"💰 <b>Предложение:</b> {esc(app.get('deal_price'))} ₽")
    if app.get("final_price"):
        lines.append(f"✅ <b>Финальная цена:</b> {esc(app.get('final_price'))} ₽")
    lines.extend(["", f"<b>Статус:</b> {status_label(app.get('status', 'new'))}"])
    return "\n".join(lines)


async def submit_application(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    app_id = next_app_id()

    app_record = {
        "app_id": app_id,
        "status": "new",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "user_id": user.id if user else None,
        "username": user.username if user else None,
        "first_name": user.first_name if user else None,
        "device_type": context.user_data.get("device_type"),
        "model": context.user_data.get("model"),
        "memory": context.user_data.get("memory"),
        "battery": context.user_data.get("battery"),
        "color": context.user_data.get("color"),
        "condition": context.user_data.get("condition"),
        "defects": context.user_data.get("defects", []),
        "photos": context.user_data.get("photos", []),
        "city": context.user_data.get("city"),
        "contact": context.user_data.get("contact"),
    }
    save_application(app_record)

    success_caption = (
        f"🎉 <b>Заявка успешно отправлена!</b>\n\n"
        f"🆔 <b>Номер заявки:</b> {esc(app_id)}\n\n"
        f"📨 Мы уже получили информацию о вашем устройстве.\n"
        f"⏱ Обычно отвечаем в течение <b>5–15 минут</b>.\n\n"
        f"💬 Если потребуется уточнить детали, менеджер свяжется с вами в Telegram.\n\n"
        f"❤️ <b>Спасибо, что выбрали ZVER Store!</b>"
    )

    if SUCCESS_IMAGE.exists():
        await update.message.reply_photo(
            photo=SUCCESS_IMAGE.open("rb"),
            caption=success_caption,
            parse_mode="HTML",
            reply_markup=MAIN_MENU,
        )
    else:
        await update.message.reply_text(success_caption, parse_mode="HTML", reply_markup=MAIN_MENU)

    await notify_admin(context, app_record)

    try:
        context.job_queue.run_once(
            remind_unprocessed_application,
            when=30 * 60,
            data={"app_id": app_id},
            name=f"reminder_{app_id}",
        )
    except Exception:
        logger.exception("Could not schedule reminder for %s", app_id)


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, app_record: Dict[str, Any]) -> None:
    photos = app_record.get("photos") or []

    if photos:
        try:
            await context.bot.send_photo(
                chat_id=ADMIN_CHAT_ID_INT,
                photo=photos[0],
                caption=admin_application_text(app_record),
                parse_mode="HTML",
                reply_markup=admin_status_kb(app_record["app_id"], app_record.get("username") or ""),
            )
            for extra in photos[1:]:
                await context.bot.send_photo(chat_id=ADMIN_CHAT_ID_INT, photo=extra)
            return
        except Exception:
            logger.exception("Could not send photos to admin; fallback to text")

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID_INT,
        text=admin_application_text(app_record),
        parse_mode="HTML",
        reply_markup=admin_status_kb(app_record["app_id"], app_record.get("username") or ""),
    )


async def remind_unprocessed_application(context: ContextTypes.DEFAULT_TYPE) -> None:
    app_id = (context.job.data or {}).get("app_id")
    if not app_id:
        return
    app = get_application(app_id)
    if not app:
        return
    if app.get("status") != "new":
        return

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID_INT,
        text=(
            f"⏰ <b>Напоминание</b>\n\n"
            f"🆔 Заявка <b>{esc(app_id)}</b> ещё не обработана.\n"
            f"Прошло <b>30 минут</b> с момента создания.\n\n"
            f"Пожалуйста, обработайте заявку."
        ),
        parse_mode="HTML",
        reply_markup=admin_status_kb(app_id, app.get("username") or ""),
    )


# -----------------------------------------------------------------------------
# ADMIN CALLBACKS
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
            f"💰 <b>Введите финальную цену выкупа по заявке {esc(app_id)}</b>\n\n"
            f"Например:\n"
            f"<code>35000</code>\n"
            f"<code>35000-38000</code>\n\n"
            f"После ввода суммы заявка будет закрыта как <b>✅ Выкуплено</b>.",
            parse_mode="HTML",
        )
        return

    app_record = patch_application(app_id, {"status": status})
    if not app_record:
        await q.answer("Заявка не найдена", show_alert=True)
        return

    try:
        old = q.message.text_html or q.message.caption_html or q.message.text or q.message.caption or ""
        marker = "<b>Статус:</b>"
        if marker in old:
            new_text = old.split(marker)[0] + f"<b>Статус:</b> {status_label(status)}"
        else:
            new_text = old + f"\n\n<b>Статус:</b> {status_label(status)}"

        if q.message.photo:
            await q.edit_message_caption(
                caption=new_text,
                parse_mode="HTML",
                reply_markup=admin_status_kb(app_id, app_record.get("username") or ""),
            )
        else:
            await q.edit_message_text(
                text=new_text,
                parse_mode="HTML",
                reply_markup=admin_status_kb(app_id, app_record.get("username") or ""),
            )
    except Exception:
        logger.exception("Could not edit admin status message")

    user_id = app_record.get("user_id")
    if user_id and status == "working":
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📌 <b>Заявка {esc(app_id)} в работе</b>\n\nМенеджер уже смотрит данные устройства. Скоро вернёмся с ответом.",
            parse_mode="HTML",
        )
    elif user_id and status == "rejected":
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"❌ <b>Заявка {esc(app_id)} отклонена</b>\n\n"
                f"К сожалению, сейчас мы не готовы выкупить это устройство по заявленным данным.\n\n"
                f"Если хотите уточнить детали — напишите менеджеру: @{MANAGER_USERNAME}"
            ),
            parse_mode="HTML",
        )
    elif status == "remind":
        context.job_queue.run_once(
            remind_unprocessed_application,
            when=30 * 60,
            data={"app_id": app_id},
            name=f"manual_reminder_{app_id}",
        )


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

    price = parse_price_offer(update.message.text)
    if not price:
        await update.message.reply_text(
            "Введите финальную сумму от 1 000 ₽.\n\n"
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
                text=f"✅ <b>Сделка по заявке {esc(app_id)} завершена</b>\n\nСпасибо, что выбрали <b>ZVER Store</b> ❤️",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Could not notify client about done status")
    return True


async def admin_price_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await admin_done_price_text_handler(update, context):
        return

    pending = context.bot_data.setdefault("pending_price_requests", {})
    app_id = pending.get(update.effective_user.id)
    if not app_id:
        return

    price = parse_price_offer(update.message.text)
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
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID_INT,
            text=(
                f"{icon} <b>{title}</b>\n\n"
                f"🆔 <b>{esc(app_id)}</b>\n"
                f"Статус: {status_label(status)}\n"
                f"Предложение: <b>{esc(app_record.get('deal_price'))} ₽</b>"
            ),
            parse_mode="HTML",
            reply_markup=admin_status_kb(app_id, app_record.get("username") or ""),
        )


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
    price = parse_price_offer(" ".join(context.args[1:]).strip())
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


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    apps = read_json(APPLICATIONS_FILE, [])
    total = len(apps)
    new = sum(1 for a in apps if a.get("status") == "new")
    done = sum(1 for a in apps if a.get("status") == "done")
    rejected = sum(1 for a in apps if a.get("status") == "rejected")
    await update.message.reply_text(
        f"📊 <b>Статистика</b>\n\n"
        f"Всего заявок: <b>{total}</b>\n"
        f"Новые: <b>{new}</b>\n"
        f"Выкуплено: <b>{done}</b>\n"
        f"Отказы: <b>{rejected}</b>",
        parse_mode="HTML",
    )


# -----------------------------------------------------------------------------
# APP
# -----------------------------------------------------------------------------

def build_app() -> Application:
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📱 Продать устройство$"), begin_sell)],
        states={
            DEVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_device)],
            MODEL_IPHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_iphone_model)],
            MODEL_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_model_text)],
            MEMORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_memory)],
            BATTERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_battery)],
            COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_color)],
            CONDITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_condition)],
            DEFECTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_defects)],
            PHOTOS: [MessageHandler((filters.PHOTO | filters.TEXT) & ~filters.COMMAND, step_photos)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_city)],
            CONTACT: [MessageHandler((filters.CONTACT | filters.TEXT) & ~filters.COMMAND, step_contact)],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^🏠 Главное меню$"), go_home),
            MessageHandler(filters.Regex(r"^⬅️ Назад$"), back),
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(conv)

    app.add_handler(MessageHandler(filters.Regex(r"^💰 Узнать стоимость$"), price_info))
    app.add_handler(MessageHandler(filters.Regex(r"^☎️ Связаться с менеджером$"), contact_manager))
    app.add_handler(MessageHandler(filters.Regex(r"^📢 Канал ZVER$"), channel_info))
    app.add_handler(MessageHandler(filters.Regex(r"^🏠 Главное меню$"), go_home))

    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern=r"^check_sub$"))
    app.add_handler(CallbackQueryHandler(admin_status_callback, pattern=r"^status:"))
    app.add_handler(CallbackQueryHandler(admin_hint_callback, pattern=r"^admin_hint:"))
    app.add_handler(CallbackQueryHandler(client_offer_callback, pattern=r"^client_offer:"))

    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, admin_price_text_handler))

    return app


def main() -> None:
    logger.info("Starting ZVER Store Bot final...")
    logger.info("Admin chat: %s", ADMIN_CHAT_ID_INT)
    build_app().run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

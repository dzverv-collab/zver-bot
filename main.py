"""
ZVER Store — Apple Buyback Telegram Bot + Mini CRM
Buyback flow, inline defect checkboxes, admin status controls,
customer history, deal price capture, stats, search, export.
"""

import html
import io
import logging
import os
import re
from datetime import datetime
from pathlib import Path

import storage

from telegram import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8506708320:AAEKEcaSplEjU2OBB7cguZQ3ocX495sAZZw")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "8463353959")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/zver_store")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "zver_store")

# ---------------------------------------------------------------------------
# Branding image paths
# ---------------------------------------------------------------------------
# Place your image files here:
#   assets/welcome.jpg  — shown on /start
#   assets/success.jpg  — shown after a completed application
#
# You can also override the paths with environment variables:
#   WELCOME_IMAGE_PATH — absolute or relative path to the welcome image
#   SUCCESS_IMAGE_PATH — absolute or relative path to the success image
#
# If the file is missing or the variable is unset, the bot falls back to
# plain text — no errors, no downtime.

def _image_path(env_var: str, default: str) -> Path | None:
    """Return a Path if the image file exists, otherwise None (silent fallback)."""
    raw = os.getenv(env_var, default)
    p = Path(raw)
    return p if p.is_file() else None

WELCOME_IMAGE: Path | None = _image_path("WELCOME_IMAGE_PATH", "assets/welcome.png")
SUCCESS_IMAGE: Path | None = _image_path("SUCCESS_IMAGE_PATH", "assets/success.png")

# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Navigation constants
# ---------------------------------------------------------------------------

BACK = "⬅️ Назад"
HOME = "🏠 Главное меню"
NAV_ROW = [BACK, HOME]

# ---------------------------------------------------------------------------
# Defect options
# ---------------------------------------------------------------------------

DEFECT_OPTIONS = [
    "Нет дефектов",
    "Разбит экран",
    "Разбита задняя крышка",
    "Face ID не работает",
    "Камера не работает",
    "Не заряжается",
    "Динамик не работает",
    "Микрофон не работает",
    "Не ловит сеть / Wi-Fi",
    "После воды",
    "Другие дефекты",
]

DEFECT_NONE_IDX = 0
DEFECT_OTHER_IDX = 10

# ---------------------------------------------------------------------------
# Static keyboards
# ---------------------------------------------------------------------------

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["💰 Продать устройство", "📱 Узнать стоимость"],
        ["☎️ Связаться с менеджером", "📢 Канал ZVER"],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие…",
)

DEVICE_KB = ReplyKeyboardMarkup(
    [
        ["iPhone", "iPad"],
        ["MacBook", "Apple Watch"],
        ["AirPods", "Другое"],
        [HOME],
    ],
    resize_keyboard=True,
)

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

MEMORY_KB = ReplyKeyboardMarkup(
    [
        ["64 GB", "128 GB", "256 GB"],
        ["512 GB", "1 TB", "Другая"],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

BATTERY_KB = ReplyKeyboardMarkup(
    [
        ["100–95%", "94–90%"],
        ["89–85%", "84–80%"],
        ["Меньше 80%", "Не знаю"],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

COLOR_KB = ReplyKeyboardMarkup(
    [
        ["Чёрный", "Белый", "Серый"],
        ["Синий", "Зелёный", "Золотой"],
        ["Фиолетовый", "Другой"],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

CONDITION_KB = ReplyKeyboardMarkup(
    [
        ["✨ Отличное", "👍 Хорошее"],
        ["👌 Среднее", "😬 Плохое"],
        ["🔧 После ремонта", "❌ Не включается"],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

DONE_PHOTO_KB = ReplyKeyboardMarkup(
    [
        ["✅ Готово"],
        NAV_ROW,
    ],
    resize_keyboard=True,
)

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
        [KeyboardButton("📱 Отправить мой контакт", request_contact=True)],
        [BACK],
    ],
    resize_keyboard=True,
)

# ---------------------------------------------------------------------------
# Dynamic keyboards
# ---------------------------------------------------------------------------


def _defects_inline_kb(selected: set) -> InlineKeyboardMarkup:
    rows = []
    for i, opt in enumerate(DEFECT_OPTIONS):
        label = f"✅ {opt}" if i in selected else opt
        rows.append([InlineKeyboardButton(label, callback_data=f"defect:{i}")])
    rows.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="defect:back"),
        InlineKeyboardButton("✅ Дефекты выбраны", callback_data="defect:done"),
    ])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Admin inline keyboard (status + optional DM button)
# ---------------------------------------------------------------------------

STATUS_LABELS = {
    "working":  "🔵 Статус: Менеджер рассматривает заявку",
    "agreed":   "🟢 Статус: Цена согласована",
    "done":     "✅ Статус: Сделка завершена",
    "rejected": "❌ Статус: Отказ",
}

STATUS_NOTIFY = {
    "working":  "Статус обновлён: В работе",
    "agreed":   "Статус обновлён: Цена согласована",
    "done":     "Введите цену выкупа",
    "rejected": "Статус обновлён: Отказ",
}

_STATUS_BUTTONS = {
    "working":  ("🔵 В работе",        "✅ В работе"),
    "agreed":   ("🟢 Цена согласована", "✅ Цена согласована"),
    "done":     ("✅ Сделка завершена", "✅ Сделка завершена"),
    "rejected": ("❌ Отказ",            "✅ Отказ"),
}


def _build_status_kb(
    active_key: str | None = None,
    username: str = "",
) -> InlineKeyboardMarkup:
    """Status keyboard. Username (without @) adds a DM button."""

    def _btn(key: str) -> InlineKeyboardButton:
        normal, selected = _STATUS_BUTTONS[key]
        label = selected if key == active_key else normal
        return InlineKeyboardButton(label, callback_data=f"status:{key}:{username}")

    rows: list[list[InlineKeyboardButton]] = [
        [_btn("working"), _btn("agreed")],
        [_btn("done"),    _btn("rejected")],
    ]
    if username:
        rows.append([
            InlineKeyboardButton("💬 Написать клиенту", url=f"https://t.me/{username}")
        ])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Welcome
# ---------------------------------------------------------------------------

WELCOME_TEXT = (
    "👋 *Добро пожаловать в ZVER Store!*\n\n"
    "Ответьте на несколько вопросов — это займёт около минуты. "
    "Мы получим данные, фотографии устройства и свяжемся с вами для предварительной оценки.\n\n"
    "Также можете заглянуть в наш канал ZVER — там показываем поступления, сделки и жизнь проекта."
)

SUCCESS_TEXT_TPL = (
    "✅ *Спасибо! Ваша заявка принята.*\n\n"
    "Номер заявки: *{app_id}*\n"
    "Мы получили данные и фотографии устройства. Скоро свяжемся с вами.\n\n"
    "Пока мы обрабатываем заявку, можете перейти в наш канал ZVER."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _step(n: int, title: str) -> str:
    return f"*Шаг {n} из {TOTAL_STEPS} — {title}*\n\n"


async def _send_branded(
    update: Update,
    image: Path | None,
    caption: str,
    reply_markup,
) -> None:
    """Send a photo with caption if the image exists; otherwise plain text.

    Never raises — both photo send and text fallback are guarded, so a
    failure here cannot prevent the conversation from ending cleanly.
    """
    if image is not None:
        try:
            with image.open("rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
            return
        except Exception:
            logger.warning(
                "Could not send branded image %s — falling back to text",
                image,
                exc_info=True,
            )
    # Text fallback — also guarded so callers are never interrupted
    try:
        await update.message.reply_text(
            caption,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
    except Exception:
        logger.exception(
            "Text fallback also failed for branded message: chat=%s user=%s",
            update.effective_chat.id if update.effective_chat else "?",
            update.effective_user.id if update.effective_user else "?",
        )




def _channel_inline_kb() -> InlineKeyboardMarkup:
    """Inline URL button to the ZVER Telegram channel."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("📢 Перейти в канал", url=CHANNEL_URL)]]
    )


async def _send_channel_button(update: Update) -> None:
    """Send a separate channel CTA so it does not replace the main reply menu."""
    try:
        await update.message.reply_text(
            "📢 Канал ZVER: новые поступления, сделки и жизнь проекта.",
            reply_markup=_channel_inline_kb(),
        )
    except Exception:
        logger.exception("Failed to send channel button")


def _subscription_required_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_subscription")],
    ])


async def _is_user_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check whether the user is subscribed to the ZVER channel.

    Important: the bot must be added to the channel as an admin; otherwise
    Telegram may not allow checking channel membership.
    """
    if not CHANNEL_USERNAME:
        return True

    chat_id = f"@{CHANNEL_USERNAME.lstrip('@')}"
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in {"member", "administrator", "creator"}
    except Exception:
        logger.exception("Could not check subscription for user_id=%s in %s", user_id, chat_id)
        return False


async def _send_subscription_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🔒 *Чтобы пользоваться ботом ZVER Store, подпишитесь на канал.*\n\n"
        "Там публикуем поступления, сделки, отзывы и жизнь проекта.\n\n"
        "После подписки нажмите *✅ Проверить подписку*."
    )
    if update.message:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=_subscription_required_kb(),
        )
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=_subscription_required_kb(),
        )


async def _ensure_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False
    if await _is_user_subscribed(user.id, context):
        return True
    await _send_subscription_gate(update, context)
    return False


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not user:
        await query.answer("Не удалось определить пользователя", show_alert=True)
        return

    if await _is_user_subscribed(user.id, context):
        await query.answer("✅ Подписка подтверждена")
        context.user_data.clear()
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.message.reply_text(
            "✅ Подписка подтверждена. Теперь можно пользоваться ботом.",
            reply_markup=MAIN_MENU,
        )
    else:
        await query.answer("Пока не вижу подписку. Подпишитесь и нажмите проверку ещё раз.", show_alert=True)


def _esc(value: object) -> str:
    """HTML-escape user-supplied values to prevent parse errors."""
    return html.escape(str(value) if value else "—")


def _price_str(amount) -> str:
    """Format a price as '42 000 ₽' or '—'."""
    if not amount:
        return "—"
    try:
        return f"{int(amount):,} ₽".replace(",", "\u202f")
    except (TypeError, ValueError):
        return str(amount)


def _is_admin_chat(update: Update) -> bool:
    return bool(ADMIN_CHAT_ID and str(update.effective_chat.id) == str(ADMIN_CHAT_ID))


def _fmt_application(data: dict, user, ts: str, app_id: str, customer: dict | None) -> str:
    """Format the full admin application message (HTML).

    Accepts both context.user_data (key: 'defects_selected') and a saved
    app_record dict (key: 'defects') so callers are not order-sensitive.
    """
    username = f"@{user.username}" if user.username else "—"
    defects = data.get("defects_selected") or data.get("defects") or []
    defects_text = "\n".join(f"  • {_esc(d)}" for d in defects) if defects else "  • Нет"
    device = f"{_esc(data.get('device', '—'))} {_esc(data.get('model', ''))}".strip()

    # Customer history block
    if customer is None:
        client_block = "🆕 Новый клиент"
    else:
        models_list = (customer.get("models") or [])
        last_models = ", ".join(models_list[-3:]) if models_list else "—"
        client_block = (
            f"🟢 Уже обращался\n"
            f"Обращений: {customer.get('app_count', 0)}\n"
            f"Последняя заявка: {_esc(customer.get('last_app_date', '—'))}\n"
            f"Последние устройства: {_esc(last_models)}"
        )

    return (
        f"🔥 <b>Новая заявка {_esc(app_id)}</b>\n\n"
        f"🟡 Статус: Новая заявка\n\n"
        f"🆔 Заявка: {_esc(app_id)}\n\n"
        f"👤 {_esc(user.full_name)}\n"
        f"🔗 {_esc(username)}\n"
        f"🆔 <code>{user.id}</code>\n\n"
        f"{client_block}\n\n"
        "──────────────\n\n"
        f"📱 <b>Устройство:</b> {device}\n"
        f"💾 <b>Память:</b> {_esc(data.get('memory', '—'))}\n"
        f"🔋 <b>АКБ:</b> {_esc(data.get('battery', '—'))}\n"
        f"🎨 <b>Цвет:</b> {_esc(data.get('color', '—'))}\n"
        f"⭐ <b>Состояние:</b> {_esc(data.get('condition', '—'))}\n\n"
        f"⚠️ <b>Неисправности:</b>\n{defects_text}\n\n"
        f"📍 <b>Город:</b> {_esc(data.get('city', '—'))}\n"
        f"☎️ <b>Контакт:</b> {_esc(data.get('contact', '—'))}\n"
        f"🕒 <b>Дата/время:</b> {_esc(ts)}"
    )


def _update_status_text(original: str, new_status_line: str) -> str:
    """Replace the status line (and optional deal price line) in the message."""
    # Match the status emoji line plus an optional following price line
    return re.sub(
        r"[🟡🔵🟢✅❌] Статус: .+(\n💰 Сумма выкупа: .+)?",
        new_status_line,
        original,
        count=1,
    )


# ---------------------------------------------------------------------------
# "Ask" functions
# ---------------------------------------------------------------------------


async def ask_device(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        _step(1, "Тип устройства") + "Что вы хотите продать?",
        parse_mode="Markdown",
        reply_markup=DEVICE_KB,
    )
    return DEVICE


async def ask_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        _step(2, "Модель iPhone") + "Выберите модель:",
        parse_mode="Markdown",
        reply_markup=IPHONE_MODELS_KB,
    )
    return MODEL


async def ask_model_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    device = context.user_data.get("device", "устройство")
    await update.message.reply_text(
        _step(2, "Модель") + f"Введите модель {device}:\n\n"
        "_Например: MacBook Air M2, iPad Pro 12.9, Apple Watch Series 9_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([[BACK, HOME]], resize_keyboard=True),
    )
    return MODEL_TEXT


async def ask_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        _step(3, "Объём памяти") + "Выберите объём встроенной памяти:",
        parse_mode="Markdown",
        reply_markup=MEMORY_KB,
    )
    return MEMORY


async def ask_battery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        _step(4, "Ёмкость батареи (АКБ)") +
        "Выберите текущий уровень АКБ.\n"
        "_Настройки → Аккумулятор → Состояние аккумулятора_",
        parse_mode="Markdown",
        reply_markup=BATTERY_KB,
    )
    return BATTERY


async def ask_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        _step(5, "Цвет") + "Выберите цвет устройства:",
        parse_mode="Markdown",
        reply_markup=COLOR_KB,
    )
    return COLOR


async def ask_condition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        _step(6, "Внешнее состояние") + "Оцените внешний вид устройства:",
        parse_mode="Markdown",
        reply_markup=CONDITION_KB,
    )
    return CONDITION


async def ask_defects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected: set = context.user_data.setdefault("defects_selected_idx", set())

    # Убираем обычную клавиатуру предыдущего шага, чтобы на экране дефектов
    # не висели кнопки состояния устройства. Inline-кнопки дефектов придут ниже.
    try:
        await update.message.reply_text(
            "👇 Выберите неисправности ниже",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception:
        logger.exception("Failed to remove reply keyboard before defects step")

    msg = await update.message.reply_text(
        _step(7, "Неисправности") +
        "⚠️ Какие есть неисправности?\n"
        "Выберите все подходящие варианты, затем нажмите *✅ Дефекты выбраны*.",
        parse_mode="Markdown",
        reply_markup=_defects_inline_kb(selected),
    )
    context.user_data["defects_msg_id"] = msg.message_id
    return DEFECTS


async def ask_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    count = len(context.user_data.get("photos", []))
    hint = f" Уже загружено: {count} фото." if count else ""
    await update.message.reply_text(
        _step(8, "Фотографии") +
        "Пришлите фото устройства (можно несколько).\n"
        "После каждого фото пришлите ещё или нажмите *✅ Готово*." + hint,
        parse_mode="Markdown",
        reply_markup=DONE_PHOTO_KB,
    )
    return PHOTOS


async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        _step(9, "Город") + "Выберите ваш город:",
        parse_mode="Markdown",
        reply_markup=CITY_KB,
    )
    return CITY


async def ask_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        _step(10, "Контакт") +
        "Введите номер телефона или Telegram для связи.\n"
        "Или нажмите кнопку, чтобы поделиться контактом автоматически.",
        parse_mode="Markdown",
        reply_markup=CONTACT_KB,
    )
    return CONTACT


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if not await _ensure_subscription(update, context):
        return
    await _send_branded(update, WELCOME_IMAGE, WELCOME_TEXT, MAIN_MENU)
    await _send_channel_button(update)


# ---------------------------------------------------------------------------
# Static menu handlers (outside conversation)
# ---------------------------------------------------------------------------


async def price_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📊 *Стоимость выкупа*\n\n"
        "Цена зависит от модели, состояния и актуального рынка.\n\n"
        "Для точной оценки заполните анкету — нажмите *«💰 Продать устройство»* "
        "или напишите менеджеру: @zvertech",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )


async def contact_manager(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "☎️ *Связаться с менеджером*\n\n"
        "Мы онлайн с 9:00 до 22:00 (МСК).\n"
        "Напишите нам: @zvertech",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )


async def channel_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📢 *Канал ZVER*\n\n"
        "Там публикуем новые поступления, реальные сделки, полезные заметки "
        "по технике Apple и жизнь проекта ZVER.",
        parse_mode="Markdown",
        reply_markup=_channel_inline_kb(),
    )


# ---------------------------------------------------------------------------
# Conversation entry
# ---------------------------------------------------------------------------


async def sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if not await _ensure_subscription(update, context):
        return ConversationHandler.END
    return await ask_device(update, context)


# ---------------------------------------------------------------------------
# Step 1: device
# ---------------------------------------------------------------------------


async def step_device(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    device = update.message.text.strip()
    context.user_data["device"] = device
    context.user_data.pop("model", None)
    if device == "iPhone":
        return await ask_model(update, context)
    return await ask_model_text(update, context)


# ---------------------------------------------------------------------------
# Step 2a: iPhone model
# ---------------------------------------------------------------------------


async def step_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_device(update, context)
    context.user_data["model"] = text
    return await ask_memory(update, context)


# ---------------------------------------------------------------------------
# Step 2b: non-iPhone model (text input)
# ---------------------------------------------------------------------------


async def step_model_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_device(update, context)
    context.user_data["model"] = text
    return await ask_memory(update, context)


# ---------------------------------------------------------------------------
# Step 3: memory
# ---------------------------------------------------------------------------


async def step_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        if context.user_data.get("device") == "iPhone":
            return await ask_model(update, context)
        return await ask_model_text(update, context)
    context.user_data["memory"] = text
    return await ask_battery(update, context)


# ---------------------------------------------------------------------------
# Step 4: battery
# ---------------------------------------------------------------------------


async def step_battery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_memory(update, context)
    context.user_data["battery"] = text
    return await ask_color(update, context)


# ---------------------------------------------------------------------------
# Step 5: color
# ---------------------------------------------------------------------------


async def step_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_battery(update, context)
    context.user_data["color"] = text
    return await ask_condition(update, context)


# ---------------------------------------------------------------------------
# Step 6: external condition
# ---------------------------------------------------------------------------


async def step_condition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_color(update, context)
    context.user_data["condition"] = text
    context.user_data["defects_selected_idx"] = set()
    context.user_data["defects_custom"] = []
    return await ask_defects(update, context)


# ---------------------------------------------------------------------------
# Step 7: defects (inline checkboxes via CallbackQueryHandler)
# ---------------------------------------------------------------------------


async def defect_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    action = query.data.split(":", 1)[1]
    selected: set = context.user_data.setdefault("defects_selected_idx", set())
    customs: list = context.user_data.setdefault("defects_custom", [])

    # ── Back ───────────────────────────────────────────────────────
    if action == "back":
        await query.answer()
        context.user_data["defects_selected_idx"] = set()
        context.user_data["defects_custom"] = []
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text(
            _step(6, "Внешнее состояние") + "Оцените внешний вид устройства:",
            parse_mode="Markdown",
            reply_markup=CONDITION_KB,
        )
        return CONDITION

    # ── Confirm ────────────────────────────────────────────────────
    if action == "done":
        await query.answer()
        if not selected and not customs:
            names = ["Нет дефектов"]
        elif DEFECT_NONE_IDX in selected and len(selected) == 1 and not customs:
            names = ["Нет дефектов"]
        else:
            names = [
                DEFECT_OPTIONS[i]
                for i in sorted(selected)
                if i not in (DEFECT_NONE_IDX, DEFECT_OTHER_IDX)
            ]
            for c in customs:
                names.append(f"Другие дефекты: {c}")
            if not names:
                names = ["Нет дефектов"]
        context.user_data["defects_selected"] = names
        context.user_data["photos"] = []
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text(
            _step(8, "Фотографии") +
            "Пришлите фото устройства (можно несколько).\n"
            "После каждого фото пришлите ещё или нажмите *✅ Готово*.",
            parse_mode="Markdown",
            reply_markup=DONE_PHOTO_KB,
        )
        return PHOTOS

    # ── "Другие дефекты" ───────────────────────────────────────────
    idx = int(action)
    if idx == DEFECT_OTHER_IDX:
        await query.answer()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text(
            "✏️ Опишите дефект подробнее:",
            reply_markup=ReplyKeyboardMarkup([[BACK]], resize_keyboard=True),
        )
        return DEFECTS_OTHER

    # ── Toggle ─────────────────────────────────────────────────────
    if idx == DEFECT_NONE_IDX:
        selected.clear()
        selected.add(DEFECT_NONE_IDX)
    else:
        selected.discard(DEFECT_NONE_IDX)
        if idx in selected:
            selected.discard(idx)
        else:
            selected.add(idx)
    context.user_data["defects_selected_idx"] = selected
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=_defects_inline_kb(selected))
    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.exception("Failed to update defects keyboard")
    return DEFECTS


async def _defects_back_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ⬅️ Назад typed as text while the defects keyboard is open."""
    context.user_data["defects_selected_idx"] = set()
    context.user_data["defects_custom"] = []
    return await ask_condition(update, context)


async def step_defects_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_defects(update, context)
    customs: list = context.user_data.setdefault("defects_custom", [])
    customs.append(text)
    context.user_data.setdefault("defects_selected_idx", set()).add(DEFECT_OTHER_IDX)
    return await ask_defects(update, context)


# ---------------------------------------------------------------------------
# Step 8: photos
# ---------------------------------------------------------------------------


async def step_photos_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file_id = update.message.photo[-1].file_id
    context.user_data.setdefault("photos", []).append(file_id)
    count = len(context.user_data["photos"])
    await update.message.reply_text(
        f"✅ Фото {count} получено. Пришлите ещё или нажмите «✅ Готово».",
        reply_markup=DONE_PHOTO_KB,
    )
    return PHOTOS


async def step_photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await ask_city(update, context)


async def step_photos_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["photos"] = []
    return await ask_defects(update, context)


async def step_photos_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Пожалуйста, пришлите фото или нажмите «✅ Готово».",
        reply_markup=DONE_PHOTO_KB,
    )
    return PHOTOS


# ---------------------------------------------------------------------------
# Step 9: city
# ---------------------------------------------------------------------------


async def step_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_photos(update, context)
    if text == "Другой город":
        await update.message.reply_text(
            "📍 Введите название города:",
            reply_markup=ReplyKeyboardMarkup([[BACK]], resize_keyboard=True),
        )
        return CITY_TEXT
    context.user_data["city"] = text
    return await ask_contact(update, context)


async def step_city_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text == BACK:
        return await ask_city(update, context)
    context.user_data["city"] = text
    return await ask_contact(update, context)


# ---------------------------------------------------------------------------
# Step 10: contact + submission
# ---------------------------------------------------------------------------


async def reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fire 30 min after submission if application is still unprocessed."""
    app_id: str = context.job.data["app_id"]
    admin_chat: int = context.job.data["admin_chat"]
    if storage.get_app_status(app_id) == "new":
        try:
            await context.bot.send_message(
                chat_id=admin_chat,
                text=(
                    f"⏰ Напоминание: заявка <b>{_esc(app_id)}</b> "
                    "ещё не взята в работу."
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception(
                "Failed to send reminder for %s to admin_chat=%s", app_id, admin_chat
            )


async def step_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ── Parse contact ──────────────────────────────────────────────────────
    if update.message.contact:
        phone = update.message.contact.phone_number
        context.user_data["contact"] = f"+{phone}" if not phone.startswith("+") else phone
    else:
        text = update.message.text.strip()
        if text == BACK:
            return await ask_city(update, context)
        context.user_data["contact"] = text

    user = update.effective_user
    ts = datetime.now().strftime("%d.%m.%Y %H:%M")
    app_id = storage.next_app_id()

    # Check customer history BEFORE upserting (determines 🆕 vs 🟢 block)
    existing_customer = storage.get_customer(user.id)

    # ── Snapshot all form data while user_data is still intact ────────────
    # This must happen before any await or clear so nothing is lost.
    device   = context.user_data.get("device", "")
    model    = context.user_data.get("model", "")
    full_model = f"{device} {model}".strip() if model else device
    photos   = list(context.user_data.get("photos", []))
    defects  = list(context.user_data.get("defects_selected", []))

    app_record = {
        "app_id":    app_id,
        "date":      ts,
        "user_id":   user.id,
        "username":  user.username or "",
        "full_name": user.full_name,
        "device":    device,
        "model":     model,
        "memory":    context.user_data.get("memory", ""),
        "battery":   context.user_data.get("battery", ""),
        "color":     context.user_data.get("color", ""),
        "condition": context.user_data.get("condition", ""),
        "defects":   defects,
        "city":      context.user_data.get("city", ""),
        "contact":   context.user_data.get("contact", ""),
        "status":    "new",
        "deal_price": None,
        "photos":    photos,
    }

    # ── 1. Clear session state immediately ────────────────────────────────
    # Done first so the user can restart (/start or "💰 Продать устройство")
    # at any point, even if subsequent network calls are slow or fail.
    context.user_data.clear()

    # ── 2. Persist to storage ─────────────────────────────────────────────
    try:
        storage.save_application(app_record)
        storage.upsert_customer(
            user_id=user.id,
            username=user.username or "",
            full_name=user.full_name,
            app_id=app_id,
            date=ts,
            model=full_model,
        )
        logger.info("Application %s saved to storage (user_id=%s)", app_id, user.id)
    except Exception:
        logger.exception(
            "Storage write FAILED for application %s (user_id=%s)", app_id, user.id
        )

    # ── 3. Confirm to user ────────────────────────────────────────────────
    # _send_branded never raises — both photo and text paths are guarded.
    await _send_branded(
        update,
        SUCCESS_IMAGE,
        SUCCESS_TEXT_TPL.format(app_id=app_id),
        MAIN_MENU,
    )
    await _send_channel_button(update)

    # ── 4. Notify admin ───────────────────────────────────────────────────
    # Runs after user confirmation so a slow admin chat never delays the UX.
    if ADMIN_CHAT_ID:
        try:
            username_str = user.username or ""
            summary = _fmt_application(
                app_record, user, ts, app_id, existing_customer
            )
            await context.bot.send_message(
                chat_id=int(ADMIN_CHAT_ID),
                text=summary,
                parse_mode="HTML",
                reply_markup=_build_status_kb(username=username_str),
            )
            logger.info("Admin notified for application %s", app_id)

            if photos:
                for chunk in [photos[i: i + 10] for i in range(0, len(photos), 10)]:
                    await context.bot.send_media_group(
                        chat_id=int(ADMIN_CHAT_ID),
                        media=[InputMediaPhoto(media=fid) for fid in chunk],
                    )
            else:
                await context.bot.send_message(
                    chat_id=int(ADMIN_CHAT_ID),
                    text="📷 Фото не прикреплены.",
                )

            if context.application.job_queue is not None:
                context.application.job_queue.run_once(
                    reminder_job,
                    when=30 * 60,
                    data={"app_id": app_id, "admin_chat": int(ADMIN_CHAT_ID)},
                    name=f"reminder_{app_id}",
                )
            else:
                logger.warning("job_queue unavailable — reminder for %s skipped", app_id)

        except Exception:
            logger.exception(
                "Admin notification FAILED for application %s (user_id=%s) — "
                "check bot is admin in chat %s and the HTML is valid",
                app_id, user.id, ADMIN_CHAT_ID,
            )

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Admin status callback
# ---------------------------------------------------------------------------


async def admin_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    # Auth: only the configured admin chat may change statuses
    if ADMIN_CHAT_ID and str(query.message.chat_id) != str(ADMIN_CHAT_ID):
        await query.answer("⛔️ Нет доступа", show_alert=True)
        return

    # callback_data: "status:<key>:<username>"
    parts = query.data.split(":", 2)
    key = parts[1]
    username = parts[2] if len(parts) > 2 else ""

    if key not in STATUS_LABELS:
        await query.answer()
        return

    # Extract app_id from the message text
    app_id_match = re.search(r"ZV-\d{4}", query.message.text or "")
    app_id = app_id_match.group() if app_id_match else None

    # ── "Сделка завершена" → ask for deal price first ─────────────
    if key == "done":
        await query.answer("Введите цену выкупа")
        prompt = await query.message.reply_text(
            "💰 За сколько выкупили устройство?\n"
            "Введите сумму числом или напишите <b>пропустить</b>.",
            parse_mode="HTML",
            reply_markup=ForceReply(
                selective=False,
                input_field_placeholder="42000",
            ),
        )
        context.bot_data.setdefault("pending_prices", {})[prompt.message_id] = {
            "app_id": app_id,
            "username": username,
            "orig_message_id": query.message.message_id,
            "orig_message_text": query.message.text,
        }
        return

    # ── All other statuses: update immediately ─────────────────────
    await query.answer(STATUS_NOTIFY.get(key, "Статус обновлён"))

    if app_id:
        storage.update_application(app_id, status=key)

    original = query.message.text or ""
    updated = _update_status_text(original, STATUS_LABELS[key])
    try:
        await query.edit_message_text(
            text=updated,
            parse_mode="HTML",
            reply_markup=_build_status_kb(active_key=key, username=username),
        )
    except Exception:
        logger.exception(
            "Failed to edit admin message for app=%s status=%s chat=%s msg=%s",
            app_id, key, query.message.chat_id, query.message.message_id,
        )


# ---------------------------------------------------------------------------
# Deal price reply handler (admin chat only)
# ---------------------------------------------------------------------------


async def price_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches admin replies to the ForceReply price prompt."""
    if not update.message or not update.message.reply_to_message:
        return
    if not ADMIN_CHAT_ID or str(update.message.chat_id) != str(ADMIN_CHAT_ID):
        return

    prompt_id = update.message.reply_to_message.message_id
    pending: dict = context.bot_data.get("pending_prices", {})
    if prompt_id not in pending:
        return

    info = pending.pop(prompt_id)
    app_id: str | None = info["app_id"]
    username: str = info["username"]
    orig_msg_id: int = info["orig_message_id"]
    orig_text: str = info["orig_message_text"]

    raw = update.message.text.strip().lower()

    if raw == "пропустить":
        deal_price = None
    else:
        digits = re.sub(r"[^\d]", "", raw)
        if not digits:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 42000) "
                "или напишите <b>пропустить</b>.",
                parse_mode="HTML",
            )
            # Restore pending entry so admin can try again
            context.bot_data.setdefault("pending_prices", {})[prompt_id] = info
            return
        deal_price = int(digits)

    # Persist
    if app_id:
        storage.update_application(app_id, status="done", deal_price=deal_price)

    # Build new status line (with optional price)
    status_line = STATUS_LABELS["done"]
    if deal_price:
        status_line += f"\n💰 Сумма выкупа: {_price_str(deal_price)}"

    updated_text = _update_status_text(orig_text, status_line)

    try:
        await context.bot.edit_message_text(
            chat_id=int(ADMIN_CHAT_ID),
            message_id=orig_msg_id,
            text=updated_text,
            parse_mode="HTML",
            reply_markup=_build_status_kb(active_key="done", username=username),
        )
    except Exception:
        logger.exception(
            "Failed to edit original message after price entry: "
            "app=%s msg=%s chat=%s",
            app_id, orig_msg_id, ADMIN_CHAT_ID,
        )

    price_display = _price_str(deal_price) if deal_price else "не указана"
    await update.message.reply_text(f"✅ Сделка завершена. Сумма: {price_display}")


# ---------------------------------------------------------------------------
# Admin CRM commands
# ---------------------------------------------------------------------------


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin_chat(update):
        return

    s = storage.get_stats()
    t, w, m = s["today"], s["week"], s["month"]

    def _price_block(period: dict) -> str:
        if not period["price_count"]:
            return ""
        return (
            f"• Куплено устройств: {period['price_count']}\n"
            f"• Общая сумма выкупа: {_price_str(period['total_price'])}\n"
            f"• Средняя сумма выкупа: {_price_str(period['avg_price'])}\n"
        )

    text = (
        "📊 <b>Статистика ZVER</b>\n\n"
        "<b>Сегодня:</b>\n"
        f"• Заявок: {t['total']}\n"
        f"• В работе: {t['working']}\n"
        f"• Цена согласована: {t['agreed']}\n"
        f"• Сделка завершена: {t['done']}\n"
        f"• Отказ: {t['rejected']}\n"
        + _price_block(t) +
        "\n<b>За 7 дней:</b>\n"
        f"• Заявок: {w['total']}\n"
        f"• Сделок: {w['done']}\n"
        f"• Отказов: {w['rejected']}\n"
        f"• Конверсия: {w['conversion']}%\n"
        + _price_block(w) +
        "\n<b>За 30 дней:</b>\n"
        f"• Заявок: {m['total']}\n"
        f"• Сделок: {m['done']}\n"
        f"• Отказов: {m['rejected']}\n"
        f"• Конверсия: {m['conversion']}%\n"
        + _price_block(m)
    )
    await update.message.reply_text(text.rstrip(), parse_mode="HTML")


async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin_chat(update):
        return
    if not context.args:
        await update.message.reply_text(
            "Использование:\n"
            "/find ZV-0001\n"
            "/find @username\n"
            "/find 8463353959\n"
            "/find +79812684247"
        )
        return

    query = " ".join(context.args)
    apps = storage.find_applications(query)

    if not apps:
        await update.message.reply_text(
            f"🔍 Ничего не найдено по запросу: <code>{_esc(query)}</code>",
            parse_mode="HTML",
        )
        return

    _emoji = {"new": "🟡", "working": "🔵", "agreed": "🟢", "done": "✅", "rejected": "❌"}
    lines = [f"🔍 <b>Найдено ({len(apps)}):</b>\n"]
    for app in apps:
        em = _emoji.get(app.get("status", ""), "❓")
        uname = f"@{app['username']}" if app.get("username") else ""
        price = (
            f" · {_price_str(app['deal_price'])}"
            if app.get("deal_price") else ""
        )
        lines.append(
            f"{em} <b>{_esc(app.get('app_id', '?'))}</b> · {_esc(app.get('date', '?'))}\n"
            f"  👤 {_esc(app.get('full_name', '?'))} {_esc(uname)}\n"
            f"  📱 {_esc(app.get('device', ''))} {_esc(app.get('model', ''))}\n"
            f"  ☎️ {_esc(app.get('contact', '—'))}{price}\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin_chat(update):
        return
    try:
        csv_bytes = storage.export_csv()
        now = datetime.now().strftime("%Y%m%d_%H%M")
        await update.message.reply_document(
            document=io.BytesIO(csv_bytes),
            filename=f"zver_applications_{now}.csv",
            caption="📄 Экспорт всех заявок",
        )
    except Exception:
        logger.exception("Export failed")
        await update.message.reply_text("❌ Ошибка при экспорте.")


async def cmd_client(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin_chat(update):
        return
    if not context.args:
        await update.message.reply_text(
            "Использование:\n/client @username\n/client user_id"
        )
        return

    identifier = context.args[0]
    card = storage.get_customer_card(identifier)

    if not card:
        await update.message.reply_text(
            f"👤 Клиент не найден: <code>{_esc(identifier)}</code>",
            parse_mode="HTML",
        )
        return

    models = card.get("last_3_models") or []
    models_text = ", ".join(models) if models else "—"
    total_price = card.get("total_price", 0)
    uname = f"@{card['username']}" if card.get("username") else "—"

    text = (
        "👤 <b>Клиент</b>\n\n"
        f"Имя: {_esc(card.get('full_name', '—'))}\n"
        f"Username: {_esc(uname)}\n"
        f"User ID: <code>{card.get('user_id', '—')}</code>\n\n"
        f"Всего обращений: {card.get('app_count', 0)}\n"
        f"Последнее обращение: {_esc(card.get('last_app_date', '—'))}\n"
        f"Последние устройства: {_esc(models_text)}\n\n"
        f"Сделок завершено: {card.get('done_count', 0)}\n"
        f"Общая сумма выкупа: {_price_str(total_price) if total_price else '—'}"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# /cancel and 🏠 home
# ---------------------------------------------------------------------------


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Заявка отменена. Вы можете начать заново в любое время.",
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


async def go_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("🏠 Главное меню", reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Utility: /id
# ---------------------------------------------------------------------------


async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"🆔 Chat ID: `{update.effective_chat.id}`",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception:", exc_info=context.error)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Add it as a Replit Secret.")
    if not ADMIN_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID is not set — applications will not be forwarded.")
    else:
        logger.info("Admin chat: %s", ADMIN_CHAT_ID)

    app = Application.builder().token(TOKEN).build()

    text = filters.TEXT & ~filters.COMMAND
    home_f = filters.Regex(rf"^{re.escape(HOME)}$")

    sell_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^💰 Продать устройство$"), sell_start)
        ],
        states={
            DEVICE:        [MessageHandler(text, step_device)],
            MODEL:         [MessageHandler(text, step_model)],
            MODEL_TEXT:    [MessageHandler(text, step_model_text)],
            MEMORY:        [MessageHandler(text, step_memory)],
            BATTERY:       [MessageHandler(text, step_battery)],
            COLOR:         [MessageHandler(text, step_color)],
            CONDITION:     [MessageHandler(text, step_condition)],
            DEFECTS: [
                CallbackQueryHandler(defect_callback, pattern=r"^defect:"),
                MessageHandler(filters.Regex(rf"^{re.escape(BACK)}$"), _defects_back_msg),
                MessageHandler(home_f, go_home),
            ],
            DEFECTS_OTHER: [MessageHandler(text, step_defects_other)],
            PHOTOS: [
                MessageHandler(filters.PHOTO, step_photos_receive),
                MessageHandler(filters.Regex(r"^✅ Готово$"), step_photos_done),
                MessageHandler(filters.Regex(rf"^{re.escape(BACK)}$"), step_photos_back),
                MessageHandler(text, step_photos_invalid),
            ],
            CITY:      [MessageHandler(text, step_city)],
            CITY_TEXT: [MessageHandler(text, step_city_text)],
            CONTACT: [
                MessageHandler(filters.CONTACT, step_contact),
                MessageHandler(text, step_contact),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(home_f, go_home),
        ],
        allow_reentry=True,
    )

    # ── Core handlers ──────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", get_chat_id))
    app.add_handler(sell_conv)

    # ── Admin CRM commands ─────────────────────────────────────────
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("find", cmd_find))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("client", cmd_client))

    # ── Inline callbacks ───────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern=r"^check_subscription$"))
    app.add_handler(CallbackQueryHandler(admin_status_callback, pattern=r"^status:"))

    # ── Deal price reply (must come before generic text handlers) ──
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT, price_reply_handler))

    # ── Static menu ────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.Regex(r"^📱 Узнать стоимость$"), price_info))
    app.add_handler(MessageHandler(filters.Regex(r"^☎️ Связаться с менеджером$"), contact_manager))
    app.add_handler(MessageHandler(filters.Regex(r"^📢 Канал ZVER$"), channel_info))

    app.add_error_handler(error_handler)

    logger.info("ZVER Store bot is running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

DEVICE, MODEL, MEMORY, CONDITION, DEFECTS, PHOTOS, CITY, PHONE = range(8)

main_menu = ReplyKeyboardMarkup(
    [["💰 Продать устройство", "☎️ Связаться с менеджером"]],
    resize_keyboard=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Добро пожаловать в ZVER Store\n\n"
        "Здесь можно быстро отправить заявку на оценку техники Apple.",
        reply_markup=main_menu
    )

async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Chat ID: {update.effective_chat.id}")

async def sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "📱 Что хотите продать?\n\nНапример: iPhone, MacBook, iPad, Apple Watch"
    )
    return DEVICE

async def device(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["device"] = update.message.text
    await update.message.reply_text("Напишите модель устройства. Например: iPhone 13 Pro")
    return MODEL

async def model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["model"] = update.message.text
    await update.message.reply_text("Какая память? Например: 128 GB")
    return MEMORY

async def memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["memory"] = update.message.text
    await update.message.reply_text("В каком состоянии устройство? Целое / битое / после ремонта / не включается")
    return CONDITION

async def condition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["condition"] = update.message.text
    await update.message.reply_text("Какие есть дефекты? Если нет — напишите «нет».")
    return DEFECTS

async def defects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["defects"] = update.message.text
    context.user_data["photos"] = []
    await update.message.reply_text("📷 Пришлите фото устройства. Можно несколько. Когда закончите — напишите «готово».")
    return PHOTOS

async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        context.user_data["photos"].append(file_id)
        await update.message.reply_text("Фото получил. Пришлите ещё или напишите «готово».")
        return PHOTOS

    if update.message.text and update.message.text.lower() == "готово":
        await update.message.reply_text("📍 В каком вы городе?")
        return CITY

    await update.message.reply_text("Пришлите фото или напишите «готово».")
    return PHOTOS

async def city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["city"] = update.message.text
    await update.message.reply_text("📞 Оставьте телефон или Telegram для связи.")
    return PHONE

async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text

    data = context.user_data
    username = update.effective_user.username
    user_link = f"@{username}" if username else update.effective_user.full_name

    text = (
        "🟢 НОВАЯ ЗАЯВКА ZVER\n\n"
        f"👤 Клиент: {user_link}\n"
        f"📱 Устройство: {data.get('device')}\n"
        f"📌 Модель: {data.get('model')}\n"
        f"💾 Память: {data.get('memory')}\n"
        f"⚙️ Состояние: {data.get('condition')}\n"
        f"❗️ Дефекты: {data.get('defects')}\n"
        f"📍 Город: {data.get('city')}\n"
        f"📞 Контакт: {data.get('phone')}"
    )

    if ADMIN_CHAT_ID:
        await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=text)

        for photo_id in data.get("photos", []):
            await context.bot.send_photo(chat_id=int(ADMIN_CHAT_ID), photo=photo_id)

    await update.message.reply_text(
        "✅ Заявка отправлена!\n\nМы скоро свяжемся с вами для оценки.",
        reply_markup=main_menu
    )

    return ConversationHandler.END

async def manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("☎️ Напишите нам: @zvertech")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Заявка отменена.", reply_markup=main_menu)
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Продать устройство$"), sell_start)],
        states={
            DEVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, device)],
            MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, model)],
            MEMORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, memory)],
            CONDITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, condition)],
            DEFECTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, defects)],
            PHOTOS: [MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), photos)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, city)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", chat_id))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Regex("^☎️ Связаться с менеджером$"), manager))

    app.run_polling()

if __name__ == "__main__":
    main()
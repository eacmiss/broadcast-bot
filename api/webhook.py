import os
import json
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from fastapi import FastAPI, Request

load_dotenv()

DATA_FILE = "broadcast_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"users": [], "scheduled_messages": [], "sent_messages": 0}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_admin(user_id):
    admin_ids = os.getenv("ADMIN_USER_IDS", "").split(",")
    return str(user_id) in admin_ids

app = FastAPI()

bot_app = None

def get_bot_app():
    global bot_app
    if bot_app is None:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found")
        bot_app = Application.builder().token(token).build()
        
        bot_app.add_handler(CommandHandler("start", start))
        bot_app.add_handler(CallbackQueryHandler(handle_callback))
        bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_message))
    return bot_app

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user_id = update.effective_user.id
    data = load_data()
    
    if user_id not in data["users"]:
        data["users"].append(user_id)
        save_data(data)
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")]
    ]
    
    if is_admin(user_id):
        keyboard.insert(0, [InlineKeyboardButton("📢 Админ-панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📢 Бот для рассылок сообщений\n\n"
        "Этот бот используется для массовых рассылок "
        "в сообществах и чатах.\n\n"
        f"Пользователей в базе: {len(data['users'])}",
        reply_markup=reply_markup
    )

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику"""
    query = update.callback_query
    data = load_data()
    
    text = "📊 Статистика бота\n\n"
    text += f"👥 Всего пользователей: {len(data['users'])}\n"
    text += f"📨 Отправлено сообщений: {data['sent_messages']}\n"
    text += f"⏰ Запланированных рассылок: {len(data['scheduled_messages'])}\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию"""
    query = update.callback_query
    
    text = "ℹ️ Информация о боте\n\n"
    text += "📢 Бот для массовых рассылок\n\n"
    text += "Возможности:\n"
    text += "• Массовые рассылки всем пользователям\n"
    text += "• Планирование рассылок по времени\n"
    text += "• Статистика отправленных сообщений\n"
    text += "• Сегментация пользователей\n\n"
    text += "Связь с разработчиком: @eacmiss"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-панель"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.answer("⛔ У вас нет прав администратора")
        return
    
    keyboard = [
        [InlineKeyboardButton("📨 Отправить рассылку", callback_data="send_broadcast")],
        [InlineKeyboardButton("⏰ Запланировать рассылку", callback_data="schedule_broadcast")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="user_list")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "⚙️ Админ-панель\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def send_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало отправки рассылки"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.answer("⛔ У вас нет прав администратора")
        return
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📨 Отправка рассылки\n\n"
        "Напишите сообщение для рассылки.\n\n"
        "Поддерживается:\n"
        "• Текст\n"
        "• Фотографии (отправьте фото с описанием)\n"
        "• Ссылки",
        reply_markup=reply_markup
    )
    
    context.user_data['awaiting_broadcast'] = True

async def user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список пользователей"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.answer("⛔ У вас нет прав администратора")
        return
    
    data = load_data()
    
    text = f"👥 Список пользователей ({len(data['users'])})\n\n"
    for i, uid in enumerate(data['users'][:20], 1):
        text += f"{i}. ID: {uid}\n"
    
    if len(data['users']) > 20:
        text += f"\n... и ещё {len(data['users']) - 20} пользователей"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщения для рассылки"""
    if not context.user_data.get('awaiting_broadcast'):
        return
    
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав администратора")
        return
    
    message_text = update.message.text
    data = load_data()
    
    success_count = 0
    error_count = 0
    
    await update.message.reply_text(
        f"📨 Начинаю рассылку {len(data['users'])} пользователям...\n"
        "Это может занять некоторое время."
    )
    
    for user_id in data['users']:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode='HTML'
            )
            success_count += 1
        except Exception as e:
            error_count += 1
            print(f"Ошибка отправки пользователю {user_id}: {e}")
    
    data['sent_messages'] += success_count
    save_data(data)
    
    await update.message.reply_text(
        f"✅ Рассылка завершена!\n\n"
        f"📊 Результаты:\n"
        f"• Успешно отправлено: {success_count}\n"
        f"• Ошибок: {error_count}"
    )
    
    context.user_data['awaiting_broadcast'] = False

async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    user_id = update.effective_user.id
    data = load_data()
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")]
    ]
    
    if is_admin(user_id):
        keyboard.insert(0, [InlineKeyboardButton("📢 Админ-панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query = update.callback_query
    await query.edit_message_text(
        "📢 Бот для рассылок сообщений\n\n"
        "Этот бот используется для массовых рассылок "
        "в сообществах и чатах.\n\n"
        f"Пользователей в базе: {len(data['users'])}",
        reply_markup=reply_markup
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback запросов"""
    query = update.callback_query
    data = query.data
    
    if data == "stats":
        await show_stats(update, context)
    elif data == "info":
        await show_info(update, context)
    elif data == "admin_panel":
        await admin_panel(update, context)
    elif data == "send_broadcast":
        await send_broadcast_start(update, context)
    elif data == "user_list":
        await user_list(update, context)
    elif data == "back_main":
        await back_main(update, context)

@app.post("/webhook")
async def webhook(request: Request):
    """Обработка Telegram webhook"""
    application = get_bot_app()
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "broadcast-bot is running"}

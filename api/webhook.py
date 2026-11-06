import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application
from fastapi import FastAPI, Request

from bot_core import register_handlers

load_dotenv()

app = FastAPI()
bot_app = None
_init_lock = asyncio.Lock()
_initialized = False


async def get_bot_app():
    """Лениво создаёт и инициализирует PTB Application один раз на инстанс.

    ВАЖНО: shutdown() после каждого апдейта ломал бота — повторный
    initialize() на «выключенном» приложении приводил к ошибкам,
    и бот переставал отвечать до cold start.
    """
    global bot_app, _initialized
    if bot_app is None:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN не найден")
        bot_app = Application.builder().token(token).build()
        register_handlers(bot_app)
    if not _initialized:
        async with _init_lock:
            if not _initialized:
                await bot_app.initialize()
                _initialized = True
    return bot_app


@app.post("/")
@app.post("/webhook")
@app.post("/api/webhook")
async def webhook(request: Request):
    """Обработка вебхука Telegram"""
    application = await get_bot_app()
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"status": "broadcast-bot запущен"}

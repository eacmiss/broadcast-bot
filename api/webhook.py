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


def get_bot_app():
    global bot_app
    if bot_app is None:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN не найден")
        bot_app = Application.builder().token(token).build()
        register_handlers(bot_app)
    return bot_app


@app.post("/")
@app.post("/webhook")
@app.post("/api/webhook")
async def webhook(request: Request):
    """Обработка вебхука Telegram"""
    application = get_bot_app()
    data = await request.json()
    update = Update.de_json(data, application.bot)

    await application.initialize()
    try:
        await application.process_update(update)
    finally:
        await application.shutdown()

    return {"status": "ok"}


@app.get("/")
async def root():
    return {"status": "broadcast-bot запущен"}

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from telegram.ext import Application
from bot_core import register_handlers

load_dotenv()


def main():
    """Запуск бота"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Ошибка: TELEGRAM_BOT_TOKEN не найден в файле .env")
        return

    application = Application.builder().token(token).build()
    register_handlers(application)

    print("Бот-рассыльщик запущен...")
    application.run_polling()


if __name__ == "__main__":
    main()

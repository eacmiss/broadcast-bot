"""Скрипт для получения Telethon-сессии (запускать ОДИН раз локально).

Использование:
1. Создай api_id/api_hash на https://my.telegram.org → API development tools
2. Пропиши их в .env: TELEGRAM_API_ID, TELEGRAM_API_HASH
3. Запусти: python src/login_session.py
4. Введи номер телефона и код из Telegram
5. Скрипт выведет TELETHON_SESSION — добавь его в .env и в Vercel env
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()


async def main():
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    if not api_id or not api_hash:
        print("Ошибка: добавь TELEGRAM_API_ID и TELEGRAM_API_HASH в .env")
        print("Получить можно на https://my.telegram.org → API development tools")
        return

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.start()  # спросит номер телефона и код

    session_string = client.session.save()
    print("\n=== TELETHON_SESSION ===")
    print(session_string)
    print("=== конец ===")
    print("\nСохрани эту строку в .env как TELETHON_SESSION и добавь в Vercel env vars.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

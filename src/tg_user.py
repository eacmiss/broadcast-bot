import os
from telethon import TelegramClient
from telethon.sessions import StringSession

_client = None


def get_client():
    """Ленивый клиент Telethon с сессией из env"""
    global _client
    if _client is None:
        session = os.getenv("TELETHON_SESSION", "")
        api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
        api_hash = os.getenv("TELEGRAM_API_HASH", "")
        if not session or not api_id or not api_hash:
            raise RuntimeError("Не настроена Telethon-сессия (TELETHON_SESSION / TELEGRAM_API_ID / TELEGRAM_API_HASH)")
        _client = TelegramClient(StringSession(session), api_id, api_hash)
    return _client


async def connect():
    """Подключиться и проверить авторизацию"""
    client = get_client()
    if not client.is_connected():
        await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Telethon-сессия не авторизована")
    return client


async def get_dialogs():
    """Список диалогов аккаунта: [{key, title, entity}]"""
    client = await connect()
    dialogs = await client.get_dialogs(limit=300)
    result = []
    for d in dialogs:
        e = d.entity
        key = f"{e.__class__.__name__}:{e.id}"
        title = d.name or d.title or str(e.id)
        result.append({"key": key, "title": title, "entity": e})
    return result


async def resolve_entities(keys):
    """Получить entity-объекты по ключам из свежего списка диалогов"""
    dialogs = await get_dialogs()
    wanted = set(keys)
    return [d["entity"] for d in dialogs if d["key"] in wanted]


async def send_text(entity, text):
    client = await connect()
    await client.send_message(entity, text)


async def send_file(entity, data: bytes, caption=""):
    client = await connect()
    await client.send_file(entity, data, caption=caption)

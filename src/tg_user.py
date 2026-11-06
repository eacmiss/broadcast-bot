import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from telethon.tl.types import InputPeerUser, InputPeerChat, InputPeerChannel

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
    """Подключиться и проверить авторизацию.

    Переподключается, если прошлое соединение умерло (serverless freeze,
    обрыв сети).
    """
    client = get_client()
    if not client.is_connected():
        await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Telethon-сессия не авторизована — перелогинься через src/login_session.py")
    return client


def _peer_info(e):
    """Данные для прямого резолва entity: kind, id, access_hash."""
    cls = e.__class__.__name__
    return {
        "kind": cls,                      # User | Chat | Channel
        "id": e.id,
        "hash": getattr(e, "access_hash", None),
    }


def peer_from_info(info):
    """InputPeer из сохранённых данных (работает без свежего списка диалогов)."""
    kind, pid, h = info["kind"], info["id"], info.get("hash")
    if kind == "User" and h is not None:
        return InputPeerUser(pid, h)
    if kind == "Chat":
        return InputPeerChat(pid)
    if kind == "Channel" and h is not None:
        return InputPeerChannel(pid, h)
    return None


async def get_dialogs():
    """Список диалогов аккаунта: [{key, title, entity, peer}]"""
    client = await connect()
    dialogs = await client.get_dialogs(limit=None)
    result = []
    for d in dialogs:
        e = d.entity
        key = f"{e.__class__.__name__}:{e.id}"
        title = d.name or d.title or str(e.id)
        result.append({"key": key, "title": title, "entity": e, "peer": _peer_info(e)})
    return result


async def resolve_entities(items):
    """Резолвит выбранные чаты в InputPeer-объекты БЕЗ лишних запросов к API.

    InputPeer достаточно для send_message/send_file — так мы не делаем
    по одному get_entity на чат (это съедало таймаут serverless-функции
    до первой отправки).

    items — список dict {key, title, peer} из кэша диалогов.
    Возвращает (peers, missing_keys).
    """
    peers, missing = [], []
    for it in items:
        peer = peer_from_info(it["peer"]) if it.get("peer") else None
        if peer is not None:
            peers.append({"peer": peer, "title": it.get("title") or it["key"], "key": it["key"]})
        else:
            missing.append(it["key"])
    return peers, missing


async def _send_with_retry(coro_factory, retries=2):
    """Выполнить отправку; при обрыве соединения — переподключиться и повторить."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            client = await connect()
            return await coro_factory(client)
        except FloodWaitError:
            raise  # флуд-лимит не лечится реконнектом
        except (ConnectionError, OSError, asyncio.TimeoutError) as e:
            last_err = e
            try:
                client = get_client()
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass
            if attempt < retries:
                await asyncio.sleep(1)
        except Exception:
            raise
    raise last_err


async def send_text(entity, text):
    async def do(client):
        await client.send_message(entity, text)
    await _send_with_retry(do)


async def send_file(entity, data: bytes, caption=""):
    async def do(client):
        await client.send_file(entity, data, caption=caption)
    await _send_with_retry(do)

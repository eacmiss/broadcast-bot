import os
import sys
import json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import tg_user

DATA_FILE = "/tmp/broadcast_data.json" if os.getenv("VERCEL") else "broadcast_data.json"
PAGE_SIZE = 8

# Управление бесконечной рассылкой (работает только в polling-режиме,
# на Vercel serverless-функция будет убита по таймауту)
_loop = {"active": False}


def stop_loop():
    _loop["active"] = False


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"chats": {}, "sent_messages": 0, "dlg_cache": {}, "delay": 1}


def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_admin(user_id):
    admin_ids = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]
    return str(user_id) in admin_ids


def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("� Выбрать чаты", callback_data="pick_chats")],
        [InlineKeyboardButton("� Выбранные чаты", callback_data="my_chats")],
        [InlineKeyboardButton("� Создать рассылку", callback_data="broadcast")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("⏱ Интервал", callback_data="set_delay")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="info")]
    ])


START_TEXT = (
    "� Бот-рассыльщик от личного аккаунта\n\n"
    "Рассылки уходят ОТ ТВОЕГО ИМЕНИ — бот использует сессию твоего аккаунта.\n\n"
    "Как пользоваться:\n"
    "1. «Выбрать чаты» — отметь нужные диалоги\n"
    "2. «Создать рассылку» — отправь текст, фото или стикер\n"
    "3. Бот разошлёт сообщение всем выбранным чатам по кругу\n"
    "4. /stop — остановить рассылку\n\n"
    "Только для администратора."
)


async def start(update, context):
    user_id = update.effective_user.id
    context.user_data.clear()

    if not is_admin(user_id):
        await update.message.reply_text("⛔ Этот бот приватный. Доступ только для администратора.")
        return

    await update.message.reply_text(START_TEXT, reply_markup=main_keyboard())


async def show_info(update, context):
    query = update.callback_query
    await query.edit_message_text(
        "ℹ️ Информация о боте\n\n"
        "� Юзербот-рассыльщик\n\n"
        "Возможности:\n"
        "• Рассылка от твоего личного аккаунта\n"
        "• Выбор чатов из твоих диалогов\n"
        "• Текст, фото и стикеры\n\n"
        "Важно: Telegram ограничивает частоту сообщений — "
        "не делай слишком частые рассылки, аккаунт могут ограничить.\n\n"
        "Связь с разработчиком: @eacmiss",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
        ])
    )


async def show_stats(update, context):
    query = update.callback_query
    data = load_data()
    await query.edit_message_text(
        f"📊 Статистика\n\n"
        f"💬 Выбрано чатов: {len(data['chats'])}\n"
        f"📨 Отправлено сообщений: {data['sent_messages']}\n"
        f"⏱ Интервал между сообщениями: {data.get('delay', 1)} сек",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
        ])
    )


# ---------- Выбор чатов ----------

async def _get_dialog_cache(admin_id):
    """Получить кэш диалогов (key/title/peer — без entity, он не сериализуется)"""
    data = load_data()
    cache = data.get("dlg_cache", {}).get(str(admin_id))
    if cache is None:
        try:
            dialogs = await tg_user.get_dialogs()
            cache = [{"key": d["key"], "title": d["title"], "peer": d["peer"]} for d in dialogs]
        except Exception as e:
            return None, str(e)
        data.setdefault("dlg_cache", {})[str(admin_id)] = cache
        save_data(data)
    return cache, None


def _chat_title(v):
    """Название чата из значения data['chats'] (dict или legacy-строка)."""
    return v.get("title", "?") if isinstance(v, dict) else str(v)


def _render_dialog_page(cache, chats, page):
    total_pages = max(1, (len(cache) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    items = cache[start:start + PAGE_SIZE]

    keyboard = []
    for d in items:
        mark = "✅" if d["key"] in chats else "▫️"
        title = d["title"][:30]
        keyboard.append([InlineKeyboardButton(f"{mark} {title}", callback_data=f"tg_{d['key']}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"pg_{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"pg_{page + 1}"))
    keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_main")])

    return InlineKeyboardMarkup(keyboard), page


async def pick_chats(update, context):
    query = update.callback_query
    admin_id = str(query.from_user.id)
    data = load_data()

    await query.edit_message_text("⏳ Загружаю твои диалоги...")

    cache, err = await _get_dialog_cache(admin_id)
    if err:
        await query.edit_message_text(
            f"⚠️ Не удалось загрузить диалоги.\n\n{err}\n\n"
            "Проверь, что Telethon-сессия настроена.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("� Повторить", callback_data="pick_chats")],
                [InlineKeyboardButton("�🔙 Назад", callback_data="back_main")]
            ])
        )
        return

    context.user_data['dlg_page'] = 0
    keyboard, _ = _render_dialog_page(cache, data['chats'], 0)
    await query.edit_message_text(
        f"💬 Выбери чаты для рассылки ({len(data['chats'])} выбрано):",
        reply_markup=keyboard
    )


async def dlg_page(update, context):
    query = update.callback_query
    admin_id = str(query.from_user.id)
    page = int(query.data.replace("pg_", ""))

    data = load_data()
    cache = data.get("dlg_cache", {}).get(admin_id, [])
    if not cache:
        await pick_chats(update, context)
        return

    keyboard, page = _render_dialog_page(cache, data['chats'], page)
    context.user_data['dlg_page'] = page
    await query.edit_message_text(
        f"💬 Выбери чаты для рассылки ({len(data['chats'])} выбрано):",
        reply_markup=keyboard
    )


async def toggle_chat(update, context):
    query = update.callback_query
    admin_id = str(query.from_user.id)
    key = query.data[3:]  # убираем "tg_"

    data = load_data()
    cache = data.get("dlg_cache", {}).get(admin_id, [])
    title = next((d["title"] for d in cache if d["key"] == key), key)

    entry = next((d for d in cache if d["key"] == key), None)
    peer = entry.get("peer") if entry else None

    if key in data['chats']:
        del data['chats'][key]
        await query.answer(f"❌ Убрано: {title[:30]}")
    else:
        data['chats'][key] = {"title": title, "peer": peer}
        await query.answer(f"✅ Добавлено: {title[:30]}")

    save_data(data)
    page = context.user_data.get('dlg_page', 0)
    keyboard, page = _render_dialog_page(cache, data['chats'], page)
    await query.edit_message_text(
        f"💬 Выбери чаты для рассылки ({len(data['chats'])} выбрано):",
        reply_markup=keyboard
    )


async def my_chats(update, context):
    query = update.callback_query
    data = load_data()

    if not data['chats']:
        text = "📋 Выбранные чаты\n\nПока ничего не выбрано."
    else:
        text = f"� Выбранные чаты ({len(data['chats'])}):\n\n"
        for i, (key, val) in enumerate(data['chats'].items(), 1):
            text += f"{i}. {_chat_title(val)}\n"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("� Сбросить выбор", callback_data="clear_chats")],
            [InlineKeyboardButton("�🔙 Назад", callback_data="back_main")]
        ])
    )


async def clear_chats(update, context):
    query = update.callback_query
    data = load_data()
    data['chats'] = {}
    save_data(data)
    await query.answer("✅ Выбор сброшен")
    await my_chats(update, context)


# ---------- Рассылка ----------

async def broadcast_start(update, context):
    query = update.callback_query
    data = load_data()

    if not data['chats']:
        await query.answer("⚠️ Сначала выбери чаты", show_alert=True)
        return

    context.user_data['mode'] = 'broadcast'
    await query.edit_message_text(
        f"📢 Создание рассылки\n\n"
        f"Чатов: {len(data['chats'])}\n\n"
        "Отправь сообщение для рассылки:\n"
        "• Текст\n"
        "• Фото (подпись опционально)\n"
        "• Стикер",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="back_main")]
        ])
    )


async def _resolve_selected():
    """Список элементов выбранных чатов [{key,title,peer}] для резолва.

    Peer-данные берём из кэша диалогов; если кэш протух — обновляем.
    """
    data = load_data()
    admin_id = next(iter([k for k in data.get("dlg_cache", {})] or [None]), None)
    cache = {}
    if admin_id:
        cache, _ = await _get_dialog_cache(admin_id)
        cache = {d["key"]: d for d in (cache or [])}

    items = []
    for key, val in data['chats'].items():
        title = _chat_title(val)
        peer = val.get("peer") if isinstance(val, dict) else None
        entry = cache.get(key)
        if peer is None and entry:
            peer = entry.get("peer")
        items.append({"key": key, "title": title, "peer": peer})
    return items


async def _interruptible_sleep(seconds):
    """Sleep, прерываемый командой /stop (проверка каждые 2 сек)."""
    end = asyncio.get_event_loop().time() + seconds
    while _loop["active"] and asyncio.get_event_loop().time() < end:
        await asyncio.sleep(min(2, max(0.1, end - asyncio.get_event_loop().time())))


async def _send_pass(update, targets, missing, title_by_key, kind, payload, caption, data):
    """Один проход рассылки по всем чатам. Возвращает (success, errors)."""
    success, errors = 0, []
    total_n = len(targets) + len(missing)

    for key in missing:
        errors.append(f"{title_by_key.get(key, key)}: чат недоступен (нет доступа или диалог удалён)")

    for i, target in enumerate(targets):
        if not _loop["active"]:
            break
        peer, name = target["peer"], target["title"]
        try:
            if kind == 'text':
                await asyncio.wait_for(tg_user.send_text(peer, payload), timeout=30)
            else:
                await asyncio.wait_for(tg_user.send_file(peer, payload, caption=caption), timeout=30)
            success += 1
        except asyncio.TimeoutError:
            errors.append(f"{name}: таймаут отправки (30с)")
        except Exception as e:
            # FloodWait: короткий — ждём и повторяем, длинный — пропускаем чат
            if type(e).__name__ == 'FloodWaitError':
                secs = getattr(e, 'seconds', 0)
                if secs <= 60:
                    await asyncio.sleep(secs + 1)
                    try:
                        if kind == 'text':
                            await asyncio.wait_for(tg_user.send_text(peer, payload), timeout=30)
                        else:
                            await asyncio.wait_for(tg_user.send_file(peer, payload, caption=caption), timeout=30)
                        success += 1
                    except Exception as e2:
                        errors.append(f"{name}: flood {secs}s")
                else:
                    errors.append(f"{name}: floodwait {secs}s")
            else:
                errors.append(f"{name}: {str(e)[:60]}")

        # Прогресс каждые 5 чатов — чтобы было видно, что рассылка жива
        if (i + 1) % 5 == 0 and i + 1 < total_n:
            try:
                await update.message.reply_text(f"📨 Прогресс: {i + 1}/{total_n} (успешно: {success})")
            except Exception:
                pass

        # Пауза между сообщениями (кроме последнего)
        delay = data.get('delay', 1)
        if delay > 0 and i < len(targets) - 1:
            await _interruptible_sleep(delay)

    return success, errors


async def _send_broadcast(update, context, kind, payload, caption=""):
    """Рассылка по кругу: проход за проходом, пока не /stop.

    ВНИМАНИЕ: бесконечный цикл работает только в polling-режиме
    (python src/bot.py). На Vercel функцию убьёт таймаут.
    """
    data = load_data()
    total = len(data['chats'])
    context.user_data.pop('mode', None)

    await update.message.reply_text(
        f"📨 Начинаю рассылку в {total} чатов...\n"
        "Работает в цикле до команды /stop.\nЭто может занять время."
    )

    try:
        items = await _resolve_selected()
        targets, missing = await tg_user.resolve_entities(items)
    except Exception as e:
        await update.message.reply_text(
            f"❌ Не удалось подготовить рассылку:\n<code>{str(e)[:500]}</code>",
            parse_mode="HTML")
        return

    title_by_key = {it["key"]: it["title"] for it in items}
    _loop["active"] = True
    cycle = 0
    total_success, total_errors = 0, 0

    while _loop["active"]:
        cycle += 1
        success, errors = await _send_pass(
            update, targets, missing, title_by_key, kind, payload, caption, data)
        total_success += success
        total_errors += len(errors)
        data['sent_messages'] += success
        save_data(data)

        if not _loop["active"]:
            break

        await update.message.reply_text(
            f"🔁 Цикл {cycle} завершён: успешно {success}, ошибок {len(errors)}. "
            f"Следующий цикл через {data.get('delay', 1)} сек. /stop — остановить.")
        await _interruptible_sleep(data.get('delay', 1))

    _loop["active"] = False
    await update.message.reply_text(
        f"⏹ Рассылка остановлена.\n"
        f"Всего циклов: {cycle}\n"
        f"Успешных отправок: {total_success}\n"
        f"Ошибок: {total_errors}",
        reply_markup=main_keyboard())


async def set_delay_mode(update, context):
    query = update.callback_query
    data = load_data()
    context.user_data['mode'] = 'set_delay'
    await query.edit_message_text(
        f"⏱ Интервал между сообщениями\n\n"
        f"Сейчас: {data.get('delay', 1)} сек\n\n"
        "Отправь новое значение в секундах (0 — без паузы, например 3).",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="back_main")]
        ])
    )


async def handle_delay_input(update, context):
    """Установка интервала"""
    context.user_data.pop('mode', None)
    text = update.message.text.strip()

    try:
        delay = int(text)
        if delay < 0 or delay > 300:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Введи число от 0 до 300 секунд")
        return

    data = load_data()
    data['delay'] = delay
    save_data(data)

    await update.message.reply_text(
        f"✅ Интервал установлен: {delay} сек между сообщениями",
        reply_markup=main_keyboard()
    )


async def handle_broadcast(update, context):
    """Роутер контента рассылки (текст/фото/стикер)"""
    mode = context.user_data.get('mode')
    if mode == 'set_delay':
        await handle_delay_input(update, context)
        return
    if mode != 'broadcast':
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав")
        return

    msg = update.message

    if msg.text:
        await _send_broadcast(update, context, 'text', msg.text)
    elif msg.photo:
        file = await msg.photo[-1].get_file()
        data = await file.download_as_bytearray()
        await _send_broadcast(update, context, 'file', bytes(data), caption=msg.caption or "")
    elif msg.sticker:
        file = await msg.sticker.get_file()
        data = await file.download_as_bytearray()
        await _send_broadcast(update, context, 'file', bytes(data))
    else:
        await msg.reply_text("⚠️ Поддерживаются только текст, фото и стикеры")


# ---------- Навигация ----------

async def handle_callback(update, context):
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет прав", show_alert=True)
        return

    if query.data == "noop":
        await query.answer()
        return

    await query.answer()
    data = query.data

    if data == "pick_chats":
        await pick_chats(update, context)
    elif data == "my_chats":
        await my_chats(update, context)
    elif data == "clear_chats":
        await clear_chats(update, context)
    elif data == "broadcast":
        await broadcast_start(update, context)
    elif data == "stats":
        await show_stats(update, context)
    elif data == "set_delay":
        await set_delay_mode(update, context)
    elif data == "info":
        await show_info(update, context)
    elif data == "back_main":
        context.user_data.clear()
        await query.edit_message_text(START_TEXT, reply_markup=main_keyboard())
    elif data.startswith("pg_"):
        await dlg_page(update, context)
    elif data.startswith("tg_"):
        await toggle_chat(update, context)


async def cmd_stop(update, context):
    """Остановить циклическую рассылку"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав")
        return
    if _loop["active"]:
        stop_loop()
        await update.message.reply_text("⏹ Останавливаю рассылку...")
    else:
        await update.message.reply_text("Рассылка не запущена.")


def register_handlers(application):
    """Регистрация обработчиков для polling и webhook"""
    from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", cmd_stop))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast))
    application.add_handler(MessageHandler(filters.PHOTO, handle_broadcast))
    application.add_handler(MessageHandler(filters.Sticker.ALL, handle_broadcast))

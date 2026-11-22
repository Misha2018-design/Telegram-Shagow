import asyncio
import html
from datetime import datetime

from dotenv import load_dotenv
from telethon import TelegramClient, events, functions, types

load_dotenv()

from config import (
    API_HASH,
    API_ID,
    DATABASE_PATH,
    NOTIFY_CHAT_ID,
    PHONE,
    SESSION_PATH,
    TRACK_CHAT_IDS,
    TRANSLATION_API_KEY,
    TRANSLATION_URL,
)
from store import Store
from translator import translate_to_english

store = Store(DATABASE_PATH)
client = TelegramClient(SESSION_PATH, API_ID, API_HASH)


def message_text(message) -> str | None:
    return message.message.strip() if message.message and message.message.strip() else None


def media_description(message) -> str | None:
    if not message.media:
        return None
    if isinstance(message.media, types.MessageMediaPhoto):
        return "фото"
    if isinstance(message.media, types.MessageMediaDocument):
        return getattr(message.file, "name", None) or "документ"
    if isinstance(message.media, types.MessageMediaContact):
        return "контакт"
    if isinstance(message.media, types.MessageMediaGeo):
        return "геолокація"
    if isinstance(message.media, types.MessageMediaPoll):
        return "опитування"
    return "медіа"


def is_tracking_paused() -> bool:
    return store.get_setting("paused", "0") == "1"


def chat_allowed(chat_id: int) -> bool:
    return not TRACK_CHAT_IDS or chat_id in TRACK_CHAT_IDS


async def sender_name(sender) -> str:
    if sender is None:
        return "Невідомий відправник"
    first = getattr(sender, "first_name", "") or ""
    last = getattr(sender, "last_name", "") or ""
    name = f"{first} {last}".strip()
    if name:
        return name
    return getattr(sender, "title", None) or getattr(sender, "username", None) or "Невідомий"


async def notification_chat():
    if NOTIFY_CHAT_ID:
        return await client.get_entity(NOTIFY_CHAT_ID)
    return await client.get_me()


async def cache_incoming(event):
    message = event.message
    chat = await event.get_chat()
    chat_id = event.chat_id
    if not chat_allowed(chat_id) or is_tracking_paused():
        return

    sender = await event.get_sender()
    store.cache_message(
        chat_id,
        message.id,
        getattr(sender, "id", None),
        await sender_name(sender),
        message_text(message),
        media_description(message),
    )


async def send_notice(
    kind: str,
    chat,
    chat_id: int,
    message_id: int,
    sender_id: int | None,
    sender_name_text: str,
    old_text: str | None = None,
    new_text: str | None = None,
    media: str | None = None,
):
    chat_title = getattr(chat, "title", None) or await sender_name(chat)
    occurred = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    notice_id = store.add_notice(
        kind=kind,
        chat_id=chat_id,
        chat_name=chat_title,
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name_text,
        old_text=old_text,
        new_text=new_text,
        media=media,
        occurred_at=occurred,
    )

    if kind == "edit":
        title = f"✏️ Повідомлення змінено"
        body = (
            f"<b>Було:</b> {html.escape(old_text or '[текст відсутній у кеші]')}\n"
            f"<b>Стало:</b> {html.escape(new_text or '[текст видалено]')}"
        )
    else:
        title = "🗑 Повідомлення видалено"
        body = (
            f"<b>Текст/медіа:</b> "
            f"{html.escape(old_text or ('[' + media + ']' if media else '[текст відсутній у кеші]'))}"
        )

    text = (
        f"{title}\n"
        f"<b>Чат:</b> {html.escape(chat_title)}\n"
        f"<b>Автор:</b> {html.escape(sender_name_text)}\n"
        f"<b>Час:</b> {occurred}\n"
        f"<b>ID повідомлення:</b> <code>{message_id}</code>\n\n"
        f"{body}"
    )

    keyboard = types.InlineKeyboardMarkup([
        [
            types.InlineKeyboardButton(
                text="🌐 Перекласти англійською",
                callback_data=f"tr:{notice_id}".encode(),
            ),
            types.InlineKeyboardButton(
                text="👤 Профіль",
                callback_data=f"pr:{notice_id}".encode(),
            ),
        ]
    ])

    await client.send_message(
        await notification_chat(),
        text,
        parse_mode="html",
        link_preview=False,
        buttons=keyboard,
    )


@client.on(events.NewMessage())
async def on_new_message(event):
    await cache_incoming(event)


@client.on(events.MessageEdited())
async def on_edited_message(event):
    chat_id = event.chat_id
    if not chat_allowed(chat_id) or is_tracking_paused():
        return

    message = event.message
    cached = store.get_message(chat_id, message.id)
    sender = await event.get_sender()
    chat = await event.get_chat()
    sender_name_text = (
        cached["sender_name"]
        if cached
        else await sender_name(sender)
    )
    sender_id = cached["sender_id"] if cached else getattr(sender, "id", None)

    await send_notice(
        kind="edit",
        chat=chat,
        chat_id=chat_id,
        message_id=message.id,
        sender_id=sender_id,
        sender_name_text=sender_name_text,
        old_text=cached["text"] if cached else None,
        new_text=message_text(message),
        media=media_description(message),
    )

    store.cache_message(
        chat_id,
        message.id,
        sender_id,
        sender_name_text,
        message_text(message),
        media_description(message),
    )


@client.on(events.MessageDeleted)
async def on_deleted_messages(event):
    chat_id = event.chat_id
    if not chat_allowed(chat_id) or is_tracking_paused():
        return

    chat = await client.get_entity(chat_id)
    for message_id in event.deleted_ids:
        cached = store.get_message(chat_id, message_id)
        await send_notice(
            kind="delete",
            chat=chat,
            chat_id=chat_id,
            message_id=message_id,
            sender_id=cached["sender_id"] if cached else None,
            sender_name_text=cached["sender_name"] if cached else "Невідомий відправник",
            old_text=cached["text"] if cached else None,
            media=cached["media"] if cached else None,
        )


@client.on(events.CallbackQuery())
async def on_callback(event):
    data = event.data.decode("utf-8", errors="replace")
    action, separator, raw_id = data.partition(":")
    if not separator:
        await event.answer("Невідомий тип дії", alert=True)
        return

    try:
        notice_id = int(raw_id)
    except ValueError:
        await event.answer("Невірний ідентифікатор", alert=True)
        return

    notice = store.get_notice(notice_id)
    if not notice:
        await event.answer("Запис не знайдено", alert=True)
        return

    if action == "tr":
        source = notice["new_text"] or notice["old_text"] or ""
        if not source:
            await event.answer("Для цього повідомлення немає тексту", alert=True)
            return
        await event.answer("Перекладаю...")
        try:
            translated = await translate_to_english(
                source,
                TRANSLATION_URL,
                TRANSLATION_API_KEY,
            )
            base_text = event.message.message or ""
            await event.edit(
                f"{base_text}\n\n"
                f"<b>🌐 English:</b>\n{html.escape(translated)}",
                parse_mode="html",
                buttons=event.message.buttons,
            )
        except Exception as exc:
            await event.answer(f"Помилка перекладу: {exc}", alert=True)

    elif action == "pr":
        sender_id = notice["sender_id"]
        if not sender_id:
            await event.answer("ID відправника недоступний", alert=True)
            return

        await event.answer("Завантажую профіль...")
        try:
            sender = await client.get_entity(sender_id)
            lines = [
                "👤 <b>Інформація про відправника</b>",
                f"<b>Імʼя:</b> {html.escape(await sender_name(sender))}",
                f"<b>ID:</b> <code>{sender_id}</code>",
            ]
            username = getattr(sender, "username", None)
            if username:
                lines.append(f"<b>Username:</b> @{html.escape(username)}")

            full = await client(functions.users.GetFullUserRequest(sender))
            about = getattr(full.full_user, "about", None)
            if about:
                lines.append(f"<b>Про себе:</b> {html.escape(about)}")

            base_text = event.message.message or ""
            await event.edit(
                f"{base_text}\n\n" + "\n".join(lines),
                parse_mode="html",
                buttons=event.message.buttons,
            )
        except Exception as exc:
            await event.answer(f"Не вдалося отримати профіль: {exc}", alert=True)


@client.on(events.NewMessage(outgoing=True, from_users="me"))
async def on_saved_commands(event):
    me = await client.get_me()
    if event.chat_id != me.id:
        return

    text = (event.raw_text or "").strip()
    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    command = parts[0].lower()
    argument = parts[1].strip() if len(parts) > 1 else ""

    if command == "/pause":
        store.set_setting("paused", "1")
        await event.reply("⏸ Відстеження призупинено")
    elif command == "/resume":
        store.set_setting("paused", "0")
        await event.reply("▶️ Відстеження відновлено")
    elif command == "/track" and argument:
        try:
            chat_id = int(argument)
        except ValueError:
            await event.reply("Використання: /track <chat_id>")
            return
        TRACK_CHAT_IDS.add(chat_id)
        await event.reply(f"✅ Додано чат <code>{chat_id}</code> до відстеження")
    elif command == "/untrack" and argument:
        try:
            chat_id = int(argument)
        except ValueError:
            await event.reply("Використання: /untrack <chat_id>")
            return
        TRACK_CHAT_IDS.discard(chat_id)
        await event.reply(f"✅ Прибрано чат <code>{chat_id}</code> з відстеження")
    elif command == "/status":
        state = "призупинено" if is_tracking_paused() else "активне"
        chats = ", ".join(str(chat_id) for chat_id in sorted(TRACK_CHAT_IDS)) or "усі доступні чати"
        await event.reply(
            f"Статус: <b>{state}</b>\n"
            f"Відстежувані чати: <code>{html.escape(chats)}</code>",
            parse_mode="html",
        )
    elif command == "/help":
        await event.reply(
            "<b>Команди</b>\n"
            "/status — поточний стан\n"
            "/pause — призупинити\n"
            "/resume — відновити\n"
            "/track 123456789 — додати чат\n"
            "/untrack 123456789 — прибрати чат",
            parse_mode="html",
        )


async def main():
    await client.start(phone=PHONE or None)
    me = await client.get_me()
    print(f"Userbot запущено для @{me.username or me.first_name}")
    print("Команди керування надішліть собі в «Збережені повідомлення»: /help")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())

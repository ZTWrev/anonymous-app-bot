import os
import json
import logging
import random
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATA_FILE = "bot_data.json"

NAME, REASON, ROOM_INPUT, NICKNAME = range(4)

NICK_PREFIXES = ["Скрытный", "Тихий", "Хитрый", "Смелый", "Дикий", "Быстрый", "Ленивый", "Мудрый", "Тёмный", "Светлый"]
NICK_NOUNS = ["Лис", "Волк", "Кот", "Сов", "Панд", "Енот", "Дракон", "Феникс", "Тень", "Призрак"]

def load_data():
    if Path(DATA_FILE).exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"applications": [], "approved": [], "users": {}, "rooms": {}, "blocks": [], "reports": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def gen_nick():
    return f"{random.choice(NICK_PREFIXES)} {random.choice(NICK_NOUNS)}_{random.randint(10, 99)}"

def main_kb(is_admin):
    if is_admin:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Заявки", callback_data="admin_apps")],
            [InlineKeyboardButton("✅ Принятые", callback_data="admin_approved")],
            [InlineKeyboardButton("🚫 Заблокировать", callback_data="admin_block_list")],
            [InlineKeyboardButton("📢 Анонимный чат", callback_data="admin_chat")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Подать заявку", callback_data="apply")],
        [InlineKeyboardButton("💬 Анонимный чат", callback_data="anon_menu")],
    ])

def chat_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Создать комнату", callback_data="room_create")],
        [InlineKeyboardButton("📋 Список комнат", callback_data="room_list")],
        [InlineKeyboardButton("🔄 Сменить ник", callback_data="change_nick")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])

def room_actions_kb(room_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✉️ Писать сюда", callback_data=f"msg_{room_id}")],
        [InlineKeyboardButton("👥 Участники", callback_data=f"members_{room_id}")],
        [InlineKeyboardButton("🚪 Выйти", callback_data=f"leave_{room_id}")],
        [InlineKeyboardButton("⚠️ Пожаловаться", callback_data=f"report_{room_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="anon_menu")],
    ])

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_data()
    data["users"][str(uid)] = {
        "name": update.effective_user.full_name,
        "username": update.effective_user.username,
        "nick": data["users"].get(str(uid), {}).get("nick") or gen_nick(),
    }
    save_data(data)
    is_admin = uid == ADMIN_ID

    if is_admin:
        text = "👑 Панель администратора"
    else:
        text = (
            "👋 Добро пожаловать!\n\n"
            "📝 Подать заявку — заполни анкету для доступа\n"
            "💬 Анонимный чат — общайся анонимно"
        )
    await update.message.reply_text(text, reply_markup=main_kb(is_admin))

async def back_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    is_admin = uid == ADMIN_ID
    await query.edit_message_text(
        "👑 Панель администратора" if is_admin else "👋 Главное меню",
        reply_markup=main_kb(is_admin))

async def apply_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введи своё имя:")
    return NAME

async def apply_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["app_name"] = update.message.text
    await update.message.reply_text("Напиши, зачем тебе нужен доступ:")
    return REASON

async def apply_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_data()
    app_id = str(uuid4())[:8]
    data["applications"].append({
        "id": app_id, "user_id": uid,
        "name": ctx.user_data["app_name"],
        "username": update.effective_user.username or "нет",
        "reason": update.message.text,
        "date": datetime.now().isoformat(),
    })
    save_data(data)
    await update.message.reply_text("✅ Заявка отправлена!")

    if ADMIN_ID:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Принять", callback_data=f"approve_{app_id}"),
             InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{app_id}")]
        ])
        ui = f"@{update.effective_user.username}" if update.effective_user.username else f"id{uid}"
        await ctx.bot.send_message(
            ADMIN_ID,
            f"📩 Новая заявка #{app_id}\n"
            f"Имя: {ctx.user_data['app_name']}\n"
            f"User: {ui}\n"
            f"Причина: {update.message.text}",
            reply_markup=kb)
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

async def approve_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, app_id = query.data.split("_", 1)
    data = load_data()
    app = next((a for a in data["applications"] if a["id"] == app_id), None)
    if not app:
        await query.edit_message_text("⚠️ Заявка уже обработана.")
        return
    data["applications"].remove(app)
    if action == "approve":
        data["approved"].append(app)
        await query.edit_message_text(f"✅ Заявка #{app_id} принята.")
        await ctx.bot.send_message(app["user_id"],
            "✅ Твоя заявка принята! Теперь тебе доступен анонимный чат.")
    else:
        await query.edit_message_text(f"❌ Заявка #{app_id} отклонена.")
        await ctx.bot.send_message(app["user_id"],
            "❌ Твоя заявка отклонена. Если хочешь, попробуй ещё раз.")
    save_data(data)

async def admin_apps(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    if not data["applications"]:
        await query.edit_message_text("📭 Нет новых заявок.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))
        return
    lines = []
    for a in data["applications"]:
        lines.append(
            f"#{a['id']} | {a['name']} | @{a['username']}\n"
            f"  └ {a['reason'][:80]}")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_apps")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text("📋 Заявки:\n\n" + "\n\n".join(lines), reply_markup=kb)

async def admin_approved(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    if not data["approved"]:
        await query.edit_message_text("✅ Нет принятых пользователей.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))
        return
    lines = [f"{i+1}. {a['name']} | @{a['username']}" for i, a in enumerate(data["approved"])]
    lines.append(f"\nВсего: {len(data['approved'])}")
    await query.edit_message_text("✅ Принятые:\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))

async def admin_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    rooms = data.get("rooms", {})
    total_users = len(data.get("users", {}))
    total_approved = len(data.get("approved", []))
    total_apps = len(data.get("applications", []))
    total_rooms = len(rooms)
    total_messages = sum(len(r.get("messages", [])) for r in rooms.values())
    total_blocks = len(data.get("blocks", []))
    total_reports = len(data.get("reports", []))

    text = (
        f"📊 Статистика\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"✅ Принято: {total_approved}\n"
        f"📋 Ожидают: {total_apps}\n"
        f"💬 Комнат: {total_rooms}\n"
        f"✉️ Сообщений: {total_messages}\n"
        f"🚫 Заблокировано: {total_blocks}\n"
        f"⚠️ Репортов: {total_reports}"
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))

async def admin_block_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    approved = data.get("approved", [])
    if not approved:
        await query.edit_message_text("Нет принятых пользователей для блокировки.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))
        return
    kb = []
    for a in approved:
        uid = a["user_id"]
        blocked = uid in data.get("blocks", [])
        label = f"{'🔓' if blocked else '🔒'} {a['name']} @{a['username']}"
        kb.append([InlineKeyboardButton(label, callback_data=f"toggle_block_{uid}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    await query.edit_message_text("🚫 Управление блокировками:", reply_markup=InlineKeyboardMarkup(kb))

async def toggle_block(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_", 2)[2])
    data = load_data()
    blocks = data.setdefault("blocks", [])
    if uid in blocks:
        blocks.remove(uid)
        await query.edit_message_text(f"✅ Пользователь разблокирован.")
    else:
        blocks.append(uid)
        await query.edit_message_text(f"🚫 Пользователь заблокирован.")
    save_data(data)

# ─── Анонимный чат ───────────────────────────────────────────────

async def anon_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = load_data()

    if uid == ADMIN_ID:
        await admin_chat_menu(query, data)
        return

    if uid in data.get("blocks", []):
        await query.edit_message_text("⛔ Ты заблокирован.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("◀️ На главную", callback_data="back_main")]]))
        return

    approved_ids = [a["user_id"] for a in data.get("approved", [])]
    if uid not in approved_ids:
        await query.edit_message_text(
            "⛔ Доступ только для принятых пользователей.\nПодай заявку через меню.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))
        return

    nick = data["users"].get(str(uid), {}).get("nick", "Неизвестный")
    rooms = data.get("rooms", {})
    my_rooms = sum(1 for r in rooms.values() if uid in r.get("members", []))
    text = f"💬 Анонимный чат\nТвой ник: {nick}\nТы в комнатах: {my_rooms}"
    await query.edit_message_text(text, reply_markup=chat_menu_kb())

async def change_nick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введи новый ник (или отправь /skip для случайного):")
    return NICKNAME

async def set_nick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    data = load_data()
    if text == "/skip" or not text:
        nick = gen_nick()
    elif len(text) > 30:
        await update.message.reply_text("❌ Слишком длинный ник (макс 30 символов). Попробуй ещё раз:")
        return NICKNAME
    else:
        nick = text
    data["users"][str(uid)]["nick"] = nick
    save_data(data)
    await update.message.reply_text(f"✅ Твой ник: {nick}")
    return ConversationHandler.END

async def room_create(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["room_action"] = "create"
    await query.edit_message_text("Введи название комнаты (тему):")
    return ROOM_INPUT

async def room_create_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    topic = update.message.text.strip()
    data = load_data()
    room_id = str(uuid4())[:6]
    rooms = data.setdefault("rooms", {})
    rooms[room_id] = {
        "topic": topic[:50],
        "owner": uid,
        "members": [uid],
        "messages": [],
        "created": datetime.now().isoformat(),
    }
    save_data(data)
    await update.message.reply_text(
        f"✅ Комната «{topic[:50]}» создана!\n"
        f"ID: {room_id}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Войти", callback_data=f"enter_{room_id}")]]))
    return ConversationHandler.END

async def room_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    rooms = data.get("rooms", {})
    if not rooms:
        await query.edit_message_text("📭 Нет активных комнат. Создай первую!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Создать", callback_data="room_create")],
                                                [InlineKeyboardButton("◀️ Назад", callback_data="anon_menu")]]))
        return
    kb = []
    for rid, r in rooms.items():
        label = f"{r['topic']} ({len(r['members'])} чел)"
        kb.append([InlineKeyboardButton(label, callback_data=f"enter_{rid}")])
    kb.append([InlineKeyboardButton("🔍 Войти по ID", callback_data="room_join_by_id")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="anon_menu")])
    await query.edit_message_text("📋 Доступные комнаты:", reply_markup=InlineKeyboardMarkup(kb))

async def room_join_by_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["room_action"] = "join"
    await query.edit_message_text("Введи ID комнаты (6 символов):")
    return ROOM_INPUT

async def room_join_by_id_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    room_id = update.message.text.strip().lower()
    data = load_data()
    rooms = data.get("rooms", {})
    room = rooms.get(room_id)
    if not room:
        await update.message.reply_text("❌ Комната не найдена. Проверь ID.")
        return ConversationHandler.END
    if uid in room["members"]:
        await update.message.reply_text("ℹ️ Ты уже в этой комнате.")
        return ConversationHandler.END
    room["members"].append(uid)
    save_data(data)
    nick = data["users"].get(str(uid), {}).get("nick", "Неизвестный")
    await notify_room(ctx, room_id, f"➕ {nick} присоединился к комнате")
    await update.message.reply_text(f"✅ Ты вошёл в комнату «{room['topic']}»",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Открыть чат", callback_data=f"enter_{room_id}")]]))
    return ConversationHandler.END

async def enter_room(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, room_id = query.data.split("_", 1)
    data = load_data()
    rooms = data.get("rooms", {})
    room = rooms.get(room_id)
    if not room:
        await query.edit_message_text("❌ Комната удалена.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="anon_menu")]]))
        return
    uid = query.from_user.id
    if uid not in room["members"] and uid != ADMIN_ID:
        room["members"].append(uid)
        save_data(data)
        nick = data["users"].get(str(uid), {}).get("nick", "Неизвестный")
        await notify_room(ctx, room_id, f"➕ {nick} присоединился к комнате")
    await show_room(query, room_id, data)

async def show_room(query, room_id, data):
    room = data.get("rooms", {}).get(room_id)
    if not room:
        await query.edit_message_text("❌ Комната не найдена.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="anon_menu")]]))
        return
    msg = f"💬 {room['topic']}\n👥 {len(room['members'])} участников\n\n"
    msgs = room.get("messages", [])
    if msgs:
        for m in msgs[-10:]:
            t = m.get("time", "")[-8:] if m.get("time") else ""
            msg += f"[{t}] {m['nick']}: {m['text']}\n"
    else:
        msg += "Пока нет сообщений. Напиши первым!"
    await query.edit_message_text(msg, reply_markup=room_actions_kb(room_id))

async def room_members(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, room_id = query.data.split("_", 1)
    data = load_data()
    room = data.get("rooms", {}).get(room_id)
    if not room:
        await query.edit_message_text("❌ Комната не найдена.")
        return
    users = data.get("users", {})
    lines = [f"👥 Участники «{room['topic']}»:\n"]
    for muid in room["members"]:
        nick = users.get(str(muid), {}).get("nick", "Неизвестный")
        lines.append(f"  • {nick}")
    await query.edit_message_text("\n".join(lines), reply_markup=room_actions_kb(room_id))

async def leave_room(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    _, room_id = query.data.split("_", 1)
    data = load_data()
    rooms = data.get("rooms", {})
    room = rooms.get(room_id)
    if not room:
        await query.edit_message_text("❌ Комната не найдена.")
        return
    if uid in room["members"]:
        room["members"].remove(uid)
        nick = data["users"].get(str(uid), {}).get("nick", "Неизвестный")
        await notify_room(ctx, room_id, f"➖ {nick} покинул комнату")
    if not room["members"]:
        del rooms[room_id]
    save_data(data)
    await query.edit_message_text("🚪 Ты вышел из комнаты.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ К комнатам", callback_data="room_list")]]))

async def report_room(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    _, room_id = query.data.split("_", 1)
    data = load_data()
    room = data.get("rooms", {}).get(room_id)
    if not room:
        return
    data.setdefault("reports", []).append({
        "user_id": uid, "room_id": room_id,
        "topic": room["topic"], "date": datetime.now().isoformat(),
    })
    save_data(data)
    await query.edit_message_text("⚠️ Жалоба отправлена администратору.",
        reply_markup=room_actions_kb(room_id))
    if ADMIN_ID:
        nick = data["users"].get(str(uid), {}).get("nick", "Неизвестный")
        await ctx.bot.send_message(ADMIN_ID,
            f"⚠️ Репорт от {nick}\nКомната: {room['topic']} ({room_id})")

async def notify_room(ctx, room_id, text):
    data = load_data()
    room = data.get("rooms", {}).get(room_id)
    if not room:
        return
    for muid in room["members"]:
        try:
            await ctx.bot.send_message(muid, f"ℹ️ {text}")
        except Exception:
            pass

async def msg_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, room_id = query.data.split("_", 1)
    ctx.user_data["chat_room"] = room_id
    await query.edit_message_text(
        "✏️ Режим чата включён. Отправляй сообщения.\n"
        "Для выхода напиши /exit",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад в комнату", callback_data=f"enter_{room_id}")]]))

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    uid = update.effective_user.id
    text = update.message.text.strip()
    data = load_data()

    # Broadcast for admin
    if uid == ADMIN_ID and text.startswith("/broadcast "):
        msg = text[11:]
        approved = data.get("approved", [])
        sent = 0
        for a in approved:
            try:
                await ctx.bot.send_message(a["user_id"], f"📢 {msg}")
                sent += 1
            except Exception:
                pass
        await update.message.reply_text(f"✅ Разослано {sent} пользователям.")
        return

    if text == "/exit":
        ctx.user_data.pop("chat_room", None)
        await update.message.reply_text("🚪 Выход из чата.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Меню чата", callback_data="anon_menu")]]))
        return

    # Chat mode
    room_id = ctx.user_data.get("chat_room")
    if not room_id:
        return
    rooms = data.get("rooms", {})
    room = rooms.get(room_id)
    if not room or uid not in room["members"]:
        await update.message.reply_text("❌ Ты не в этой комнате.")
        ctx.user_data.pop("chat_room", None)
        return
    if uid in data.get("blocks", []):
        await update.message.reply_text("⛔ Ты заблокирован.")
        return

    nick = data["users"].get(str(uid), {}).get("nick", "Неизвестный")
    ts = datetime.now().strftime("%H:%M")
    room["messages"].append({"user_id": uid, "nick": nick, "text": text, "time": ts})
    if len(room["messages"]) > 200:
        room["messages"] = room["messages"][-200:]
    save_data(data)

    for muid in room["members"]:
        if muid != uid:
            try:
                await ctx.bot.send_message(muid, f"💬 [{ts}] {nick}: {text}")
            except Exception:
                pass

    # Admin sees all with real identity
    if ADMIN_ID:
        real = data["users"].get(str(uid), {}).get("name", str(uid))
        try:
            await ctx.bot.send_message(ADMIN_ID, f"👁 [{room['topic']}] {real} ({nick}): {text}")
        except Exception:
            pass

async def admin_chat_menu(query, data):
    rooms = data.get("rooms", {})
    if not rooms:
        await query.edit_message_text("📭 Нет активных комнат.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))
        return
    kb = []
    for rid, r in rooms.items():
        kb.append([InlineKeyboardButton(f"{r['topic']} ({len(r['members'])} чел, {len(r['messages'])} сообщ)",
                                        callback_data=f"admin_room_{rid}")])
    kb.append([InlineKeyboardButton("🚫 Блокировки", callback_data="admin_block_list")])
    kb.append([InlineKeyboardButton("⚠️ Репорты", callback_data="admin_reports")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    await query.edit_message_text("👑 Администрирование чата:", reply_markup=InlineKeyboardMarkup(kb))

async def admin_room_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, room_id = query.data.split("_", 2)
    data = load_data()
    room = data.get("rooms", {}).get(room_id)
    if not room:
        await query.edit_message_text("❌ Комната не найдена.")
        return
    msg = f"👑 Комната «{room['topic']}»\n👥 {len(room['members'])} участников\n\n"
    users = data.get("users", {})
    members_info = []
    for muid in room["members"]:
        u = users.get(str(muid), {})
        nick = u.get("nick", "?")
        real = u.get("name", str(muid))
        members_info.append(f"  • {nick} ({real})")
    msg += "\n".join(members_info)
    msg += "\n\n📝 Последние сообщения:\n"
    for m in room.get("messages", [])[-10:]:
        real = users.get(str(m["user_id"]), {}).get("name", str(m["user_id"]))
        msg += f"\n[{m.get('time','')}] {real} ({m['nick']}): {m['text']}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data=f"admin_room_{room_id}")],
        [InlineKeyboardButton("◀️ К списку", callback_data="admin_chat")],
    ])
    await query.edit_message_text(msg, reply_markup=kb)

async def admin_reports(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    reports = data.get("reports", [])
    if not reports:
        await query.edit_message_text("Нет репортов.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_chat")]]))
        return
    lines = []
    for r in reports[-10:]:
        nick = data.get("users", {}).get(str(r["user_id"]), {}).get("nick", "?")
        lines.append(f"• {nick} → {r['topic']} ({r['room_id']})")
    await query.edit_message_text("⚠️ Репорты:\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_chat")]]))

def main():
    if not TOKEN or not ADMIN_ID:
        logger.error("BOT_TOKEN и ADMIN_ID должны быть в .env файле")
        return
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    # Conversation: application
    app_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(apply_start, pattern="^apply$")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_name)],
            REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_reason)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Conversation: room input (create or join)
    async def room_input_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        action = ctx.user_data.get("room_action")
        if action == "create":
            return await room_create_done(update, ctx)
        elif action == "join":
            return await room_join_by_id_done(update, ctx)
        await update.message.reply_text("❌ Ошибка. Попробуй снова.")
        return ConversationHandler.END

    room_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(room_create, pattern="^room_create$"),
                      CallbackQueryHandler(room_join_by_id, pattern="^room_join_by_id$")],
        states={
            ROOM_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, room_input_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Conversation: change nick
    nick_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(change_nick, pattern="^change_nick$")],
        states={
            NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_nick)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(app_conv)
    app.add_handler(room_conv)
    app.add_handler(nick_conv)

    # Admin callbacks
    app.add_handler(CallbackQueryHandler(approve_reject, pattern="^(approve|reject)_"))
    app.add_handler(CallbackQueryHandler(toggle_block, pattern="^toggle_block_"))
    app.add_handler(CallbackQueryHandler(admin_apps, pattern="^admin_apps$"))
    app.add_handler(CallbackQueryHandler(admin_approved, pattern="^admin_approved$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_block_list, pattern="^admin_block_list$"))
    app.add_handler(CallbackQueryHandler(admin_reports, pattern="^admin_reports$"))
    app.add_handler(CallbackQueryHandler(admin_room_view, pattern="^admin_room_"))

    # User menu callbacks
    app.add_handler(CallbackQueryHandler(anon_menu, pattern="^anon_menu$"))
    app.add_handler(CallbackQueryHandler(room_list, pattern="^room_list$"))
    app.add_handler(CallbackQueryHandler(enter_room, pattern="^enter_"))
    app.add_handler(CallbackQueryHandler(room_members, pattern="^members_"))
    app.add_handler(CallbackQueryHandler(leave_room, pattern="^leave_"))
    app.add_handler(CallbackQueryHandler(report_room, pattern="^report_"))
    app.add_handler(CallbackQueryHandler(msg_mode, pattern="^msg_"))

    # Admin chat management
    app.add_handler(CallbackQueryHandler(admin_chat_menu_start, pattern="^admin_chat$"))

    # Navigation
    app.add_handler(CallbackQueryHandler(back_main, pattern="^back_main$"))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

# Separate handler because it needs query not update
async def admin_chat_menu_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    await admin_chat_menu(query, data)

if __name__ == "__main__":
    main()

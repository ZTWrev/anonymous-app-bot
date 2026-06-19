import os
import json
import logging
from pathlib import Path
from uuid import uuid4
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

NAME, REASON = range(2)
anon_rooms = {}

def load_data():
    if Path(DATA_FILE).exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"applications": [], "approved": [], "users": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_kb(items_per_row=1):
    return InlineKeyboardMarkup.from_column if items_per_row == 1 else InlineKeyboardMarkup

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_data()
    data["users"][str(uid)] = {"name": update.effective_user.full_name, "username": update.effective_user.username}
    save_data(data)

    if uid == ADMIN_ID:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Заявки", callback_data="admin_apps")],
            [InlineKeyboardButton("✅ Принятые", callback_data="admin_approved")],
            [InlineKeyboardButton("📢 Анонимный чат", callback_data="admin_chat")],
        ])
        await update.message.reply_text("👑 Панель администратора", reply_markup=kb)
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Подать заявку", callback_data="apply")],
            [InlineKeyboardButton("💬 Анонимный чат", callback_data="anon_chat")],
        ])
        await update.message.reply_text(
            "Привет! Что хочешь сделать?\n"
            "📝 Подать заявку — заполни анкету\n"
            "💬 Анонимный чат — общайся анонимно с другими", reply_markup=kb)

async def menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "apply":
        await query.edit_message_text("Введи своё имя:")
        return NAME

    elif data == "anon_chat":
        await anon_chat_menu(query, ctx)

    elif data == "admin_apps":
        await show_applications(query, ctx)
    elif data == "admin_approved":
        await show_approved(query, ctx)
    elif data == "admin_chat":
        await admin_anon_chat(query, ctx)

    return ConversationHandler.END if data in ("apply",) else None

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
        "reason": update.message.text
    })
    save_data(data)

    await update.message.reply_text("✅ Заявка отправлена! Жди решения администратора.")

    if ADMIN_ID:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Принять", callback_data=f"approve_{app_id}"),
             InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{app_id}")]
        ])
        user_info = f"@{update.effective_user.username}" if update.effective_user.username else f"id{uid}"
        await ctx.bot.send_message(
            ADMIN_ID,
            f"📩 Новая заявка #{app_id}\n"
            f"Имя: {ctx.user_data['app_name']}\n"
            f"User: {user_info}\n"
            f"Причина: {update.message.text}",
            reply_markup=kb)

    return ConversationHandler.END

async def approve_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, app_id = query.data.split("_", 1)
    data = load_data()
    app = next((a for a in data["applications"] if a["id"] == app_id), None)
    if not app:
        await query.edit_message_text("Заявка уже обработана.")
        return

    data["applications"].remove(app)

    if action == "approve":
        data["approved"].append(app)
        await query.edit_message_text(f"✅ Заявка {app_id} принята.")
        await ctx.bot.send_message(app["user_id"], "✅ Твоя заявка принята! Теперь ты можешь пользоваться анонимным чатом.")
    else:
        await query.edit_message_text(f"❌ Заявка {app_id} отклонена.")
        await ctx.bot.send_message(app["user_id"], "❌ Твоя заявка отклонена.")

    save_data(data)

async def show_applications(query, ctx):
    data = load_data()
    if not data["applications"]:
        await query.edit_message_text("📭 Нет новых заявок.")
        return
    lines = []
    for a in data["applications"]:
        lines.append(
            f"#{a['id']} | {a['name']} | @{a['username']}\n"
            f"  → {a['reason'][:100]}")
    await query.edit_message_text("📋 Заявки:\n\n" + "\n\n".join(lines))

async def show_approved(query, ctx):
    data = load_data()
    if not data["approved"]:
        await query.edit_message_text("Нет принятых пользователей.")
        return
    lines = [f"#{a['id']} | {a['name']} | @{a['username']}" for a in data["approved"]]
    await query.edit_message_text("✅ Принятые:\n" + "\n".join(lines))

async def anon_chat_menu(query, ctx):
    data = load_data()
    uid = query.from_user.id
    if str(uid) == str(ADMIN_ID):
        await admin_anon_chat(query, ctx)
        return
    approved_ids = [a["user_id"] for a in data.get("approved", [])]
    if uid not in approved_ids:
        await query.edit_message_text(
            "⛔ Доступ только для принятых пользователей.\n"
            "Сначала подай заявку через меню.")
        return

    user = data["users"].get(str(uid), {})
    uname = user.get("name", "Неизвестный")
    await ctx.bot_data.setdefault("anon_users", {})[uid] = uname

    if not anon_rooms:
        room_id = str(uuid4())[:6]
        anon_rooms[room_id] = {"users": set(), "messages": []}
    else:
        room_id = next(iter(anon_rooms))

    room = anon_rooms[room_id]
    room["users"].add(uid)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✉️ Написать в чат", callback_data=f"send_{room_id}")],
        [InlineKeyboardButton("🔄 Найти собеседника", callback_data=f"pair_{room_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    msg = f"💬 Анонимный чат\nВ комнате: {len(room['users'])} чел.\n\n"
    if room["messages"]:
        msg += "Последние сообщения:\n" + "\n".join(
            f"Аноним: {m['text']}" for m in room["messages"][-5:])
    else:
        msg += "Пока нет сообщений. Напиши первым!"

    await query.edit_message_text(msg, reply_markup=kb)

async def admin_anon_chat(query, ctx):
    ks = []
    if anon_rooms:
        for rid, room in anon_rooms.items():
            ks.append([InlineKeyboardButton(f"Комната {rid} ({len(room['users'])} чел)", callback_data=f"room_{rid}")])
    ks.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])

    if anon_rooms:
        await query.edit_message_text("👑 Выбери комнату для просмотра:", reply_markup=InlineKeyboardMarkup(ks))
    else:
        await query.edit_message_text("Нет активных комнат.", reply_markup=InlineKeyboardMarkup(ks))

async def room_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, room_id = query.data.split("_", 1)
    room = anon_rooms.get(room_id)
    if not room:
        await query.edit_message_text("Комната не найдена.")
        return
    msg = f"Комната {room_id}\nУчастников: {len(room['users'])}\n\n"
    if room["messages"]:
        msg += "\n".join(f"Аноним: {m['text']}" for m in room["messages"][-20:])
    else:
        msg += "Нет сообщений."
    await query.edit_message_text(msg)

async def back_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id == ADMIN_ID:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Заявки", callback_data="admin_apps")],
            [InlineKeyboardButton("✅ Принятые", callback_data="admin_approved")],
            [InlineKeyboardButton("📢 Анонимный чат", callback_data="admin_chat")],
        ])
        await query.edit_message_text("👑 Панель администратора", reply_markup=kb)
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Подать заявку", callback_data="apply")],
            [InlineKeyboardButton("💬 Анонимный чат", callback_data="anon_chat")],
        ])
        await query.edit_message_text("Главное меню", reply_markup=kb)

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    uid = update.effective_user.id
    text = update.message.text
    data = load_data()

    if uid == ADMIN_ID and text.startswith("/broadcast"):
        msg = text.replace("/broadcast", "", 1).strip()
        if msg:
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

    # anonymous chat message
    if uid in ctx.bot_data.setdefault("anon_users", {}):
        for room_id, room in anon_rooms.items():
            if uid in room["users"]:
                room["messages"].append({"user_id": uid, "text": text})
                for muid in room["users"]:
                    if muid != uid:
                        try:
                            await ctx.bot.send_message(muid, f"💬 Аноним: {text}")
                        except Exception:
                            pass
                if ADMIN_ID:
                    uname = ctx.bot_data["anon_users"].get(uid, "Неизвестный")
                    await ctx.bot.send_message(ADMIN_ID, f"👁 {uname}: {text}")
                return

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

def main():
    if not TOKEN or not ADMIN_ID:
        logger.error("BOT_TOKEN и ADMIN_ID должны быть в .env файле")
        return

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_callback, pattern="^apply$")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_name)],
            REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_reason)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(approve_reject, pattern="^(approve|reject)_"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^(apply|anon_chat|admin_apps|admin_approved|admin_chat)$"))
    app.add_handler(CallbackQueryHandler(room_callback, pattern="^room_"))
    app.add_handler(CallbackQueryHandler(back_main, pattern="^back_main$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Otaplama Biznesi - Telegram Bot
Zakazlar | Prixodlar | Kassa | Ishchilar Reytingi
"""

import logging
import re
import json
import os
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from database import Database

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== SOZLAMALAR ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", ""8918826829:AAGoTikt8LYIfys8mWjixizR0Td_DtaHQac"")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(",")))

# Guruh turlari
GROUP_TYPES = {
    "zakazlar": "📦 Zakazlar guruhi",
    "prixodlar": "💰 Prixodlar guruhi",
    "kassa": "🏦 Kassa guruhi",
    "ishchilar": "⭐ Ishchilar guruhi",
}

db = Database("otaplama.db")


# ==================== YORDAMCHI FUNKSIYALAR ====================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def format_money(amount: float) -> str:
    return f"{amount:,.0f} so'm"

def now_str() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M")

def today_str() -> str:
    return date.today().strftime("%d.%m.%Y")


# ==================== START / YORDAM ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Assalomu alaykum! Otaplama Bot!*\n\n"
        "Bu bot quyidagi guruhlarni boshqaradi:\n\n"
        "📦 *Zakazlar guruhi*\n"
        "`#zakaz Ism Familiya 500000`\n"
        "`#chiqdi Ism Familiya` — zakaz chiqdi\n\n"
        "💰 *Prixodlar guruhi*\n"
        "`#prixod Postavshik nomi 2000000`\n\n"
        "🏦 *Kassa guruhi*\n"
        "`#kirim Ism/Tashkilot 500000`\n"
        "`#chiqim Ism/Tashkilot 300000`\n\n"
        "⭐ *Ishchilar (faqat admin)*\n"
        "`/ball @username 10 Yaxshi ish`\n\n"
        "📊 *Hisobotlar*\n"
        "`/hisobot` — bugungi hisobot\n"
        "`/oylik` — oylik hisobot\n"
        "`/reyting` — ishchilar reytingi\n\n"
        "⚙️ *Admin buyruqlari*\n"
        "`/guruh_tur` — bu guruhni sozlash\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ==================== GURUH SOZLASH ====================

async def guruh_tur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin guruh turini belgilaydi"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Faqat adminlar uchun!")
        return

    chat_id = update.effective_chat.id
    keyboard = [
        [InlineKeyboardButton("📦 Zakazlar guruhi", callback_data=f"settype_zakazlar_{chat_id}")],
        [InlineKeyboardButton("💰 Prixodlar guruhi", callback_data=f"settype_prixodlar_{chat_id}")],
        [InlineKeyboardButton("🏦 Kassa guruhi", callback_data=f"settype_kassa_{chat_id}")],
        [InlineKeyboardButton("⭐ Ishchilar guruhi", callback_data=f"settype_ishchilar_{chat_id}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Bu guruhni qaysi tur deb belgilamoqchisiz?",
        reply_markup=reply_markup
    )

async def settype_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ Faqat adminlar uchun!")
        return

    parts = query.data.split("_")
    group_type = parts[1]
    chat_id = int(parts[2])

    db.set_group_type(chat_id, group_type)
    type_name = GROUP_TYPES.get(group_type, group_type)
    await query.edit_message_text(f"✅ Guruh turi: *{type_name}* deb belgilandi!", parse_mode="Markdown")


# ==================== XABARLARNI TAHLIL QILISH ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    text = update.message.text.strip()

    group_type = db.get_group_type(chat_id)

    if group_type == "zakazlar":
        await handle_zakaz(update, context, text, user, chat_id)
    elif group_type == "prixodlar":
        await handle_prixod(update, context, text, user, chat_id)
    elif group_type == "kassa":
        await handle_kassa(update, context, text, user, chat_id)


# ==================== ZAKAZLAR ====================

async def handle_zakaz(update, context, text, user, chat_id):
    """
    Formatlar:
    #zakaz Ism Familiya 500000 [Obyekt nomi]
    #chiqdi Ism Familiya
    #bekor Ism Familiya
    """
    # Yangi zakaz: #zakaz Ahmad Karimov 750000 Chilonzor
    zakaz_match = re.match(
        r'#zakaz\s+(.+?)\s+([\d\s]+)\s*(.*)$', text, re.IGNORECASE
    )
    if zakaz_match:
        mijoz = zakaz_match.group(1).strip()
        summa_str = zakaz_match.group(2).replace(" ", "")
        obyekt = zakaz_match.group(3).strip() or "—"

        try:
            summa = float(summa_str)
        except ValueError:
            await update.message.reply_text("❌ Summa noto'g'ri formatda!")
            return

        zakaz_id = db.add_zakaz(
            chat_id=chat_id,
            mijoz=mijoz,
            summa=summa,
            obyekt=obyekt,
            qoshgan=f"{user.first_name} {user.last_name or ''}".strip()
        )

        stats = db.get_zakaz_stats(chat_id)
        reply = (
            f"✅ *Yangi zakaz #{zakaz_id} qo'shildi!*\n\n"
            f"👤 Mijoz: *{mijoz}*\n"
            f"💵 Summa: *{format_money(summa)}*\n"
            f"🏠 Obyekt: *{obyekt}*\n"
            f"📅 Sana: {now_str()}\n\n"
            f"📊 *Jami holat:*\n"
            f"  🟢 Faol zakazlar: {stats['faol']}\n"
            f"  ✅ Yopilgan: {stats['yopilgan']}\n"
            f"  💰 Jami summa: {format_money(stats['jami_summa'])}"
        )
        await update.message.reply_text(reply, parse_mode="Markdown")
        return

    # Zakaz chiqdi: #chiqdi Ahmad Karimov
    chiqdi_match = re.match(r'#chiqdi\s+(.+)$', text, re.IGNORECASE)
    if chiqdi_match:
        mijoz = chiqdi_match.group(1).strip()
        result = db.close_zakaz(chat_id, mijoz)

        if result:
            stats = db.get_zakaz_stats(chat_id)
            reply = (
                f"✅ *Zakaz yopildi!*\n\n"
                f"👤 Mijoz: *{result['mijoz']}*\n"
                f"💵 Summa: *{format_money(result['summa'])}*\n"
                f"🏠 Obyekt: *{result['obyekt']}*\n"
                f"📅 Yopildi: {now_str()}\n\n"
                f"📊 *Jami:* {stats['faol']} faol | {stats['yopilgan']} yopilgan"
            )
        else:
            reply = f"❌ *{mijoz}* nomli faol zakaz topilmadi!"

        await update.message.reply_text(reply, parse_mode="Markdown")
        return


# ==================== PRIXODLAR ====================

async def handle_prixod(update, context, text, user, chat_id):
    """
    #prixod PostavshikNomi 2000000 [Izoh]
    """
    match = re.match(r'#prixod\s+(.+?)\s+([\d\s]+)\s*(.*)$', text, re.IGNORECASE)
    if not match:
        return

    postavshik = match.group(1).strip()
    summa_str = match.group(2).replace(" ", "")
    izoh = match.group(3).strip() or "—"

    try:
        summa = float(summa_str)
    except ValueError:
        await update.message.reply_text("❌ Summa noto'g'ri!")
        return

    prixod_id = db.add_prixod(
        chat_id=chat_id,
        postavshik=postavshik,
        summa=summa,
        izoh=izoh,
        qoshgan=f"{user.first_name} {user.last_name or ''}".strip()
    )

    stats = db.get_prixod_stats(chat_id)
    reply = (
        f"📦 *Yangi prixod #{prixod_id}!*\n\n"
        f"🏭 Postavshik: *{postavshik}*\n"
        f"💵 Summa: *{format_money(summa)}*\n"
        f"📝 Izoh: {izoh}\n"
        f"📅 Sana: {now_str()}\n\n"
        f"📊 *Bugungi prixodlar:* {format_money(stats['bugun'])}\n"
        f"📅 *Bu oylik jami:* {format_money(stats['oylik'])}"
    )
    await update.message.reply_text(reply, parse_mode="Markdown")


# ==================== KASSA ====================

async def handle_kassa(update, context, text, user, chat_id):
    """
    #kirim Ism/Tashkilot 500000 [Izoh]
    #chiqim Ism/Tashkilot 300000 [Izoh]
    """
    kirim_match = re.match(r'#kirim\s+(.+?)\s+([\d\s]+)\s*(.*)$', text, re.IGNORECASE)
    chiqim_match = re.match(r'#chiqim\s+(.+?)\s+([\d\s]+)\s*(.*)$', text, re.IGNORECASE)

    match = kirim_match or chiqim_match
    if not match:
        return

    tur = "kirim" if kirim_match else "chiqim"
    kim = match.group(1).strip()
    summa_str = match.group(2).replace(" ", "")
    izoh = match.group(3).strip() or "—"

    try:
        summa = float(summa_str)
    except ValueError:
        await update.message.reply_text("❌ Summa noto'g'ri!")
        return

    db.add_kassa(
        chat_id=chat_id,
        tur=tur,
        kim=kim,
        summa=summa,
        izoh=izoh,
        qoshgan=f"{user.first_name} {user.last_name or ''}".strip()
    )

    balans = db.get_kassa_balans(chat_id)
    emoji = "💚" if tur == "kirim" else "🔴"
    arrow = "⬆️" if tur == "kirim" else "⬇️"

    reply = (
        f"{emoji} *Kassa {tur.upper()}!*\n\n"
        f"👤 Kim: *{kim}*\n"
        f"{arrow} Summa: *{format_money(summa)}*\n"
        f"📝 Izoh: {izoh}\n"
        f"📅 Sana: {now_str()}\n\n"
        f"💰 *Joriy balans: {format_money(balans)}*"
    )
    await update.message.reply_text(reply, parse_mode="Markdown")


# ==================== BALL BERISH (ADMIN) ====================

async def ball_ber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ball @username 10 Yaxshi ish bajardi
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Faqat adminlar uchun!")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📝 Format: `/ball @username 10 Sabab`",
            parse_mode="Markdown"
        )
        return

    username = args[0].lstrip("@")
    try:
        ball = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Ball raqam bo'lishi kerak!")
        return

    sabab = " ".join(args[2:]) if len(args) > 2 else "—"

    db.add_ball(
        username=username,
        ball=ball,
        sabab=sabab,
        admin=f"{update.effective_user.first_name}"
    )

    jami = db.get_worker_balls(username)
    sign = "+" if ball > 0 else ""
    reply = (
        f"⭐ *Ball berildi!*\n\n"
        f"👤 Ishchi: @{username}\n"
        f"🎯 Ball: *{sign}{ball}*\n"
        f"📝 Sabab: {sabab}\n"
        f"📊 Jami ball: *{jami}*"
    )
    await update.message.reply_text(reply, parse_mode="Markdown")


# ==================== HISOBOTLAR ====================

async def hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bugungi hisobot"""
    chat_id = update.effective_chat.id
    group_type = db.get_group_type(chat_id)

    if group_type == "zakazlar":
        await zakaz_hisobot(update, chat_id, "bugun")
    elif group_type == "prixodlar":
        await prixod_hisobot(update, chat_id, "bugun")
    elif group_type == "kassa":
        await kassa_hisobot(update, chat_id, "bugun")
    else:
        await update.message.reply_text(
            "❗ Bu guruh hali sozlanmagan.\n"
            "Admin `/guruh_tur` buyrug'ini ishlatsin.",
            parse_mode="Markdown"
        )

async def oylik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oylik hisobot"""
    chat_id = update.effective_chat.id
    group_type = db.get_group_type(chat_id)

    if group_type == "zakazlar":
        await zakaz_hisobot(update, chat_id, "oy")
    elif group_type == "prixodlar":
        await prixod_hisobot(update, chat_id, "oy")
    elif group_type == "kassa":
        await kassa_hisobot(update, chat_id, "oy")
    else:
        await update.message.reply_text("❗ Guruh sozlanmagan!")

async def zakaz_hisobot(update, chat_id, davr):
    data = db.get_zakaz_hisobot(chat_id, davr)
    davr_text = "📅 Bugungi" if davr == "bugun" else "📆 Oylik"

    text = f"📦 *{davr_text} Zakazlar Hisoboti*\n"
    text += f"🗓 {today_str()}\n"
    text += "━━━━━━━━━━━━━━━\n\n"
    text += f"🟢 Faol zakazlar: *{data['faol']}*\n"
    text += f"✅ Yopilgan: *{data['yopilgan']}*\n"
    text += f"💰 Jami summa: *{format_money(data['jami_summa'])}*\n"
    text += f"💵 Yopilgan summa: *{format_money(data['yopilgan_summa'])}*\n\n"

    if data['yopilganlar']:
        text += "✅ *Yopilgan zakazlar:*\n"
        for z in data['yopilganlar']:
            text += f"  • {z['mijoz']} — {format_money(z['summa'])} | {z['obyekt']}\n"

    if data['faollar']:
        text += "\n🟢 *Faol zakazlar:*\n"
        for z in data['faollar']:
            text += f"  • {z['mijoz']} — {format_money(z['summa'])} | {z['obyekt']}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def prixod_hisobot(update, chat_id, davr):
    data = db.get_prixod_hisobot(chat_id, davr)
    davr_text = "📅 Bugungi" if davr == "bugun" else "📆 Oylik"

    text = f"💰 *{davr_text} Prixodlar Hisoboti*\n"
    text += f"🗓 {today_str()}\n"
    text += "━━━━━━━━━━━━━━━\n\n"
    text += f"📦 Jami prixodlar: *{data['soni']} ta*\n"
    text += f"💵 Jami summa: *{format_money(data['summa'])}*\n\n"

    if data['postavshiklar']:
        text += "🏭 *Postavshiklar bo'yicha:*\n"
        for p in data['postavshiklar']:
            text += f"  • {p['postavshik']}: *{format_money(p['summa'])}* ({p['soni']} ta)\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def kassa_hisobot(update, chat_id, davr):
    data = db.get_kassa_hisobot(chat_id, davr)
    davr_text = "📅 Bugungi" if davr == "bugun" else "📆 Oylik"

    text = f"🏦 *{davr_text} Kassa Hisoboti*\n"
    text += f"🗓 {today_str()}\n"
    text += "━━━━━━━━━━━━━━━\n\n"
    text += f"💚 Kirim: *{format_money(data['kirim'])}*\n"
    text += f"🔴 Chiqim: *{format_money(data['chiqim'])}*\n"
    text += f"💰 Balans: *{format_money(data['balans'])}*\n\n"

    if data['kirimlar']:
        text += "💚 *Kirimlar:*\n"
        for k in data['kirimlar']:
            text += f"  • {k['kim']}: {format_money(k['summa'])}\n"

    if data['chiqimlar']:
        text += "\n🔴 *Chiqimlar:*\n"
        for c in data['chiqimlar']:
            text += f"  • {c['kim']}: {format_money(c['summa'])}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# ==================== REYTING ====================

async def reyting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ishchilar reytingi"""
    workers = db.get_reyting()

    if not workers:
        await update.message.reply_text("📊 Hali ball berilmagan!")
        return

    medals = ["🥇", "🥈", "🥉"]
    text = "⭐ *Ishchilar Reytingi*\n"
    text += f"📅 {datetime.now().strftime('%B %Y')}\n"
    text += "━━━━━━━━━━━━━━━\n\n"

    for i, w in enumerate(workers):
        medal = medals[i] if i < 3 else f"{i+1}."
        text += f"{medal} @{w['username']} — *{w['ball']} ball*\n"

    oy = datetime.now().strftime("%B %Y")
    text += f"\n🏆 *{oy} g'olibi:* @{workers[0]['username']}"

    await update.message.reply_text(text, parse_mode="Markdown")


# ==================== UMUMIY STATISTIKA ====================

async def umumiy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha guruhlar bo'yicha umumiy statistika (faqat admin)"""
    if not is_admin(update.effective_user.id):
        return

    stats = db.get_umumiy_stats()
    text = (
        f"📊 *Umumiy Statistika*\n"
        f"🗓 {today_str()}\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📦 Zakazlar: {stats['zakaz_faol']} faol / {stats['zakaz_yopilgan']} yopilgan\n"
        f"💰 Zakazlar summasi: *{format_money(stats['zakaz_summa'])}*\n\n"
        f"📦 Prixodlar (oy): *{format_money(stats['prixod_oy'])}*\n\n"
        f"🏦 Kassa balansi: *{format_money(stats['kassa_balans'])}*\n"
        f"  💚 Kirim: {format_money(stats['kassa_kirim'])}\n"
        f"  🔴 Chiqim: {format_money(stats['kassa_chiqim'])}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ==================== MAIN ====================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Buyruqlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("guruh_tur", guruh_tur))
    app.add_handler(CommandHandler("ball", ball_ber))
    app.add_handler(CommandHandler("hisobot", hisobot))
    app.add_handler(CommandHandler("oylik", oylik))
    app.add_handler(CommandHandler("reyting", reyting))
    app.add_handler(CommandHandler("umumiy", umumiy))

    # Callback
    app.add_handler(CallbackQueryHandler(settype_callback, pattern=r"^settype_"))

    # Xabarlar
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))

    logger.info("🚀 Otaplama Bot ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

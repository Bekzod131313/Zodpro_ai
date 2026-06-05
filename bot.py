#!/usr/bin/env python3
import logging
import re
import os
import sqlite3
from datetime import datetime, date
from typing import Optional, Dict, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8918826829:AAGoTikt8LYIfys8mWjixizR0Td_DtaHQac"
ADMIN_IDS = [716768405]
DB_PATH = "otaplama.db"

# ===================== DATABASE =====================

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS guruhlar (
                chat_id INTEGER PRIMARY KEY,
                tur TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS zakazlar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                mijoz TEXT NOT NULL,
                summa REAL NOT NULL,
                obyekt TEXT DEFAULT '-',
                holat TEXT DEFAULT 'faol',
                qoshgan TEXT,
                qoshildi TEXT DEFAULT CURRENT_TIMESTAMP,
                yopildi TEXT
            );
            CREATE TABLE IF NOT EXISTS prixodlar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                postavshik TEXT NOT NULL,
                summa REAL NOT NULL,
                izoh TEXT DEFAULT '-',
                qoshgan TEXT,
                qoshildi TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS kassa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                tur TEXT NOT NULL,
                kim TEXT NOT NULL,
                summa REAL NOT NULL,
                izoh TEXT DEFAULT '-',
                qoshgan TEXT,
                qoshildi TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS balllar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ball INTEGER NOT NULL,
                sabab TEXT DEFAULT '-',
                admin TEXT,
                qoshildi TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

def set_group_type(chat_id, tur):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO guruhlar (chat_id, tur) VALUES (?, ?)", (chat_id, tur))
        conn.commit()

def get_group_type(chat_id):
    with get_conn() as conn:
        row = conn.execute("SELECT tur FROM guruhlar WHERE chat_id = ?", (chat_id,)).fetchone()
        return row["tur"] if row else None

def add_zakaz(chat_id, mijoz, summa, obyekt, qoshgan):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO zakazlar (chat_id, mijoz, summa, obyekt, qoshgan) VALUES (?, ?, ?, ?, ?)",
            (chat_id, mijoz, summa, obyekt, qoshgan)
        )
        conn.commit()
        return cur.lastrowid

def close_zakaz(chat_id, mijoz):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM zakazlar WHERE chat_id=? AND holat='faol' AND LOWER(mijoz) LIKE LOWER(?) ORDER BY qoshildi DESC LIMIT 1",
            (chat_id, f"%{mijoz}%")
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE zakazlar SET holat='yopilgan', yopildi=? WHERE id=?",
                     (datetime.now().isoformat(), row["id"]))
        conn.commit()
        return dict(row)

def get_zakaz_stats(chat_id):
    with get_conn() as conn:
        faol = conn.execute("SELECT COUNT(*) as c FROM zakazlar WHERE chat_id=? AND holat='faol'", (chat_id,)).fetchone()["c"]
        yopilgan = conn.execute("SELECT COUNT(*) as c FROM zakazlar WHERE chat_id=? AND holat='yopilgan'", (chat_id,)).fetchone()["c"]
        summa = conn.execute("SELECT COALESCE(SUM(summa),0) as s FROM zakazlar WHERE chat_id=?", (chat_id,)).fetchone()["s"]
        return {"faol": faol, "yopilgan": yopilgan, "jami_summa": summa}

def get_zakaz_hisobot(chat_id, davr):
    with get_conn() as conn:
        f = "AND DATE(qoshildi)=DATE('now')" if davr=="bugun" else "AND strftime('%Y-%m',qoshildi)=strftime('%Y-%m','now')"
        faollar = conn.execute(f"SELECT * FROM zakazlar WHERE chat_id=? AND holat='faol' {f}", (chat_id,)).fetchall()
        yopilganlar = conn.execute(f"SELECT * FROM zakazlar WHERE chat_id=? AND holat='yopilgan' {f}", (chat_id,)).fetchall()
        return {
            "faol": len(faollar), "yopilgan": len(yopilganlar),
            "jami_summa": sum(r["summa"] for r in faollar)+sum(r["summa"] for r in yopilganlar),
            "yopilgan_summa": sum(r["summa"] for r in yopilganlar),
            "faollar": [dict(r) for r in faollar],
            "yopilganlar": [dict(r) for r in yopilganlar],
        }

def add_prixod(chat_id, postavshik, summa, izoh, qoshgan):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO prixodlar (chat_id, postavshik, summa, izoh, qoshgan) VALUES (?, ?, ?, ?, ?)",
            (chat_id, postavshik, summa, izoh, qoshgan)
        )
        conn.commit()
        return cur.lastrowid

def get_prixod_stats(chat_id):
    with get_conn() as conn:
        bugun = conn.execute("SELECT COALESCE(SUM(summa),0) as s FROM prixodlar WHERE chat_id=? AND DATE(qoshildi)=DATE('now')", (chat_id,)).fetchone()["s"]
        oylik = conn.execute("SELECT COALESCE(SUM(summa),0) as s FROM prixodlar WHERE chat_id=? AND strftime('%Y-%m',qoshildi)=strftime('%Y-%m','now')", (chat_id,)).fetchone()["s"]
        return {"bugun": bugun, "oylik": oylik}

def get_prixod_hisobot(chat_id, davr):
    with get_conn() as conn:
        f = "AND DATE(qoshildi)=DATE('now')" if davr=="bugun" else "AND strftime('%Y-%m',qoshildi)=strftime('%Y-%m','now')"
        rows = conn.execute(f"SELECT * FROM prixodlar WHERE chat_id=? {f}", (chat_id,)).fetchall()
        by_p = {}
        for r in rows:
            p = r["postavshik"]
            if p not in by_p:
                by_p[p] = {"postavshik": p, "summa": 0, "soni": 0}
            by_p[p]["summa"] += r["summa"]
            by_p[p]["soni"] += 1
        return {"soni": len(rows), "summa": sum(r["summa"] for r in rows),
                "postavshiklar": sorted(by_p.values(), key=lambda x: x["summa"], reverse=True)}

def add_kassa(chat_id, tur, kim, summa, izoh, qoshgan):
    with get_conn() as conn:
        conn.execute("INSERT INTO kassa (chat_id, tur, kim, summa, izoh, qoshgan) VALUES (?, ?, ?, ?, ?, ?)",
                     (chat_id, tur, kim, summa, izoh, qoshgan))
        conn.commit()

def get_kassa_balans(chat_id):
    with get_conn() as conn:
        k = conn.execute("SELECT COALESCE(SUM(summa),0) as s FROM kassa WHERE chat_id=? AND tur='kirim'", (chat_id,)).fetchone()["s"]
        c = conn.execute("SELECT COALESCE(SUM(summa),0) as s FROM kassa WHERE chat_id=? AND tur='chiqim'", (chat_id,)).fetchone()["s"]
        return k - c

def get_kassa_hisobot(chat_id, davr):
    with get_conn() as conn:
        f = "AND DATE(qoshildi)=DATE('now')" if davr=="bugun" else "AND strftime('%Y-%m',qoshildi)=strftime('%Y-%m','now')"
        kirimlar = conn.execute(f"SELECT * FROM kassa WHERE chat_id=? AND tur='kirim' {f}", (chat_id,)).fetchall()
        chiqimlar = conn.execute(f"SELECT * FROM kassa WHERE chat_id=? AND tur='chiqim' {f}", (chat_id,)).fetchall()
        k = sum(r["summa"] for r in kirimlar)
        c = sum(r["summa"] for r in chiqimlar)
        return {"kirim": k, "chiqim": c, "balans": k-c,
                "kirimlar": [dict(r) for r in kirimlar],
                "chiqimlar": [dict(r) for r in chiqimlar]}

def add_ball(username, ball, sabab, admin):
    with get_conn() as conn:
        conn.execute("INSERT INTO balllar (username, ball, sabab, admin) VALUES (?, ?, ?, ?)",
                     (username, ball, sabab, admin))
        conn.commit()

def get_worker_balls(username):
    with get_conn() as conn:
        return conn.execute("SELECT COALESCE(SUM(ball),0) as s FROM balllar WHERE LOWER(username)=LOWER(?)", (username,)).fetchone()["s"]

def get_reyting():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT username, SUM(ball) as ball FROM balllar
            WHERE strftime('%Y-%m',qoshildi)=strftime('%Y-%m','now')
            GROUP BY LOWER(username) ORDER BY ball DESC
        """).fetchall()
        return [dict(r) for r in rows]

# ===================== HELPERS =====================

def is_admin(user_id): return user_id in ADMIN_IDS
def fmt(amount): return f"{amount:,.0f} so'm"
def now_str(): return datetime.now().strftime("%d.%m.%Y %H:%M")
def today_str(): return date.today().strftime("%d.%m.%Y")

# ===================== HANDLERS =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Assalomu alaykum! Otaplama Bot!*\n\n"
        "📦 *Zakazlar guruhi:*\n"
        "`#zakaz Ahmad 750000 Chilonzor`\n"
        "`#chiqdi Ahmad`\n\n"
        "💰 *Prixodlar guruhi:*\n"
        "`#prixod Gazprom 5000000`\n\n"
        "🏦 *Kassa guruhi:*\n"
        "`#kirim Alisher 1000000`\n"
        "`#chiqim Yetkazish 50000`\n\n"
        "⭐ *Admin:*\n"
        "`/ball @ism 10 Sabab`\n"
        "`/reyting`\n\n"
        "📊 `/hisobot` `/oylik`\n"
        "⚙️ `/guruh_tur` — guruhni sozlash"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def guruh_tur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Faqat adminlar uchun!")
        return
    chat_id = update.effective_chat.id
    kb = [
        [InlineKeyboardButton("📦 Zakazlar", callback_data=f"st_zakazlar_{chat_id}")],
        [InlineKeyboardButton("💰 Prixodlar", callback_data=f"st_prixodlar_{chat_id}")],
        [InlineKeyboardButton("🏦 Kassa", callback_data=f"st_kassa_{chat_id}")],
    ]
    await update.message.reply_text("Guruh turini tanlang:", reply_markup=InlineKeyboardMarkup(kb))

async def settype_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    parts = q.data.split("_")
    tur = parts[1]
    chat_id = int(parts[2])
    set_group_type(chat_id, tur)
    names = {"zakazlar": "📦 Zakazlar", "prixodlar": "💰 Prixodlar", "kassa": "🏦 Kassa"}
    await q.edit_message_text(f"✅ Guruh: *{names.get(tur, tur)}* deb belgilandi!", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    chat_id = update.effective_chat.id
    user = update.effective_user
    text = update.message.text.strip()
    tur = get_group_type(chat_id)
    if tur == "zakazlar":
        await handle_zakaz(update, text, user, chat_id)
    elif tur == "prixodlar":
        await handle_prixod(update, text, user, chat_id)
    elif tur == "kassa":
        await handle_kassa(update, text, user, chat_id)

async def handle_zakaz(update, text, user, chat_id):
    m = re.match(r'#zakaz\s+(.+?)\s+([\d]+)\s*(.*)', text, re.IGNORECASE)
    if m:
        mijoz, summa, obyekt = m.group(1).strip(), float(m.group(2)), m.group(3).strip() or "-"
        zid = add_zakaz(chat_id, mijoz, summa, obyekt, user.first_name)
        s = get_zakaz_stats(chat_id)
        await update.message.reply_text(
            f"✅ *Zakaz #{zid} qo'shildi!*\n👤 {mijoz}\n💵 {fmt(summa)}\n🏠 {obyekt}\n\n"
            f"🟢 Faol: {s['faol']} | ✅ Yopilgan: {s['yopilgan']}",
            parse_mode="Markdown"
        )
        return
    m = re.match(r'#chiqdi\s+(.+)', text, re.IGNORECASE)
    if m:
        r = close_zakaz(chat_id, m.group(1).strip())
        if r:
            s = get_zakaz_stats(chat_id)
            await update.message.reply_text(
                f"✅ *Zakaz yopildi!*\n👤 {r['mijoz']}\n💵 {fmt(r['summa'])}\n🏠 {r['obyekt']}\n\n"
                f"🟢 Faol: {s['faol']} | ✅ Yopilgan: {s['yopilgan']}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ Faol zakaz topilmadi!")

async def handle_prixod(update, text, user, chat_id):
    m = re.match(r'#prixod\s+(.+?)\s+([\d]+)\s*(.*)', text, re.IGNORECASE)
    if not m:
        return
    postavshik, summa, izoh = m.group(1).strip(), float(m.group(2)), m.group(3).strip() or "-"
    pid = add_prixod(chat_id, postavshik, summa, izoh, user.first_name)
    s = get_prixod_stats(chat_id)
    await update.message.reply_text(
        f"📦 *Prixod #{pid}!*\n🏭 {postavshik}\n💵 {fmt(summa)}\n\n"
        f"📅 Bugun: {fmt(s['bugun'])} | Oy: {fmt(s['oylik'])}",
        parse_mode="Markdown"
    )

async def handle_kassa(update, text, user, chat_id):
    mk = re.match(r'#kirim\s+(.+?)\s+([\d]+)\s*(.*)', text, re.IGNORECASE)
    mc = re.match(r'#chiqim\s+(.+?)\s+([\d]+)\s*(.*)', text, re.IGNORECASE)
    m = mk or mc
    if not m:
        return
    tur = "kirim" if mk else "chiqim"
    kim, summa, izoh = m.group(1).strip(), float(m.group(2)), m.group(3).strip() or "-"
    add_kassa(chat_id, tur, kim, summa, izoh, user.first_name)
    balans = get_kassa_balans(chat_id)
    e = "💚" if tur == "kirim" else "🔴"
    await update.message.reply_text(
        f"{e} *Kassa {tur.upper()}!*\n👤 {kim}\n💵 {fmt(summa)}\n\n💰 Balans: {fmt(balans)}",
        parse_mode="Markdown"
    )

async def ball_ber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Format: `/ball @username 10 Sabab`", parse_mode="Markdown")
        return
    username = args[0].lstrip("@")
    try:
        ball = int(args[1])
    except:
        await update.message.reply_text("Ball raqam bo'lishi kerak!")
        return
    sabab = " ".join(args[2:]) if len(args) > 2 else "-"
    add_ball(username, ball, sabab, update.effective_user.first_name)
    jami = get_worker_balls(username)
    sign = "+" if ball > 0 else ""
    await update.message.reply_text(
        f"⭐ *Ball berildi!*\n👤 @{username}\n🎯 {sign}{ball} ball\n📝 {sabab}\n📊 Jami: {jami}",
        parse_mode="Markdown"
    )

async def hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _hisobot(update, "bugun")

async def oylik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _hisobot(update, "oy")

async def _hisobot(update, davr):
    chat_id = update.effective_chat.id
    tur = get_group_type(chat_id)
    davr_text = "Bugungi" if davr == "bugun" else "Oylik"

    if tur == "zakazlar":
        d = get_zakaz_hisobot(chat_id, davr)
        text = f"📦 *{davr_text} Zakazlar*\n🗓 {today_str()}\n━━━━━━━━━\n"
        text += f"🟢 Faol: {d['faol']} | ✅ Yopilgan: {d['yopilgan']}\n"
        text += f"💰 Jami: {fmt(d['jami_summa'])}\n"
        if d['yopilganlar']:
            text += "\n✅ *Yopilganlar:*\n"
            for z in d['yopilganlar']:
                text += f"  • {z['mijoz']} — {fmt(z['summa'])}\n"
        if d['faollar']:
            text += "\n🟢 *Faollar:*\n"
            for z in d['faollar']:
                text += f"  • {z['mijoz']} — {fmt(z['summa'])}\n"

    elif tur == "prixodlar":
        d = get_prixod_hisobot(chat_id, davr)
        text = f"💰 *{davr_text} Prixodlar*\n🗓 {today_str()}\n━━━━━━━━━\n"
        text += f"📦 Soni: {d['soni']} ta | 💵 {fmt(d['summa'])}\n"
        if d['postavshiklar']:
            text += "\n🏭 *Postavshiklar:*\n"
            for p in d['postavshiklar']:
                text += f"  • {p['postavshik']}: {fmt(p['summa'])}\n"

    elif tur == "kassa":
        d = get_kassa_hisobot(chat_id, davr)
        text = f"🏦 *{davr_text} Kassa*\n🗓 {today_str()}\n━━━━━━━━━\n"
        text += f"💚 Kirim: {fmt(d['kirim'])}\n🔴 Chiqim: {fmt(d['chiqim'])}\n💰 Balans: {fmt(d['balans'])}\n"
        if d['kirimlar']:
            text += "\n💚 *Kirimlar:*\n"
            for k in d['kirimlar']:
                text += f"  • {k['kim']}: {fmt(k['summa'])}\n"
        if d['chiqimlar']:
            text += "\n🔴 *Chiqimlar:*\n"
            for c in d['chiqimlar']:
                text += f"  • {c['kim']}: {fmt(c['summa'])}\n"
    else:
        text = "❗ Guruh sozlanmagan. Admin `/guruh_tur` bossin."

    await update.message.reply_text(text, parse_mode="Markdown")

async def reyting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    workers = get_reyting()
    if not workers:
        await update.message.reply_text("Hali ball berilmagan!")
        return
    medals = ["🥇", "🥈", "🥉"]
    text = f"⭐ *Ishchilar Reytingi*\n🗓 {datetime.now().strftime('%B %Y')}\n━━━━━━━━━\n\n"
    for i, w in enumerate(workers):
        m = medals[i] if i < 3 else f"{i+1}."
        text += f"{m} @{w['username']} — *{w['ball']} ball*\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ===================== MAIN =====================

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("guruh_tur", guruh_tur))
    app.add_handler(CommandHandler("ball", ball_ber))
    app.add_handler(CommandHandler("hisobot", hisobot))
    app.add_handler(CommandHandler("oylik", oylik))
    app.add_handler(CommandHandler("reyting", reyting))
    app.add_handler(CallbackQueryHandler(settype_cb, pattern=r"^st_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

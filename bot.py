#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
import sqlite3
import base64
import requests
import random
import os
from datetime import datetime
from typing import Optional, Tuple
from contextlib import closing

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# ========== الإعدادات الأساسية ==========
BOT_TOKEN = "8625935716:AAEf1kMzndSjdwTNImfm4mqVz121d5CYNBc"
BOT_USERNAME = "ichancy_al_king_bot"
DB_PATH = "ichancy.db"
ADMIN_ID = 8241794104

# مكافآت الإحالات
REFERRAL_BONUS = 5000
REFERRAL_PERCENT = 0.10

USDT_BEP20 = "0x476d8a8e7b05430a38104e2ec94167310b3bb154"
USDT_TRC20 = "TSfr2bJDJL3S63BQRqjiRAWbxnkrR7Pju7"
SYRIATEL_CODES = ["51856802","14969577"]

# رابط الدخول إلى موقع Ichancy
ICHANCY_LOGIN_URL = "https://www.ichancy.com/ar#/login"

# ========== إعدادات API Ichancy ==========
AGENT_API_BASE = "https://agents.ichancy.com/global/api"
AGENT_LOGIN_URL = f"{AGENT_API_BASE}/User/signIn"
AGENT_REGISTER_URL = f"{AGENT_API_BASE}/Player/registerPlayer"
AGENT_PARENT_ID = "2668271"

AGENT_USERNAME = "Abo-taem@agent.nsp"
AGENT_PASSWORD = "Aa123123@"

agent_session = None
agent_cookies = None

# حالات المحادثة
AMOUNT_INPUT = 1
REGISTER_USERNAME = 2
REGISTER_PASSWORD = 3
TRANSACTION_ID_INPUT = 4
WITHDRAW_ADDRESS_INPUT = 5
WITHDRAW_AMOUNT_INPUT = 6
BAN_USER_INPUT = 7
UNBAN_USER_INPUT = 8
ICHANCY_CHARGE_AMOUNT = 9
ICHANCY_WITHDRAW_AMOUNT = 10
ANNOUNCEMENT_TEXT = 11
REPLY_MESSAGE = 12

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================== دوال API ========================
def agent_login():
    global agent_session, agent_cookies
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "sec-ch-ua-platform": "Android",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "dnt": "1",
            "sec-ch-ua-mobile": "?1",
            "origin": "https://agents.ichancy.com",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://agents.ichancy.com/",
            "accept-language": "ar-SY,ar;q=0.9,en-US;q=0.8,en;q=0.7",
            "priority": "u=1, i"
        }
        payload = {"username": AGENT_USERNAME, "password": AGENT_PASSWORD}
        response = requests.post(AGENT_LOGIN_URL, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            agent_cookies = response.cookies.get_dict()
            agent_session = requests.Session()
            agent_session.cookies.update(agent_cookies)
            agent_session.headers.update(headers)
            return True, "تم تسجيل الدخول بنجاح"
        return False, f"فشل تسجيل الدخول (كود {response.status_code})"
    except Exception as e:
        return False, f"استثناء: {str(e)}"

def register_player_via_api(username, password, email):
    global agent_session, agent_cookies
    try:
        if not agent_session:
            success, msg = agent_login()
            if not success:
                return False, msg, None

        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "sec-ch-ua-platform": "Android",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "dnt": "1",
            "sec-ch-ua-mobile": "?1",
            "origin": "https://agents.ichancy.com",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://agents.ichancy.com/dashboard",
            "accept-language": "ar-SY,ar;q=0.9,en-US;q=0.8,en;q=0.7",
            "priority": "u=1, i"
        }
        payload = {
            "player": {
                "email": email,
                "password": password,
                "parentId": AGENT_PARENT_ID,
                "firstname": username,
                "login": username
            }
        }
        if agent_session:
            response = agent_session.post(AGENT_REGISTER_URL, json=payload, timeout=15)
        else:
            cookies = agent_cookies or {}
            response = requests.post(AGENT_REGISTER_URL, json=payload, headers=headers, cookies=cookies, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == True:
                return True, "تم إنشاء الحساب بنجاح", data.get("result")
            return False, data.get("message", "خطأ غير معروف"), None
        elif response.status_code == 401:
            success, msg = agent_login()
            if success:
                return register_player_via_api(username, password, email)
            return False, "انتهت الجلسة ولم نتمكن من تجديدها", None
        return False, f"خطأ في الاتصال (كود {response.status_code})", None
    except Exception as e:
        return False, f"استثناء: {str(e)}", None

# ======================== دوال قاعدة البيانات ========================
def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                referred_by INTEGER,
                balance REAL DEFAULT 0,
                loyalty_points REAL DEFAULT 0,
                total_charges REAL DEFAULT 0,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0,
                seen_referral_ad INTEGER DEFAULT 0
            )
        ''')
        try:
            c.execute("ALTER TABLE users ADD COLUMN total_charges REAL DEFAULT 0")
        except:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN seen_referral_ad INTEGER DEFAULT 0")
        except:
            pass

        c.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS ichancy_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT UNIQUE,
                password TEXT,
                email TEXT,
                ichancy_balance REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        try:
            c.execute("ALTER TABLE ichancy_accounts ADD COLUMN ichancy_balance REAL DEFAULT 0")
        except:
            pass

        c.execute('''
            CREATE TABLE IF NOT EXISTS pending_charges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                method TEXT,
                transaction_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS pending_withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                method TEXT,
                account_details TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS ichancy_charge_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS ichancy_withdraw_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS pending_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                message_text TEXT,
                message_type TEXT,
                file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS referral_announcement (
                id INTEGER PRIMARY KEY CHECK (id=1),
                text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute("INSERT OR IGNORE INTO referral_announcement (id, text) VALUES (1, '🎁 *عرض خاص: نظام الإحالات الجديد!* 🎁\n\n👥 الآن يمكنك كسب المال بدعوة أصدقائك:\n💰 *مكافأة فورية:* 5000 ليرة لكل صديق تسجله!\n💸 *نسبة دائمة:* 10% من كل شحنة يقوم بها صديقك!\n\n🔗 رابط الإحالة الخاص بك متوفر في قسم ''نظام الإحالات''.\n\n🚀 ابدأ الآن واجني الأرباح!')")

        c.execute('''
            CREATE TABLE IF NOT EXISTS referral_system_text (
                id INTEGER PRIMARY KEY CHECK (id=1),
                text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute("INSERT OR IGNORE INTO referral_system_text (id, text) VALUES (1, '👥 *نظام الإحالات المتطور*\n\n🎁 *مكافأة فورية:* 5000 ليرة لكل صديق تسجله!\n💸 *نسبة دائمة:* 10% من كل شحنة يقوم بها صديقك!\n\n🔗 *رابط الإحالة الخاص بك:*\n`{link}`\n\n📊 عدد الإحالات: {total}\n✅ الإحالات النشطة: {active}\n\n📅 التوزيع القادم: {next}\n⏳ {remaining}')")

        c.execute('''
            CREATE TABLE IF NOT EXISTS main_announcement (
                id INTEGER PRIMARY KEY CHECK (id=1),
                text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute("INSERT OR IGNORE INTO main_announcement (id, text) VALUES (1, '🔥 *أهلاً بكم في البوت الأقوى على الإطلاق* 🔥\n\n🎁 *عروض البونصات الترحيبية:*\n• تعبئة زيادة على الرصيد بنسبة *42%* للاعب الجديد!\n\n💸 *عروض التعبئة الدائمة (لمدة شهر):*\n• تعبئة عبر *Sham Cash*: زيادة *20%* دائم\n• تعبئة عبر *Syriatel Cash*: زيادة *20%* دائم\n• تعبئة عبر *USDT*: زيادة *22%* دائم\n\n⏳ *العروض سارية لفترة محدودة، اغتنم الفرصة الآن!*')")

        c.execute('''
            CREATE TABLE IF NOT EXISTS admin_announcement (
                id INTEGER PRIMARY KEY CHECK (id=1),
                text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute("INSERT OR IGNORE INTO admin_announcement (id, text) VALUES (1, '')")

        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                  ("next_payout", "2026-03-09 15:29:00"))
        conn.commit()

def get_user(user_id: int, username: str = None, first_name: str = None, referred_by: int = None):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if row:
            return {
                "user_id": row[0], "username": row[1], "first_name": row[2],
                "referred_by": row[3], "balance": row[4], "loyalty_points": row[5],
                "total_charges": row[6], "registered_at": row[7], "is_active": row[8],
                "is_admin": row[9], "banned": row[10], "seen_referral_ad": row[11],
            }
        else:
            c.execute('''
                INSERT INTO users (user_id, username, first_name, referred_by, total_charges, seen_referral_ad)
                VALUES (?, ?, ?, ?, 0, 0)
            ''', (user_id, username, first_name, referred_by))
            conn.commit()
            if referred_by:
                c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (REFERRAL_BONUS, referred_by))
                conn.commit()
            return {
                "user_id": user_id, "username": username, "first_name": first_name,
                "referred_by": referred_by, "balance": 0, "loyalty_points": 0,
                "total_charges": 0, "registered_at": datetime.now(), "is_active": False,
                "is_admin": 1 if user_id == ADMIN_ID else 0, "banned": 0, "seen_referral_ad": 0,
            }

def update_balance(user_id: int, amount: float, add: bool = True):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        if add:
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        else:
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        conn.commit()

def get_referrals_count(user_id: int) -> Tuple[int, int]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,))
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE referred_by = ? AND is_active = 1", (user_id,))
        active = c.fetchone()[0]
        return total, active

def get_next_payout() -> str:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = 'next_payout'")
        row = c.fetchone()
        return row[0] if row else "2026-03-09 15:29:00"

def decode_referrer(start_param: str) -> Optional[int]:
    try:
        missing_padding = len(start_param) % 4
        if missing_padding:
            start_param += '=' * (4 - missing_padding)
        decoded_bytes = base64.b64decode(start_param)
        return int(decoded_bytes.decode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to decode referrer: {e}")
        return None

def get_ichancy_account(telegram_id: int) -> Optional[dict]:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM ichancy_accounts WHERE telegram_id = ?", (telegram_id,))
        row = c.fetchone()
        if row:
            return {
                "id": row[0], "telegram_id": row[1], "username": row[2],
                "password": row[3], "email": row[4], "ichancy_balance": row[5],
                "created_at": row[6],
            }
        return None

def is_ichancy_username_taken(username: str) -> bool:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM ichancy_accounts WHERE username = ?", (username,))
        return c.fetchone() is not None

def create_ichancy_account(telegram_id: int, username: str, password: str, email: str) -> bool:
    try:
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO ichancy_accounts (telegram_id, username, password, email)
                VALUES (?, ?, ?, ?)
            ''', (telegram_id, username, password, email))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

def delete_ichancy_account(telegram_id: int) -> bool:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM ichancy_accounts WHERE telegram_id = ?", (telegram_id,))
        conn.commit()
        return c.rowcount > 0

def set_referral_announcement(text: str):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE referral_announcement SET text = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1", (text,))
        conn.commit()

def get_referral_announcement() -> str:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT text FROM referral_announcement WHERE id = 1")
        row = c.fetchone()
        return row[0] if row else ""

def clear_referral_announcement():
    set_referral_announcement('')

def set_referral_system_text(text: str):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE referral_system_text SET text = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1", (text,))
        conn.commit()

def get_referral_system_text() -> str:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT text FROM referral_system_text WHERE id = 1")
        row = c.fetchone()
        return row[0] if row else ""

def clear_referral_system_text():
    set_referral_system_text('')

def set_main_announcement(text: str):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE main_announcement SET text = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1", (text,))
        conn.commit()

def get_main_announcement() -> str:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT text FROM main_announcement WHERE id = 1")
        row = c.fetchone()
        return row[0] if row else ""

def clear_main_announcement():
    set_main_announcement('')

def set_admin_announcement(text: str):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE admin_announcement SET text = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1", (text,))
        conn.commit()

def get_admin_announcement() -> str:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT text FROM admin_announcement WHERE id = 1")
        row = c.fetchone()
        return row[0] if row else ""

def clear_admin_announcement():
    set_admin_announcement('')

def get_pending_counts():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        counts = {}
        c.execute("SELECT COUNT(*) FROM pending_charges WHERE status='pending'")
        counts['charges'] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM pending_withdrawals WHERE status='pending'")
        counts['withdrawals'] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM ichancy_charge_requests WHERE status='pending'")
        counts['ichancy_charge'] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM ichancy_withdraw_requests WHERE status='pending'")
        counts['ichancy_withdraw'] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM pending_messages WHERE status='pending'")
        counts['messages'] = c.fetchone()[0]
        return counts

def format_button(text, count):
    return f"{text} 🔴 [{count}]" if count > 0 else text

def format_admin_panel_keyboard():
    counts = get_pending_counts()
    keyboard = [
        [InlineKeyboardButton(format_button("📋 طلبات الشحن المعلقة", counts['charges']), callback_data="admin_pending_charges")],
        [InlineKeyboardButton(format_button("📋 طلبات السحب المعلقة", counts['withdrawals']), callback_data="admin_pending_withdrawals")],
        [InlineKeyboardButton(format_button("📋 طلبات شحن Ichancy", counts['ichancy_charge']), callback_data="admin_ichancy_charge")],
        [InlineKeyboardButton(format_button("📋 طلبات سحب Ichancy", counts['ichancy_withdraw']), callback_data="admin_ichancy_withdraw")],
        [InlineKeyboardButton(format_button("📨 رسائل للنشر", counts['messages']), callback_data="admin_pending_messages")],
        [InlineKeyboardButton("🔨 حظر مستخدم", callback_data="admin_ban_user"),
         InlineKeyboardButton("🔓 رفع حظر عن مستخدم", callback_data="admin_unban_user")],
        [InlineKeyboardButton("🚫 قائمة المحظورين", callback_data="admin_banned_list"),
         InlineKeyboardButton("📊 إحصائيات البوت", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 إدارة الإعلانات", callback_data="admin_announcement_menu")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def format_remaining_time(target_date_str: str) -> str:
    try:
        target = datetime.strptime(target_date_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if target <= now:
            return "انتهى التوزيع"
        delta = target - now
        return f"{delta.days} يوم {delta.seconds//3600} ساعة {(delta.seconds%3600)//60} دقيقة"
    except:
        return "غير محدد"

def get_main_menu_keyboard():
    keyboard = [
    [InlineKeyboardButton("❤️ إيداع رصيد", callback_data="charge"),
     InlineKeyboardButton("💸 سحب رصيد", callback_data="withdraw")],
    [InlineKeyboardButton("👥 نظام الإحالات", callback_data="referral_system")],
    [InlineKeyboardButton("🎁 اهداء رصيد", callback_data="gift"),
     InlineKeyboardButton("🎟️ كود هدية", callback_data="gift_code")],
    [InlineKeyboardButton("📩 رسالة للادمن", callback_data="message_admin")],
    [InlineKeyboardButton("📚 الشروحات", callback_data="tutorials")],
    [InlineKeyboardButton("💰 رصيدي /balance", callback_data="balance")],
    [InlineKeyboardButton("🎁 البونصات والعروض", callback_data="bonuses")],
    [InlineKeyboardButton("🆕 إنشاء حساب Ichancy", callback_data="register_ichancy")],
    [InlineKeyboardButton("📋 بيانات حساب Ichancy", callback_data="my_ichancy_account")],
    [InlineKeyboardButton("📋 حساب Ichancy", callback_data="ichancy_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]])

def get_payment_methods_keyboard():
    keyboard = [
        
        [InlineKeyboardButton("Syriatel Cash ✅", callback_data="pay_syriatel")],
        [InlineKeyboardButton("عملات رقمية USDT", callback_data="pay_usdt")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_withdrawal_methods_keyboard():
    keyboard = [
    
        [InlineKeyboardButton("Syriatel Cash 📱", callback_data="withdraw_syriatel")],
        [InlineKeyboardButton("USDT (TRC20) 💎", callback_data="withdraw_usdt_trc20")],
        [InlineKeyboardButton("USDT (BEP20) 💎", callback_data="withdraw_usdt_bep20")],
        
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def is_admin(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row is not None and row[0] == 1

def is_banned(user_id: int) -> bool:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row is not None and row[0] == 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        await update.message.reply_text("❌ حسابك محظور. لا يمكنك استخدام البوت.")
        return

    args = context.args
    referrer_id = None
    if args:
        decoded = decode_referrer(args[0])
        if decoded:
            referrer_id = decoded

    user_data = get_user(user.id, user.username, user.first_name, referred_by=referrer_id)

    if user_data.get("seen_referral_ad", 0) == 0:
        referral_ad = get_referral_announcement()
        if referral_ad:
            await update.message.reply_text(referral_ad, parse_mode='Markdown')
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET seen_referral_ad = 1 WHERE user_id = ?", (user.id,))
            conn.commit()

    main_announcement = get_main_announcement()
    if main_announcement:
        await update.message.reply_text(main_announcement, parse_mode='Markdown')

    admin_announcement = get_admin_announcement()
    if admin_announcement:
        await update.message.reply_text(f"📢 *إعلان من الإدارة:*\n{admin_announcement}", parse_mode='Markdown')

    await update.message.reply_text(
        "أهلاً بك في بوت Ichancy-AI KiNG.Bot 🤖\n\nيمكنك استخدام الأزرار أدناه للتنقل بين الخيارات.",
        reply_markup=get_main_menu_keyboard()
    )

    if referrer_id:
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"🎉 تم تسجيل مستخدم جديد عن طريق رابطك! تم إضافة {REFERRAL_BONUS} ليرة إلى رصيدك.",
                parse_mode='Markdown'
            )
        except:
            pass

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        await update.message.reply_text("❌ حسابك محظور.")
        return
    user_data = get_user(user.id, user.username, user.first_name)
    text = (
        f"💰 رصيدك الحالي هو: {user_data['balance']}\n"
        f"🆔 معرفك الخاص: {user.id}\n"
        f"⭐ نقاط الولاء: {user_data['loyalty_points']:.2f}\n\n"
        "استبدال نقاط الولاء 🔥"
    )
    await update.message.reply_text(text, reply_markup=get_back_keyboard())

async def offers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        await update.message.reply_text("❌ حسابك محظور.")
        return
    offers_text = (
        "🔥 *أهلاً بكم في البوت الأقوى على الإطلاق* 🔥\n\n"
        
    )
    await update.message.reply_text(offers_text, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        await update.message.reply_text("❌ حسابك محظور.")
        return ConversationHandler.END
    await update.message.reply_text("تم الإلغاء.", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if is_banned(user_id):
        await query.edit_message_text("❌ حسابك محظور.")
        return ConversationHandler.END

    account = get_ichancy_account(user_id)
    if account:
        await query.edit_message_text(
            f"لديك حساب بالفعل! اسم المستخدم: {account['username']}",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "مرحباً بك في إنشاء حساب Ichancy!\n"
        "الرجاء إرسال اسم المستخدم الذي ترغب به:",
        reply_markup=get_back_keyboard()
    )
    return REGISTER_USERNAME

async def register_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await update.message.reply_text("❌ حسابك محظور.")
        return ConversationHandler.END
    username = update.message.text.strip()
    if len(username) < 3:
        await update.message.reply_text("اسم المستخدم قصير جداً (3 أحرف على الأقل). حاول مرة أخرى:")
        return REGISTER_USERNAME

    if is_ichancy_username_taken(username):
        await update.message.reply_text("اسم المستخدم هذا محجوب محلياً. الرجاء اختيار اسم آخر:")
        return REGISTER_USERNAME

    context.user_data["reg_username"] = username
    await update.message.reply_text("الآن أرسل كلمة المرور (4 أحرف على الأقل):")
    return REGISTER_PASSWORD

async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await update.message.reply_text("❌ حسابك محظور.")
        return ConversationHandler.END
    password = update.message.text.strip()
    if len(password) < 4:
        await update.message.reply_text("كلمة المرور قصيرة جداً (4 أحرف على الأقل). حاول مرة أخرى:")
        return REGISTER_PASSWORD

    username = context.user_data.get("reg_username")
    if not username:
        await update.message.reply_text("حدث خطأ، يرجى البدء من جديد.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    random_number = random.randint(10000, 99999)
    email = f"{username}{random_number}@gmail.com"

    await update.message.reply_text("⏳ جاري إنشاء حسابك على موقع Ichancy...")

    success, message, player_id = register_player_via_api(username, password, email)

    if success:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 *لاعب جديد سجل في Ichancy!*\n\n👤 المستخدم: {user_id}\n📝 اسم المستخدم: {username}\n📧 البريد: {email}",
            parse_mode='Markdown',
            disable_notification=False
        )
        
        if create_ichancy_account(user_id, username, password, email):
            await update.message.reply_text(
                f"🎉 *تهانياً! تم إنشاء حسابك على Ichancy بنجاح.*\n\n"
                f"👤 *اسم المستخدم:* `{username}`\n"
                f"🔑 *كلمة المرور:* `{password}`\n"
                f"📧 *البريد الإلكتروني:* `{email}`\n\n"
                "يمكنك الآن استخدام هذه البيانات لتسجيل الدخول إلى ألعاب Ichancy.",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                f"⚠️ *تم إنشاء الحساب في الموقع، ولكن حدث خطأ في الحفظ المحلي.*\n\n"
                f"👤 *اسم المستخدم:* `{username}`\n"
                f"🔑 *كلمة المرور:* `{password}`\n"
                f"📧 *البريد الإلكتروني:* `{email}`\n\n"
                "احتفظ بهذه البيانات لتسجيل الدخول.",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
    else:
        await update.message.reply_text(
            f"❌ فشل إنشاء الحساب:\n{message}\n\n"
            "الرجاء المحاولة لاحقاً أو استخدام اسم مستخدم آخر.",
            reply_markup=get_main_menu_keyboard()
        )

    context.user_data.clear()
    return ConversationHandler.END

async def amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await update.message.reply_text("❌ حسابك محظور.")
        return ConversationHandler.END
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("الرجاء إدخال رقم صحيح موجب.", reply_markup=get_back_keyboard())
        return AMOUNT_INPUT

    action = context.user_data.get("action", "charge")
    method = context.user_data.get("payment_method", "unknown")

    if action == "charge":
        context.user_data["charge_amount"] = amount
        context.user_data["charge_method"] = method
        await update.message.reply_text(
            "📝 الرجاء إرسال رقم عملية التحويل (أو أي إثبات) بعد إتمام الدفع:",
            reply_markup=get_back_keyboard()
        )
        return TRANSACTION_ID_INPUT
    return ConversationHandler.END

async def transaction_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await update.message.reply_text("❌ حسابك محظور.")
        return ConversationHandler.END
    transaction_id = update.message.text.strip()
    amount = context.user_data.get("charge_amount")
    method = context.user_data.get("charge_method")

    if not amount or not method:
        await update.message.reply_text("حدث خطأ، يرجى البدء من جديد.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO pending_charges (user_id, amount, method, transaction_id)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, method, transaction_id))
        conn.commit()
        charge_id = c.lastrowid

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 *طلب شحن جديد!*\n\n🆔 رقم الطلب: {charge_id}\n👤 المستخدم: {user_id}\n💰 المبلغ: {amount}\n💳 الطريقة: {method}\n🔢 رقم العملية: {transaction_id}",
        parse_mode='Markdown',
        disable_notification=False
    )

    await update.message.reply_text(
        f"✅ تم إرسال طلب الشحن رقم {charge_id}.\n"
        "سيتم مراجعته من قبل الإدارة وإضافة الرصيد بعد التأكد من الدفع.\n"
        "شكراً لك.",
        reply_markup=get_main_menu_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def withdraw_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.replace("withdraw_", "")
    context.user_data["withdraw_method"] = method

        if method == "syriatel":
        await query.edit_message_text("🔹 *Syriatel Cash*\n\nأرسل الآن رقم محفظتك في سيريتيل كاش:", parse_mode='Markdown', reply_markup=get_back_keyboard())
    elif method == "usdt_trc20":
        await query.edit_message_text("🔹 *USDT - شبكة TRC20*\n\nأرسل الآن عنوان محفظتك (USDT):", parse_mode='Markdown', reply_markup=get_back_keyboard())
    elif method == "usdt_bep20":
        await query.edit_message_text("🔹 *USDT - شبكة BEP20*\n\nأرسل الآن عنوان محفظتك (USDT):", parse_mode='Markdown', reply_markup=get_back_keyboard())
    elif method == "btc":
        await query.edit_message_text("🔹 *BTC (Bitcoin)*\n\nأرسل الآن عنوان محفظتك (BTC):", parse_mode='Markdown', reply_markup=get_back_keyboard())
    else:
        await query.edit_message_text("❌ طريقة سحب غير معروفة.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    return WITHDRAW_ADDRESS_INPUT

async def withdraw_address_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await update.message.reply_text("❌ حسابك محظور.")
        return ConversationHandler.END

    address = update.message.text.strip()
    if not address:
        await update.message.reply_text("❌ العنوان لا يمكن أن يكون فارغاً.")
        return WITHDRAW_ADDRESS_INPUT

    context.user_data["withdraw_address"] = address
    await update.message.reply_text("💰 أرسل المبلغ الذي تريد سحبه:", reply_markup=get_back_keyboard())
    return WITHDRAW_AMOUNT_INPUT

async def withdraw_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await update.message.reply_text("❌ حسابك محظور.")
        return ConversationHandler.END

    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح موجب.", reply_markup=get_back_keyboard())
        return WITHDRAW_AMOUNT_INPUT

    method = context.user_data.get("withdraw_method", "unknown")
    address = context.user_data.get("withdraw_address")

    user_data = get_user(user_id)
    if user_data['balance'] < amount:
        await update.message.reply_text("❌ رصيدك غير كافٍ.", reply_markup=get_main_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO pending_withdrawals (user_id, amount, method, account_details)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, method, address))
        conn.commit()
        withdraw_id = c.lastrowid

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 *طلب سحب جديد!*\n\n🆔 رقم الطلب: {withdraw_id}\n👤 المستخدم: {user_id}\n💰 المبلغ: {amount}\n💳 الطريقة: {method}\n📋 عنوان المحفظة: {address}",
        parse_mode='Markdown',
        disable_notification=False
    )

    await update.message.reply_text(
        f"✅ تم إرسال طلب السحب رقم {withdraw_id}.\n"
        "سيتم مراجعته من قبل الإدارة وتحويل المبلغ بعد التأكد.\n"
        "شكراً لك.",
        reply_markup=get_main_menu_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def ichancy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if is_banned(user_id):
        await query.edit_message_text("❌ حسابك محظور.")
        return ConversationHandler.END
    
    account = get_ichancy_account(user_id)
    if not account:
        keyboard = [[InlineKeyboardButton("🆕 إنشاء حساب", callback_data="register_ichancy")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]
        await query.edit_message_text(
            "❌ ليس لديك حساب Ichancy بعد.\nالرجاء إنشاء حساب أولاً.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    text = (
        f"📋 *حساب Ichancy الخاص بك*\n\n"
        f"👤 اسم المستخدم: `{account['username']}`\n"
        f"🔑 كلمة المرور: `{account['password']}`\n"
        f"📧 البريد الإلكتروني: `{account['email']}`\n\n"
        "اختر أحد الخيارات:"
    )
    keyboard = [
        [InlineKeyboardButton("🔄 شحن الحساب", callback_data="ichancy_charge"),
         InlineKeyboardButton("⬇️ سحب من الحساب", callback_data="ichancy_withdraw")],
        [InlineKeyboardButton("🗑️ حذف الحساب", callback_data="ichancy_delete")],
        [InlineKeyboardButton("🔗 الدخول إلى موقع Ichancy", url=ICHANCY_LOGIN_URL)],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]
    ]
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def ichancy_charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if is_banned(user_id):
        await query.edit_message_text("❌ حسابك محظور.")
        return ConversationHandler.END
    
    user_data = get_user(user_id)
    await query.edit_message_text(
        f"💰 رصيدك الحالي في البوت: {user_data['balance']}\n\n"
        "الرجاء إدخال المبلغ الذي تريد شحنه إلى حسابك في موقع Ichancy:",
        reply_markup=get_back_keyboard()
    )
    return ICHANCY_CHARGE_AMOUNT

async def ichancy_charge_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await update.message.reply_text("❌ حسابك محظور.")
        return ConversationHandler.END
    
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("الرجاء إدخال رقم صحيح موجب.", reply_markup=get_back_keyboard())
        return ICHANCY_CHARGE_AMOUNT
    
    user_data = get_user(user_id)
    if user_data['balance'] < amount:
        await update.message.reply_text("❌ رصيدك غير كافٍ.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END
    
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO ichancy_charge_requests (user_id, amount)
            VALUES (?, ?)
        ''', (user_id, amount))
        conn.commit()
        request_id = c.lastrowid
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 *طلب شحن حساب Ichancy جديد!*\n\n🆔 رقم الطلب: {request_id}\n👤 المستخدم: {user_id}\n💰 المبلغ: {amount}",
        parse_mode='Markdown',
        disable_notification=False
    )
    
    await update.message.reply_text(
        f"✅ تم إرسال طلب شحن حساب Ichancy رقم {request_id}.\n"
        "سيتم مراجعته من قبل الإدارة وتحديث رصيدك بعد التأكد.\n"
        "شكراً لك.",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END

async def ichancy_withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if is_banned(user_id):
        await query.edit_message_text("❌ حسابك محظور.")
        return ConversationHandler.END
    
    await query.edit_message_text(
        "💰 أدخل المبلغ الذي تريد سحبه من حساب Ichancy إلى رصيد البوت:",
        reply_markup=get_back_keyboard()
    )
    return ICHANCY_WITHDRAW_AMOUNT

async def ichancy_withdraw_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await update.message.reply_text("❌ حسابك محظور.")
        return ConversationHandler.END
    
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("الرجاء إدخال رقم صحيح موجب.", reply_markup=get_back_keyboard())
        return ICHANCY_WITHDRAW_AMOUNT
    
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO ichancy_withdraw_requests (user_id, amount)
            VALUES (?, ?)
        ''', (user_id, amount))
        conn.commit()
        request_id = c.lastrowid
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 *طلب سحب من حساب Ichancy جديد!*\n\n🆔 رقم الطلب: {request_id}\n👤 المستخدم: {user_id}\n💰 المبلغ: {amount}",
        parse_mode='Markdown',
        disable_notification=False
    )
    
    await update.message.reply_text(
        f"✅ تم إرسال طلب سحب من حساب Ichancy رقم {request_id}.\n"
        "سيتم مراجعته من قبل الإدارة وإضافة الرصيد بعد التأكد.\n"
        "شكراً لك.",
        reply_markup=get_main_menu_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def ichancy_delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if is_banned(user_id):
        await query.edit_message_text("❌ حسابك محظور.")
        return
    
    account = get_ichancy_account(user_id)
    if not account:
        await query.edit_message_text("❌ لا يوجد حساب لحذفه.")
        return
    
    keyboard = [
        [InlineKeyboardButton("✅ نعم، احذف", callback_data="ichancy_delete_confirm"),
         InlineKeyboardButton("❌ لا، تراجع", callback_data="ichancy_menu")]
    ]
    await query.edit_message_text(
        f"⚠️ *تأكيد حذف الحساب*\n\nاسم المستخدم: `{account['username']}`\n\n"
        "سيتم حذف بيانات الحساب من البوت فقط. حسابك في موقع Ichancy سيظل موجوداً.\n"
        "هل أنت متأكد؟",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def ichancy_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if is_banned(user_id):
        await query.edit_message_text("❌ حسابك محظور.")
        return
    
    if delete_ichancy_account(user_id):
        await query.edit_message_text("✅ تم حذف حساب Ichancy من البوت.\nيمكنك إنشاء حساب جديد في أي وقت.", reply_markup=get_main_menu_keyboard())
    else:
        await query.edit_message_text("❌ حدث خطأ أثناء الحذف.", reply_markup=get_main_menu_keyboard())

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        return
    if update.message.text and update.message.text.startswith('/'):
        return

    message_text = update.message.text if update.message.text else None
    message_type = "text"
    file_id = None
    
    if update.message.photo:
        message_type = "photo"
        file_id = update.message.photo[-1].file_id
    elif update.message.video:
        message_type = "video"
        file_id = update.message.video.file_id
    elif update.message.document:
        message_type = "document"
        file_id = update.message.document.file_id
    elif update.message.audio:
        message_type = "audio"
        file_id = update.message.audio.file_id
    elif update.message.voice:
        message_type = "voice"
        file_id = update.message.voice.file_id
    elif update.message.sticker:
        message_type = "sticker"
        file_id = update.message.sticker.file_id

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO pending_messages (user_id, username, message_text, message_type, file_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (user.id, user.username or "لا يوجد", message_text, message_type, file_id))
        conn.commit()
        msg_id = c.lastrowid

    caption = f"📨 *رسالة جديدة من المستخدم*\n\n🆔 المعرف: {user.id}\n👤 الاسم: {user.first_name}\n📝 النوع: {message_type}"
    if message_text:
        caption += f"\n\n📄 النص: {message_text}"

    keyboard = [[
        InlineKeyboardButton("✅ نشر للجميع", callback_data=f"publish_msg_{msg_id}"),
        InlineKeyboardButton("❌ تجاهل", callback_data=f"ignore_msg_{msg_id}"),
        InlineKeyboardButton("📝 رد خاص", callback_data=f"reply_msg_{msg_id}")
    ]]
    
    if message_type == "text":
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=caption,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        if message_type == "photo":
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=file_id,
                caption=caption,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif message_type == "video":
            await context.bot.send_video(
                chat_id=ADMIN_ID,
                video=file_id,
                caption=caption,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif message_type == "document":
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=file_id,
                caption=caption,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif message_type == "audio":
            await context.bot.send_audio(
                chat_id=ADMIN_ID,
                audio=file_id,
                caption=caption,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif message_type == "voice":
            await context.bot.send_voice(
                chat_id=ADMIN_ID,
                voice=file_id,
                caption=caption,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif message_type == "sticker":
            await context.bot.send_sticker(
                chat_id=ADMIN_ID,
                sticker=file_id,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=caption,
                parse_mode='Markdown'
            )

    await update.message.reply_text("✅ تم إرسال رسالتك إلى الإدارة. سنقوم بالرد قريباً إن شاء الله.")

async def reply_to_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return ConversationHandler.END
    
    data = query.data
    msg_id = int(data.split('_')[-1])
    
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, username FROM pending_messages WHERE id = ?", (msg_id,))
        row = c.fetchone()
        if not row:
            await query.edit_message_text("❌ لم يتم العثور على الرسالة.")
            return ConversationHandler.END
        
        target_user_id, target_username = row
    
    context.user_data["reply_target"] = target_user_id
    context.user_data["reply_msg_id"] = msg_id
    
    await query.edit_message_text(
        f"✏️ أرسل الآن الرد الذي تريد إرساله إلى المستخدم {target_user_id}:\n"
        "(سيظهر الرد باسم البوت ولن يراه أحد آخر)",
        reply_markup=get_back_keyboard()
    )
    return REPLY_MESSAGE

async def reply_to_user_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ غير مصرح.")
        return ConversationHandler.END
    
    target_user_id = context.user_data.get("reply_target")
    msg_id = context.user_data.get("reply_msg_id")
    reply_text = update.message.text.strip()
    
    if not target_user_id or not reply_text:
        await update.message.reply_text("❌ حدث خطأ، يرجى المحاولة مرة أخرى.")
        return ConversationHandler.END
    
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"📨 *رد من الإدارة:*\n\n{reply_text}",
            parse_mode='Markdown'
        )
        
        with closing(sqlite3.connect(DB_PATH)) as conn:
            c = conn.cursor()
            c.execute("UPDATE pending_messages SET status = 'replied' WHERE id = ?", (msg_id,))
            conn.commit()
        
        await update.message.reply_text(
            "✅ تم إرسال الرد إلى المستخدم بنجاح.",
            reply_markup=format_admin_panel_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ فشل إرسال الرد: {str(e)}",
            reply_markup=format_admin_panel_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def admin_announcement_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    keyboard = [
        [InlineKeyboardButton("✏️ تعديل إعلان الإحالات الترحيبي", callback_data="admin_referral_announcement_write")],
        [InlineKeyboardButton("📋 عرض إعلان الإحالات الترحيبي", callback_data="admin_referral_announcement_show")],
        [InlineKeyboardButton("🗑️ مسح إعلان الإحالات الترحيبي", callback_data="admin_referral_announcement_clear")],
        [InlineKeyboardButton("✏️ تعديل نص نظام الإحالات", callback_data="admin_referral_system_write")],
        [InlineKeyboardButton("📋 عرض نص نظام الإحالات", callback_data="admin_referral_system_show")],
        [InlineKeyboardButton("🗑️ مسح نص نظام الإحالات", callback_data="admin_referral_system_clear")],
        [InlineKeyboardButton("✏️ تعديل الإعلان الرئيسي (البونصات)", callback_data="admin_main_announcement_write")],
        [InlineKeyboardButton("📋 عرض الإعلان الرئيسي", callback_data="admin_main_announcement_show")],
        [InlineKeyboardButton("🗑️ مسح الإعلان الرئيسي", callback_data="admin_main_announcement_clear")],
        [InlineKeyboardButton("✏️ كتابة إعلان ثابت (للمشرف)", callback_data="admin_announcement_write")],
        [InlineKeyboardButton("📋 عرض الإعلان الثابت", callback_data="admin_announcement_show")],
        [InlineKeyboardButton("🗑️ مسح الإعلان الثابت", callback_data="admin_announcement_clear")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
    ]
    await query.edit_message_text("📢 *إدارة الإعلانات*\n\nاختر ما تريد:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_referral_announcement_write(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return ConversationHandler.END
    await query.edit_message_text("✏️ أرسل الآن نص إعلان الإحالات الترحيبي:", reply_markup=get_back_keyboard())
    return ANNOUNCEMENT_TEXT

async def admin_referral_announcement_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ غير مصرح.")
        return ConversationHandler.END
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ الإعلان لا يمكن أن يكون فارغاً.")
        return ANNOUNCEMENT_TEXT
    set_referral_announcement(text)
    await update.message.reply_text("✅ تم حفظ إعلان الإحالات الترحيبي بنجاح.", reply_markup=format_admin_panel_keyboard())
    return ConversationHandler.END

async def admin_referral_announcement_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return
    announcement = get_referral_announcement()
    text = f"📢 *إعلان الإحالات الترحيبي الحالي:*\n\n{announcement}" if announcement else "❌ لا يوجد إعلان."
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_announcement_menu")]]
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_referral_announcement_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return
    clear_referral_announcement()
    await query.edit_message_text("✅ تم مسح إعلان الإحالات الترحيبي.", reply_markup=format_admin_panel_keyboard())

async def admin_referral_system_write(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return ConversationHandler.END
    await query.edit_message_text("✏️ أرسل الآن نص نظام الإحالات (استخدم {link}, {total}, {active}, {next}, {remaining} كمتغيرات):", reply_markup=get_back_keyboard())
    return ANNOUNCEMENT_TEXT

async def admin_referral_system_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ غير مصرح.")
        return ConversationHandler.END
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ النص لا يمكن أن يكون فارغاً.")
        return ANNOUNCEMENT_TEXT
    set_referral_system_text(text)
    await update.message.reply_text("✅ تم حفظ نص نظام الإحالات بنجاح.", reply_markup=format_admin_panel_keyboard())
    return ConversationHandler.END

async def admin_referral_system_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return
    text = get_referral_system_text()
    display = f"📢 *نص نظام الإحالات الحالي:*\n\n{text}" if text else "❌ لا يوجد نص."
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_announcement_menu")]]
    await query.edit_message_text(display, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_referral_system_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return
    clear_referral_system_text()
    await query.edit_message_text("✅ تم مسح نص نظام الإحالات.", reply_markup=format_admin_panel_keyboard())

async def admin_main_announcement_write(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return ConversationHandler.END
    await query.edit_message_text("✏️ أرسل الآن نص الإعلان الرئيسي (البونصات والعروض):", reply_markup=get_back_keyboard())
    return ANNOUNCEMENT_TEXT

async def admin_main_announcement_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ غير مصرح.")
        return ConversationHandler.END
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ الإعلان لا يمكن أن يكون فارغاً.")
        return ANNOUNCEMENT_TEXT
    set_main_announcement(text)
    await update.message.reply_text("✅ تم حفظ الإعلان الرئيسي بنجاح.", reply_markup=format_admin_panel_keyboard())
    return ConversationHandler.END

async def admin_main_announcement_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return
    announcement = get_main_announcement()
    text = f"📢 *الإعلان الرئيسي الحالي:*\n\n{announcement}" if announcement else "❌ لا يوجد إعلان رئيسي."
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_announcement_menu")]]
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_main_announcement_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return
    clear_main_announcement()
    await query.edit_message_text("✅ تم مسح الإعلان الرئيسي.", reply_markup=format_admin_panel_keyboard())

async def admin_announcement_write(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return ConversationHandler.END
    await query.edit_message_text("✏️ أرسل الآن نص الإعلان الثابت (للمشرف):", reply_markup=get_back_keyboard())
    return ANNOUNCEMENT_TEXT

async def admin_announcement_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ غير مصرح.")
        return ConversationHandler.END
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ الإعلان لا يمكن أن يكون فارغاً.")
        return ANNOUNCEMENT_TEXT
    set_admin_announcement(text)
    await update.message.reply_text("✅ تم حفظ الإعلان الثابت بنجاح.", reply_markup=format_admin_panel_keyboard())
    return ConversationHandler.END

async def admin_announcement_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return
    announcement = get_admin_announcement()
    text = f"📢 *الإعلان الثابت الحالي:*\n\n{announcement}" if announcement else "❌ لا يوجد إعلان ثابت."
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_announcement_menu")]]
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_announcement_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return
    clear_admin_announcement()
    await query.edit_message_text("✅ تم مسح الإعلان الثابت.", reply_markup=format_admin_panel_keyboard())

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
        message_func = query.edit_message_text
    else:
        user_id = update.effective_user.id
        message_func = update.message.reply_text

    if not is_admin(user_id):
        await message_func("❌ هذه اللوحة خاصة بالمشرفين فقط.")
        return

    await message_func("🔧 لوحة تحكم المشرف:", reply_markup=format_admin_panel_keyboard())

async def admin_pending_charges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, amount, method, transaction_id, created_at FROM pending_charges WHERE status='pending' ORDER BY created_at DESC")
        rows = c.fetchall()

    if not rows:
        await query.edit_message_text("لا توجد طلبات شحن معلقة.", reply_markup=format_admin_panel_keyboard())
        return

    await query.edit_message_text("جاري عرض الطلبات...")
    for row in rows:
        charge_id, uid, amount, method, tx_id, created = row
        text = f"🆔 طلب شحن رقم: {charge_id}\n👤 المستخدم: {uid}\n💰 المبلغ: {amount}\n💳 الطريقة: {method}\n🔢 رقم العملية: {tx_id}\n📅 التاريخ: {created}"
        keyboard = [[InlineKeyboardButton("✅ موافقة", callback_data=f"confirm_charge_{charge_id}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_charge_{charge_id}")]]
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))

    await context.bot.send_message(chat_id=user_id, text="🔙 للعودة إلى لوحة التحكم", reply_markup=format_admin_panel_keyboard())

async def admin_pending_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, amount, method, account_details, created_at FROM pending_withdrawals WHERE status='pending' ORDER BY created_at DESC")
        rows = c.fetchall()

    if not rows:
        await query.edit_message_text("لا توجد طلبات سحب معلقة.", reply_markup=format_admin_panel_keyboard())
        return

    await query.edit_message_text("جاري عرض الطلبات...")
    for row in rows:
        wid, uid, amount, method, acc_details, created = row
        text = f"🆔 طلب سحب رقم: {wid}\n👤 المستخدم: {uid}\n💰 المبلغ: {amount}\n💳 الطريقة: {method}\n📋 تفاصيل الحساب: {acc_details}\n📅 التاريخ: {created}"
        keyboard = [[InlineKeyboardButton("✅ موافقة", callback_data=f"confirm_withdraw_{wid}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_withdraw_{wid}")]]
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))

    await context.bot.send_message(chat_id=user_id, text="🔙 للعودة إلى لوحة التحكم", reply_markup=format_admin_panel_keyboard())

async def admin_ichancy_charge_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, amount, created_at FROM ichancy_charge_requests WHERE status='pending' ORDER BY created_at DESC")
        rows = c.fetchall()

    if not rows:
        await query.edit_message_text("لا توجد طلبات شحن Ichancy معلقة.", reply_markup=format_admin_panel_keyboard())
        return

    await query.edit_message_text("جاري عرض الطلبات...")
    for row in rows:
        req_id, uid, amount, created = row
        text = f"🆔 طلب شحن Ichancy رقم: {req_id}\n👤 المستخدم: {uid}\n💰 المبلغ: {amount}\n📅 التاريخ: {created}"
        keyboard = [[InlineKeyboardButton("✅ موافقة (خصم من رصيد البوت)", callback_data=f"confirm_ichancy_charge_{req_id}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_ichancy_charge_{req_id}")]]
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))

    await context.bot.send_message(chat_id=user_id, text="🔙 للعودة إلى لوحة التحكم", reply_markup=format_admin_panel_keyboard())

async def admin_ichancy_withdraw_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, amount, created_at FROM ichancy_withdraw_requests WHERE status='pending' ORDER BY created_at DESC")
        rows = c.fetchall()

    if not rows:
        await query.edit_message_text("لا توجد طلبات سحب Ichancy معلقة.", reply_markup=format_admin_panel_keyboard())
        return

    await query.edit_message_text("جاري عرض الطلبات...")
    for row in rows:
        req_id, uid, amount, created = row
        text = f"🆔 طلب سحب Ichancy رقم: {req_id}\n👤 المستخدم: {uid}\n💰 المبلغ: {amount}\n📅 التاريخ: {created}"
        keyboard = [[InlineKeyboardButton("✅ موافقة (إضافة رصيد)", callback_data=f"confirm_ichancy_withdraw_{req_id}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_ichancy_withdraw_{req_id}")]]
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))

    await context.bot.send_message(chat_id=user_id, text="🔙 للعودة إلى لوحة التحكم", reply_markup=format_admin_panel_keyboard())

async def admin_pending_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, username, message_text, message_type, created_at FROM pending_messages WHERE status='pending' ORDER BY created_at DESC")
        rows = c.fetchall()

    if not rows:
        await query.edit_message_text("لا توجد رسائل للنشر.", reply_markup=format_admin_panel_keyboard())
        return

    await query.edit_message_text("جاري عرض الطلبات...")
    for row in rows:
        msg_id, uid, uname, msg_text, msg_type, created = row
        text = f"📨 رسالة رقم: {msg_id}\n👤 المستخدم: {uid} ({uname})\n📝 النوع: {msg_type}\n📄 النص: {msg_text if msg_text else 'لا يوجد'}\n📅 التاريخ: {created}"
        keyboard = [[InlineKeyboardButton("✅ نشر", callback_data=f"publish_msg_{msg_id}"), InlineKeyboardButton("❌ تجاهل", callback_data=f"ignore_msg_{msg_id}")]]
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))

    await context.bot.send_message(chat_id=user_id, text="🔙 للعودة إلى لوحة التحكم", reply_markup=format_admin_panel_keyboard())

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT SUM(balance) FROM users")
        total_balance = c.fetchone()[0] or 0
        c.execute('''
            SELECT u.user_id, u.username, u.first_name, u.balance, 
                   i.username as ichancy_user, i.ichancy_balance
            FROM users u
            LEFT JOIN ichancy_accounts i ON u.user_id = i.telegram_id
            WHERE i.telegram_id IS NOT NULL
            ORDER BY u.balance DESC
        ''')
        rows = c.fetchall()

    text = f"📊 *إحصائيات البوت*\n\n👥 إجمالي المسجلين: {total_users}\n💰 إجمالي الرصيد في البوت: {total_balance:.2f}\n\n📋 *تفاصيل اللاعبين (في Ichancy):*\n"
    if not rows:
        text += "لا يوجد لاعبين مسجلين في Ichancy."
    else:
        for row in rows[:10]:
            uid, uname, fname, bal, ichancy_user, ichancy_bal = row
            text += f"\n👤 {fname or 'لا اسم'} (@{uname or 'لا يوجد'})\n   🆔 {uid}\n   🎮 Ichancy: {ichancy_user}\n   💰 رصيد البوت: {bal:.2f}\n   💎 رصيد Ichancy: {ichancy_bal or 0:.2f}\n"

    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=format_admin_panel_keyboard())

async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return
    await query.edit_message_text("🔨 أرسل معرف المستخدم (user_id) الذي تريد حظره:", reply_markup=get_back_keyboard())
    return BAN_USER_INPUT

async def ban_user_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ غير مصرح.")
        return ConversationHandler.END
    try:
        target_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ معرف غير صالح. يرجى إرسال رقم فقط.", reply_markup=format_admin_panel_keyboard())
        return ConversationHandler.END

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (target_id,))
        if c.rowcount == 0:
            c.execute("INSERT OR IGNORE INTO users (user_id, banned) VALUES (?, 1)", (target_id,))
        conn.commit()

    await update.message.reply_text(f"✅ تم حظر المستخدم {target_id}.", reply_markup=format_admin_panel_keyboard())
    return ConversationHandler.END

async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return
    await query.edit_message_text("🔓 أرسل معرف المستخدم (user_id) الذي تريد رفع الحظر عنه:", reply_markup=get_back_keyboard())
    return UNBAN_USER_INPUT

async def unban_user_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ غير مصرح.")
        return ConversationHandler.END
    try:
        target_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ معرف غير صالح. يرجى إرسال رقم فقط.", reply_markup=format_admin_panel_keyboard())
        return ConversationHandler.END

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (target_id,))
        conn.commit()

    await update.message.reply_text(f"✅ تم رفع الحظر عن المستخدم {target_id}.", reply_markup=format_admin_panel_keyboard())
    return ConversationHandler.END

async def admin_banned_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, username, first_name FROM users WHERE banned = 1")
        rows = c.fetchall()

    if not rows:
        await query.edit_message_text("لا يوجد مستخدمين محظورين.", reply_markup=format_admin_panel_keyboard())
        return

    text = "🚫 قائمة المحظورين:\n\n"
    for row in rows:
        uid, uname, fname = row
        text += f"👤 {uid} | {uname or 'لا يوجد'} | {fname or 'لا يوجد'}\n"

    await query.edit_message_text(text, reply_markup=format_admin_panel_keyboard())

async def confirm_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    data = query.data
    charge_id = int(data.split('_')[-1])

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, amount FROM pending_charges WHERE id = ? AND status = 'pending'", (charge_id,))
        row = c.fetchone()
        if not row:
            await query.edit_message_text("لم يتم العثور على الطلب أو تمت معالجته مسبقاً.")
            return

        target_user_id, amount = row
        c.execute("UPDATE pending_charges SET status = 'completed' WHERE id = ?", (charge_id,))
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_user_id))
        c.execute("UPDATE users SET total_charges = total_charges + ? WHERE user_id = ?", (amount, target_user_id))

        c.execute("SELECT referred_by FROM users WHERE user_id = ?", (target_user_id,))
        ref_row = c.fetchone()
        if ref_row and ref_row[0]:
            referrer_id = ref_row[0]
            commission = amount * REFERRAL_PERCENT
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (commission, referrer_id))
            try:
                await context.bot.send_message(chat_id=referrer_id, text=f"🎉 تم إضافة {commission:.2f} ليرة إلى رصيدك كعمولة عن شحنة المُحال!", parse_mode='Markdown')
            except:
                pass
        conn.commit()

    await query.edit_message_text(f"✅ تمت الموافقة على طلب الشحن {charge_id} للمستخدم {target_user_id} بمبلغ {amount}.")
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"✅ تم شحن رصيدك بمبلغ {amount} بنجاح.")
    except:
        pass

async def reject_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    data = query.data
    charge_id = int(data.split('_')[-1])

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE pending_charges SET status = 'rejected' WHERE id = ?", (charge_id,))
        conn.commit()

    await query.edit_message_text(f"❌ تم رفض طلب الشحن {charge_id}.")
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"❌ تم رفض طلب الشحن الخاص بك (رقم {charge_id}). يرجى التواصل مع الدعم.")
    except:
        pass

async def confirm_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    data = query.data
    withdraw_id = int(data.split('_')[-1])

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, amount FROM pending_withdrawals WHERE id = ? AND status = 'pending'", (withdraw_id,))
        row = c.fetchone()
        if not row:
            await query.edit_message_text("لم يتم العثور على الطلب أو تمت معالجته مسبقاً.")
            return

        target_user_id, amount = row
        c.execute("SELECT balance FROM users WHERE user_id = ?", (target_user_id,))
        balance = c.fetchone()[0]
        if balance < amount:
            await query.edit_message_text("❌ رصيد المستخدم غير كافٍ.")
            return

        c.execute("UPDATE pending_withdrawals SET status = 'completed' WHERE id = ?", (withdraw_id,))
        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, target_user_id))
        conn.commit()

    await query.edit_message_text(f"✅ تمت الموافقة على طلب السحب {withdraw_id} للمستخدم {target_user_id} بمبلغ {amount}.")
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"✅ تمت الموافقة على طلب السحب الخاص بك بمبلغ {amount}. سيتم تحويل المبلغ إلى حسابك قريباً.")
    except:
        pass

async def reject_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    data = query.data
    withdraw_id = int(data.split('_')[-1])

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE pending_withdrawals SET status = 'rejected' WHERE id = ?", (withdraw_id,))
        conn.commit()

    await query.edit_message_text(f"❌ تم رفض طلب السحب {withdraw_id}.")
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"❌ تم رفض طلب السحب الخاص بك (رقم {withdraw_id}). يرجى التواصل مع الدعم.")
    except:
        pass

async def confirm_ichancy_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = query.from_user.id
    if not is_admin(admin_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    data = query.data
    req_id = int(data.split('_')[-1])

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, amount FROM ichancy_charge_requests WHERE id = ? AND status='pending'", (req_id,))
        row = c.fetchone()
        if not row:
            await query.edit_message_text("الطلب غير موجود أو تمت معالجته مسبقاً.")
            return

        target_user_id, amount = row
        c.execute("SELECT balance FROM users WHERE user_id = ?", (target_user_id,))
        balance = c.fetchone()[0]
        if balance < amount:
            await query.edit_message_text("❌ رصيد المستخدم غير كافٍ.")
            return

        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, target_user_id))
        c.execute("UPDATE ichancy_charge_requests SET status = 'completed' WHERE id = ?", (req_id,))
        conn.commit()

    await query.edit_message_text(f"✅ تمت الموافقة على طلب شحن Ichancy {req_id}. تم خصم {amount} من رصيد المستخدم.")
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"✅ تمت الموافقة على طلب شحن حساب Ichancy الخاص بك بمبلغ {amount}. تم خصم المبلغ من رصيد البوت.")
    except:
        pass

async def confirm_ichancy_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = query.from_user.id
    if not is_admin(admin_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    data = query.data
    req_id = int(data.split('_')[-1])

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, amount FROM ichancy_withdraw_requests WHERE id = ? AND status='pending'", (req_id,))
        row = c.fetchone()
        if not row:
            await query.edit_message_text("الطلب غير موجود أو تمت معالجته مسبقاً.")
            return

        target_user_id, amount = row
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_user_id))
        c.execute("UPDATE ichancy_withdraw_requests SET status = 'completed' WHERE id = ?", (req_id,))
        conn.commit()

    await query.edit_message_text(f"✅ تمت الموافقة على طلب سحب Ichancy {req_id}. تم إضافة {amount} إلى رصيد المستخدم.")
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"✅ تمت الموافقة على طلب سحب من حساب Ichancy الخاص بك بمبلغ {amount}. تم إضافة المبلغ إلى رصيد البوت.")
    except:
        pass

async def reject_ichancy_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = query.from_user.id
    if not is_admin(admin_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    data = query.data
    req_id = int(data.split('_')[-1])

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE ichancy_charge_requests SET status = 'rejected' WHERE id = ?", (req_id,))
        conn.commit()

    await query.edit_message_text(f"❌ تم رفض طلب شحن Ichancy {req_id}.")
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"❌ تم رفض طلب شحن حساب Ichancy الخاص بك (رقم {req_id}). يرجى التواصل مع الدعم.")
    except:
        pass

async def reject_ichancy_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = query.from_user.id
    if not is_admin(admin_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    data = query.data
    req_id = int(data.split('_')[-1])

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE ichancy_withdraw_requests SET status = 'rejected' WHERE id = ?", (req_id,))
        conn.commit()

    await query.edit_message_text(f"❌ تم رفض طلب سحب Ichancy {req_id}.")
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"❌ تم رفض طلب سحب من حساب Ichancy الخاص بك (رقم {req_id}). يرجى التواصل مع الدعم.")
    except:
        pass

async def publish_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    data = query.data
    msg_id = int(data.split('_')[-1])

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, message_text, message_type, file_id FROM pending_messages WHERE id = ? AND status='pending'", (msg_id,))
        row = c.fetchone()
        if not row:
            await query.edit_message_text("الرسالة غير موجودة أو تم نشرها مسبقاً.")
            return

        sender_id, msg_text, msg_type, file_id = row
        c.execute("UPDATE pending_messages SET status = 'published' WHERE id = ?", (msg_id,))
        conn.commit()

    await query.edit_message_text(f"✅ تم نشر الرسالة رقم {msg_id}.")

async def ignore_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ غير مصرح.")
        return

    data = query.data
    msg_id = int(data.split('_')[-1])

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE pending_messages SET status = 'ignored' WHERE id = ?", (msg_id,))
        conn.commit()

    await query.edit_message_text(f"❌ تم تجاهل الرسالة {msg_id}.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if is_banned(user_id):
        await query.edit_message_text("❌ حسابك محظور.")
        return ConversationHandler.END

    if data == "main_menu":
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    elif data == "balance":
        user_data = get_user(user_id)
        text = f"💰 رصيدك الحالي هو: {user_data['balance']}\n🆔 معرفك الخاص: {user_id}\n⭐ نقاط الولاء: {user_data['loyalty_points']:.2f}\n\nاستبدال نقاط الولاء 🔥"
        await query.edit_message_text(text, reply_markup=get_back_keyboard())
        return ConversationHandler.END

    elif data == "referral_system":
        total_refs, active_refs = get_referrals_count(user_id)
        encoded = base64.b64encode(str(user_id).encode()).decode().rstrip('=')
        referral_link = f"https://t.me/{BOT_USERNAME}?start={encoded}"
        next_payout = get_next_payout()
        remaining = format_remaining_time(next_payout)

        template = get_referral_system_text()
        if template:
            text = template.format(link=referral_link, total=total_refs, active=active_refs, next=next_payout, remaining=remaining)
        else:
            text = f"👥 *نظام الإحالات*\n\nرابطك: {referral_link}\nعدد الإحالات: {total_refs}\nالنشطة: {active_refs}"
        
        keyboard = [[InlineKeyboardButton("📋 نسخ الرابط", callback_data="copy_link")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    elif data == "copy_link":
        encoded = base64.b64encode(str(user_id).encode()).decode().rstrip('=')
        referral_link = f"https://t.me/{BOT_USERNAME}?start={encoded}"
        await query.answer(text=referral_link, show_alert=True)
        return ConversationHandler.END

    elif data == "charge":
        context.user_data["action"] = "charge"
        await query.edit_message_text("اختر إحدى طرق الشحن:", reply_markup=get_payment_methods_keyboard())
        return ConversationHandler.END

    elif data == "withdraw":
        await query.edit_message_text("اختر طريقة السحب المناسبة لك:", reply_markup=get_withdrawal_methods_keyboard())
        return ConversationHandler.END

    elif data.startswith("withdraw_"):
        return await withdraw_method_selected(update, context)

    elif data.startswith("pay_"):
        method = data.replace("pay_", "")
        context.user_data["payment_method"] = method

        if method == "syriatel":
            details = f"🔹 *Syriatel Cash* - أكواد الشحن:\n`{SYRIATEL_CODES[0]}`\n`{SYRIATEL_CODES[1]}`\n\nالرجاء إرسال المبلغ الذي تريد شحنه:"
            await query.edit_message_text(details, parse_mode='Markdown', reply_markup=get_back_keyboard())
            return AMOUNT_INPUT
        elif method == "usdt":
            details = f"🔹 *العملات الرقمية USDT*\n• شبكة BEP20:\n`{USDT_BEP20}`\n\n• شبكة TRC20:\n`{USDT_TRC20}`\n\nالرجاء إرسال المبلغ الذي تريد شحنه (بـ USDT):"
            await query.edit_message_text(details, parse_mode='Markdown', reply_markup=get_back_keyboard())
            return AMOUNT_INPUT
        elif method == "sham":
            await query.edit_message_text("❌ *عذراً، خدمة Sham Cash متوقفة مؤقتاً لأسباب تقنية.*\nيرجى استخدام الطرق الأخرى المتاحة.", parse_mode='Markdown', reply_markup=get_payment_methods_keyboard())
            return ConversationHandler.END
        elif method == "bemo":
            await query.edit_message_text("🔹 *Bemo Bank*\n\nالخدمة غير متوفرة حالياً ❌", parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
            return ConversationHandler.END
        else:
            await query.edit_message_text("طريقة دفع غير معروفة.", reply_markup=get_main_menu_keyboard())
            return ConversationHandler.END

    elif data == "gift":
        await query.edit_message_text("🎁 ميزة إهداء الرصيد قيد التطوير حالياً.", reply_markup=get_back_keyboard())
    elif data == "gift_code":
        await query.edit_message_text("🎟️ ميزة كود الهدية قيد التطوير.", reply_markup=get_back_keyboard())
    elif data == "message_admin":
        await query.edit_message_text("📩 يمكنك إرسال رسالتك الآن وسنرد عليك قريباً.", reply_markup=get_back_keyboard())
    elif data == "history":
        await query.edit_message_text("📜 سجل عملياتك قيد الإنشاء.", reply_markup=get_back_keyboard())
    elif data == "tutorials":
        await query.edit_message_text("📚 الشروحات: يمكنك مشاهدة الفيديوهات على قناتنا.", reply_markup=get_back_keyboard())
    elif data == "apk":
        await query.edit_message_text("📲 رابط تحميل التطبيق: https://www.ichancy.com/apk", reply_markup=get_back_keyboard())
    elif data == "register_ichancy":
        return await register_start(update, context)
    elif data == "my_ichancy_account":
        account = get_ichancy_account(user_id)
        if account:
            text = f"📋 *بيانات حساب Ichancy الخاص بك:*\n\n👤 اسم المستخدم: `{account['username']}`\n🔑 كلمة المرور: `{account['password']}`\n📧 البريد الإلكتروني: `{account['email']}`\n\nاحتفظ بهذه المعلومات في مكان آمن."
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=get_back_keyboard())
        else:
            await query.edit_message_text("❌ ليس لديك حساب Ichancy بعد. يمكنك إنشاء واحد بالضغط على الزر '📋 حساب Ichancy'.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END
    elif data == "ichancy_menu":
        await ichancy_menu(update, context)
        return ConversationHandler.END
    elif data == "ichancy_charge":
        return await ichancy_charge_start(update, context)
    elif data == "ichancy_withdraw":
        return await ichancy_withdraw_start(update, context)
    elif data == "ichancy_delete":
        await ichancy_delete_account(update, context)
        return ConversationHandler.END
    elif data == "ichancy_delete_confirm":
        await ichancy_delete_confirm(update, context)
        return ConversationHandler.END
    elif data == "admin_panel":
        await admin_panel(update, context)
        return ConversationHandler.END
    elif data == "admin_pending_charges":
        await admin_pending_charges(update, context)
        return ConversationHandler.END
    elif data == "admin_pending_withdrawals":
        await admin_pending_withdrawals(update, context)
        return ConversationHandler.END
    elif data == "admin_ichancy_charge":
        await admin_ichancy_charge_requests(update, context)
        return ConversationHandler.END
    elif data == "admin_ichancy_withdraw":
        await admin_ichancy_withdraw_requests(update, context)
        return ConversationHandler.END
    elif data == "admin_pending_messages":
        await admin_pending_messages(update, context)
        return ConversationHandler.END
    elif data == "admin_ban_user":
        return await admin_ban_user(update, context)
    elif data == "admin_unban_user":
        return await admin_unban_user(update, context)
    elif data == "admin_banned_list":
        await admin_banned_list(update, context)
        return ConversationHandler.END
    elif data == "admin_stats":
        await admin_stats(update, context)
        return ConversationHandler.END
    elif data == "admin_announcement_menu":
        await admin_announcement_menu(update, context)
        return ConversationHandler.END
    elif data == "admin_referral_announcement_write":
        return await admin_referral_announcement_write(update, context)
    elif data == "admin_referral_announcement_show":
        await admin_referral_announcement_show(update, context)
        return ConversationHandler.END
    elif data == "admin_referral_announcement_clear":
        await admin_referral_announcement_clear(update, context)
        return ConversationHandler.END
    elif data == "admin_referral_system_write":
        return await admin_referral_system_write(update, context)
    elif data == "admin_referral_system_show":
        await admin_referral_system_show(update, context)
        return ConversationHandler.END
    elif data == "admin_referral_system_clear":
        await admin_referral_system_clear(update, context)
        return ConversationHandler.END
    elif data == "admin_main_announcement_write":
        return await admin_main_announcement_write(update, context)
    elif data == "admin_main_announcement_show":
        await admin_main_announcement_show(update, context)
        return ConversationHandler.END
    elif data == "admin_main_announcement_clear":
        await admin_main_announcement_clear(update, context)
        return ConversationHandler.END
    elif data == "admin_announcement_write":
        return await admin_announcement_write(update, context)
    elif data == "admin_announcement_show":
        await admin_announcement_show(update, context)
        return ConversationHandler.END
    elif data == "admin_announcement_clear":
        await admin_announcement_clear(update, context)
        return ConversationHandler.END
    elif data.startswith("confirm_charge_"):
        await confirm_charge_callback(update, context)
        return ConversationHandler.END
    elif data.startswith("reject_charge_"):
        await reject_charge_callback(update, context)
        return ConversationHandler.END
    elif data.startswith("confirm_withdraw_"):
        await confirm_withdraw_callback(update, context)
        return ConversationHandler.END
    elif data.startswith("reject_withdraw_"):
        await reject_withdraw_callback(update, context)
        return ConversationHandler.END
    elif data.startswith("confirm_ichancy_charge_"):
        await confirm_ichancy_charge_callback(update, context)
        return ConversationHandler.END
    elif data.startswith("reject_ichancy_charge_"):
        await reject_ichancy_charge_callback(update, context)
        return ConversationHandler.END
    elif data.startswith("confirm_ichancy_withdraw_"):
        await confirm_ichancy_withdraw_callback(update, context)
        return ConversationHandler.END
    elif data.startswith("reject_ichancy_withdraw_"):
        await reject_ichancy_withdraw_callback(update, context)
        return ConversationHandler.END
    elif data.startswith("publish_msg_"):
        await publish_message_callback(update, context)
        return ConversationHandler.END
    elif data.startswith("ignore_msg_"):
        await ignore_message_callback(update, context)
        return ConversationHandler.END
    elif data.startswith("reply_msg_"):
        return await reply_to_user_start(update, context)

    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    charge_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^(pay_syriatel|pay_usdt|pay_sham)$")],
        states={
            AMOUNT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_received)],
            TRANSACTION_ID_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, transaction_id_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(charge_conv)

    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^withdraw_.*$")],
        states={
            WITHDRAW_ADDRESS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_address_received)],
            WITHDRAW_AMOUNT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(withdraw_conv)

    reg_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^register_ichancy$")],
        states={
            REGISTER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_username)],
            REGISTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(reg_conv_handler)

    ban_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^admin_ban_user$")],
        states={
            BAN_USER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_user_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(ban_conv_handler)

    unban_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^admin_unban_user$")],
        states={
            UNBAN_USER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, unban_user_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(unban_conv_handler)

    ichancy_charge_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^ichancy_charge$")],
        states={
            ICHANCY_CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ichancy_charge_amount_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(ichancy_charge_conv)

    ichancy_withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^ichancy_withdraw$")],
        states={
            ICHANCY_WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ichancy_withdraw_amount_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(ichancy_withdraw_conv)

    referral_announcement_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_referral_announcement_write, pattern="^admin_referral_announcement_write$")],
        states={ANNOUNCEMENT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_referral_announcement_save)]},
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(referral_announcement_conv)

    referral_system_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_referral_system_write, pattern="^admin_referral_system_write$")],
        states={ANNOUNCEMENT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_referral_system_save)]},
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(referral_system_conv)

    main_announcement_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_main_announcement_write, pattern="^admin_main_announcement_write$")],
        states={ANNOUNCEMENT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_main_announcement_save)]},
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(main_announcement_conv)

    admin_announcement_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_announcement_write, pattern="^admin_announcement_write$")],
        states={ANNOUNCEMENT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_announcement_save)]},
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(admin_announcement_conv)

    reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reply_to_user_start, pattern="^reply_msg_\\d+$")],
        states={
            REPLY_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reply_to_user_send)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(button_handler, pattern="main_menu")],
    )
    app.add_handler(reply_conv)

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_private_message))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Sticker.ALL, handle_private_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_private_message))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("offers", offers_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("admin", admin_panel))

    app.add_error_handler(error_handler)

    print("البوت يعمل...")
    return app

if __name__ == "__main__":
    app = main()
    port = int(os.environ.get('PORT', 10000))
    app.run_webhook(listen="0.0.0.0", port=port)

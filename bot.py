import asyncio
import json
import logging
import os
import random
import re
import string
import threading
from typing import Tuple

from fastapi import FastAPI, Request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
import uvicorn
import requests

# -------------------------------------------------------------
# SAFE OCR / TESSERACT IMPORT CHECK
# -------------------------------------------------------------
OCR_AVAILABLE = False
try:
    from PIL import Image
    import pytesseract

    pytesseract.get_tesseract_version()
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

# -------------------------------------------------------------
# CONFIGURATIONS & ENVIRONMENT VARIABLES
# -------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6722504980"))

# የቻናል ID - በቁጥር ስለሆነ ከፊት -100 ይጨመራል
CHANNEL_USERNAME = -1003865662998

MY_CBE_NAME = "Addis Alemayehu"
MY_TELEBIRR_NAME = "Addis"

DB_FILE = "users_db.json"
USED_TXNS_FILE = "used_txns.json"

(
    DEPOSIT_METHOD,
    DEPOSIT_AMOUNT,
    DEPOSIT_PHONE,
    DEPOSIT_REF_CODE,
    DEPOSIT_PROOF,
    TRANSFER_TARGET_ID,
    TRANSFER_AMOUNT,
    TRANSFER_PIN,
    WITHDRAW_METHOD,
    WITHDRAW_ACCOUNT_INFO,
    WITHDRAW_AMOUNT,
    WITHDRAW_PIN,
) = range(12)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
db_lock = threading.Lock()

# -------------------------------------------------------------
# FASTAPI & AFRICA'S TALKING SMS WEBHOOK
# -------------------------------------------------------------
web_app = FastAPI()

@web_app.get("/")
def read_root():
    return {"status": "ok", "bot": "running"}

@web_app.get("/sms-webhook")
def sms_webhook_get():
    return "Webhook active"

@web_app.post("/sms-webhook")
async def sms_webhook_post(request: Request):
    form_data = await request.form()
    sender = form_data.get("from", "")
    text = form_data.get("text", "")
    date = form_data.get("date", "")

    if BOT_TOKEN and ADMIN_ID:
        telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        message = f"📩 አዲስ SMS ደርሷል!\n\nከ: {sender}\nመልእክት: {text}\nቀን: {date}"
        payload = {
            "chat_id": ADMIN_ID,
            "text": message
        }
        try:
            requests.post(telegram_url, json=payload, timeout=5)
        except Exception as e:
            logging.error(f"Error sending SMS to Telegram: {e}")

    return {"status": "success"}

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(web_app, host="0.0.0.0", port=port, log_level="warning")


# -------------------------------------------------------------
# DATABASE MANAGEMENT
# -------------------------------------------------------------
def load_used_txns() -> set:
    if os.path.exists(USED_TXNS_FILE):
        try:
            with open(USED_TXNS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_used_txn(txn_id: str):
    used_txns.add(txn_id)
    with db_lock:
        try:
            with open(USED_TXNS_FILE, "w", encoding="utf-8") as f:
                json.dump(list(used_txns), f)
        except Exception as e:
            logging.error(f"Error saving txns: {e}")

used_txns = load_used_txns()

def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {int(k): v for k, v in data.items()}
        except Exception as e:
            logging.error(f"Error loading DB: {e}")
            return {}
    return {}

def save_db():
    with db_lock:
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(users_db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Error saving DB: {e}")

users_db = load_db()

def generate_ref_code(user_id: int) -> str:
    return f"REF{user_id}"

def generate_ticket_number() -> str:
    return "TKT" + "".join(random.choices(string.digits, k=6))

def get_main_keyboard():
    keyboard = [
        [
            KeyboardButton("🎟 ትኬት ይቁረጡ"),
            KeyboardButton("💸 ገንዘብ ያውጡ"),
        ],
        [
            KeyboardButton("🔄 ገንዘብ ይላኩ"),
            KeyboardButton("🎁 የሽልማት ዝርዝር"),
        ],
        [KeyboardButton("💼 የኔ ዋሌት")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# -------------------------------------------------------------
# AUTOMATIC BACKUP TO ADMIN
# -------------------------------------------------------------
async def backup_database_to_admin(context: ContextTypes.DEFAULT_TYPE):
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as doc:
                await context.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=doc,
                    caption="📦 **የደንበኞች መረጃ አውቶማቲክ ባክአፕ (Backup File)**",
                )
    except Exception as e:
        logging.error(f"Backup Error: {e}")


# -------------------------------------------------------------
# VERIFICATION LOGIC
# -------------------------------------------------------------
def verify_receipt_text(
    text: str, expected_amount: int, method: str
) -> Tuple[bool, str]:
    clean_text = text.lower()

    if "addis" not in clean_text:
        return (
            False,
            "ገንዘቡን አላስገቡም እባክዎ ገንዘቡን ገቢ በማድረግ ትኬትዎን ይውሰዱ!",
        )

    amount_str = f"{expected_amount:,}"
    amount_pattern = rf"\b({expected_amount}|{amount_str})(\.00)?\b"
    if not re.search(amount_pattern, text):
        return (
            False,
            "ገንዘቡን አላስገቡም እባክዎ ገንዘቡን ገቢ በማድረግ ትኬትዎን ይውሰዱ!",
        )

    txn_match = re.search(r"\b(FT[A-Za-z0-9]{8,10}|[A-Za-z0-9]{10,12})\b", text)
    if txn_match:
        txn_id = txn_match.group(1).upper()
        if txn_id in used_txns:
            return (
                False,
                "❌ ይህ የትራንዛክሽን ቁጥር/ደረሰኝ ቀደም ብሎ ጥቅም ላይ ውሏል!",
            )
        save_used_txn(txn_id)

    return True, "✅ ማረጋገጫው ተሳክቷል!"


# -------------------------------------------------------------
# COMMAND & MENU HANDLERS
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "ተጠቃሚ"

    if user_id not in users_db:
        users_db[user_id] = {
            "first_name": first_name,
            "wallet_balance": 0,
            "pin": None,
            "ref_code": None,
            "tickets": [],
            "referred_count": 0,
            "phone": None,
        }
        save_db()
    else:
        users_db[user_id]["first_name"] = first_name
        save_db()

    await update.message.reply_text(
        "✨ **እንኳን ወደ ህዳሴ ዲጂታል ሎተሪ በደህና መጡ!** ✨\n\n"
        "የሎተሪ ትኬት በመቁረጥ የተለያዩ አጓጊ ሽልማቶችን ያሸንፉ!\n"
        "📺 የሎተሪ አወጣጥ ሂደቱ ግልጽ እና አጓጊ ሆኖ በቻናላችን ቀጥታ (Live) ይተላለፋል።",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown",
    )

    if not users_db[user_id].get("pin"):
        await update.message.reply_text(
            "🔒 ለአካውንትዎ ደህንነት ሲባል ለወደፊት ገንዘብ ሲልኩና ሲያወጡ የሚያገለግልዎትን ባለ 4 አሃዝ የሚስጥር ቁጥር (PIN) ያስገቡ፦"
        )


async def general_text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id in users_db and not users_db[user_id].get("pin"):
        if text.isdigit() and len(text) == 4:
            users_db[user_id]["pin"] = text
            save_db()
            await update.message.reply_text(
                "✅ የሚስጥር ቁጥርዎ በጥሩ ሁኔታ ተመዝግቧል! አሁን አገልግሎቱን መጠቀም ይችላሉ።",
                reply_markup=get_main_keyboard(),
            )
        else:
            await update.message.reply_text(
                "❌ የሚስጥር ቁጥር ባለ 4 አሃዝ ቁጥር መሆን አለበት (ምሳሌ፦ 1234)። እባክዎን እንደገና ያስገቡ፦"
            )


async def show_rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎁 **የሽልማት ዝርዝር፦**\n\n"
        "1️⃣ **1ኛ እጣ 10,000 ብር ** \n\n"
        "2️⃣ **2ኛ እጣ 8,000 ብር ** \n\n"
        "3️⃣ **3ኛ እጣ 6,000 ብር ** \n\n"
        "4️⃣ **4ኛ እጣ 5,000 ብር ** \n\n"
        "5️⃣ **5ኛ እጣ 4,000 ብር ** \n\n"
        "6️⃣ **6ኛ እጣ 3,000 ብር ** \n\n"
        "7️⃣ **7ኛ እጣ 2,000 ብር ** \n\n"
        "8️⃣ **8ኛ እጣ 1,500 ብር ** \n\n"
        "9️⃣ **9ኛ እጣ 1,000 ብር ** \n\n"
        "🔟 **10ኛ እጣ 500 ብር ** \n\n"
        "✨ ሌሎች አጓጊ ሽልማቶችን በ ሁለተኛ ዙር ይጠብቁን!"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = users_db.get(user_id, {})
    balance = user_data.get("wallet_balance", 0)
    ref_code = user_data.get("ref_code")
    tickets = len(user_data.get("tickets", []))

    ref_display = (
        f"`{ref_code}`" if ref_code else "⚠️ ትኬት ሲቆርጡ የሚሰጥዎት ይሆናል"
    )

    msg = (
        f"💼 **የእርስዎ አካውንት መረጃ**\n\n"
        f"🆔 **የእርስዎ ID፦** `{user_id}`\n"
        f"💰 **የዋሌት መጠን፦** {balance} ETB\n"
        f"🎟 **የቆረጡት ትኬት ብዛት፦** {tickets}\n"
        f"🔗 **የእርስዎ ሪፈራል ኮድ፦** {ref_display}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


# -------------------------------------------------------------
# 🎟 T

import os
import asyncio
import logging
import json
import random
import re
import time
import requests
import uvicorn
from fastapi import FastAPI, Request
import threading
from PIL import Image
import pytesseract
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

# -------------------------------------------------------------
# CONFIGURATIONS
# -------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8833785126:AAEQgzZ8Wbg4t4-KDlcT1itp-E8DHbNw79M")
ADMIN_ID = 6722504980  # የአድሚን Telegram ID

# 📢 የኦፊሴላዊ ቻናልህ Username (ቦቱን የቻናሉ Admin ማድረግህን አረጋግጥ!)
CHANNEL_USERNAME = "@YourChannelUsername" 

# 🏦 TELEBIRR MERCHANT API KEYS
TELEBIRR_APP_ID = os.environ.get("TELEBIRR_APP_ID", "YOUR_APP_ID")
TELEBIRR_APP_KEY = os.environ.get("TELEBIRR_APP_KEY", "YOUR_APP_KEY")
TELEBIRR_SHORTCODE = os.environ.get("TELEBIRR_SHORTCODE", "YOUR_SHORTCODE")
SERVER_DOMAIN = os.environ.get("SERVER_DOMAIN", "https://your-render-app.onrender.com")

TICKET_PRICE = 50           # የአንድ ቲኬት ዋጋ (ETB)
REFERRAL_BONUS = 10         # ለጋባዡ የሚሄድ (ETB)
ADMIN_REFERRAL_SHARE = 40   # በሪፈራል ሲቆረጥ ለአድሚን የሚሄድ (ETB)

MIN_WITHDRAW_AMOUNT = 500   # የሚወጣው አነስተኛ የብር መጠን
WITHDRAW_FEE = 10           # የትራንስፈር አገልግሎት ክፍያ
TRANSFER_FEE = 1            # ከዋሌት ወደ ዋሌት የትራንስፈር አገልግሎት ክፍያ
REQUIRED_REFERRALS = 10     # ገንዘብ ለማውጣት የሚያስፈልግ አነስተኛ የሪፈራል ብዛት

CBE_ACCOUNT = "1000723732108"
TELEBIRR_NUMBER = "0914197335"

# 1. የተስተካከለው የሽልማት ዝርዝር (Core i7 11th Gen Laptop ብቻ)
PRIZES = [
    "🏆 የሎተሪው ዋና እጣ፦ Core i7 11th Generation Laptop 💻"
]

DB_FILE = "users_db.json"
USED_TXNS_FILE = "used_txns.json"

telegram_app = None

# -------------------------------------------------------------
# TESSERACT CONFIGURATION
# -------------------------------------------------------------
def configure_tesseract():
    if os.name == 'nt':
        win_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(win_path):
            pytesseract.pytesseract.tesseract_cmd = win_path
    else:
        linux_paths = ['/usr/bin/tesseract', '/usr/local/bin/tesseract']
        for path in linux_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break

configure_tesseract()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# CONVERSATION STATES
DEPOSIT_METHOD, DEPOSIT_AMOUNT, DEPOSIT_PROOF = range(3)
WITHDRAW_AMOUNT, WITHDRAW_DETAILS = range(3, 5)
BUY_TICKET_QTY = range(5, 6)
TRANSFER_RECIPIENT, TRANSFER_AMOUNT = range(6, 8)

# -------------------------------------------------------------
# DATABASE FUNCTIONS
# -------------------------------------------------------------
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                db = {int(k): v for k, v in data.items()}
                for u in db.values():
                    u.setdefault('wallet_balance', 0)
                    u.setdefault('ref_balance', 0)
                    u.setdefault('tickets', 0)
                    u.setdefault('ticket_numbers', [])
                    u.setdefault('phone', None)
                    u.setdefault('referred_count', 0)
                return db
        except Exception as e:
            logging.error(f"Error loading DB: {e}")
    return {}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(users_db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Error saving DB: {e}")

def load_used_txns():
    if os.path.exists(USED_TXNS_FILE):
        try:
            with open(USED_TXNS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logging.error(f"Error loading Used Txns: {e}")
    return set()

def save_used_txns():
    try:
        with open(USED_TXNS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(used_transactions), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Error saving Used Txns: {e}")

users_db = load_db()
used_transactions = load_used_txns()

def ensure_admin_exists():
    if ADMIN_ID not in users_db:
        users_db[ADMIN_ID] = {
            'wallet_balance': 0,
            'ref_balance': 0,
            'tickets': 0,
            'referrer': None,
            'username': "Admin",
            'full_name': "System Admin",
            'phone': None,
            'ticket_numbers': [],
            'referred_count': 0
        }
        save_db()

ensure_admin_exists()

# -------------------------------------------------------------
# FASTAPI WEB SERVER FOR RENDER & TELEBIRR WEBHOOK
# -------------------------------------------------------------
web_app = FastAPI()

@web_app.get("/")
def health_check():
    return {"status": "ok", "message": "Hidasse Lottery Bot is running!"}

@web_app.post("/telebirr/webhook")
async def telebirr_webhook(request: Request):
    try:
        data = await request.json()
        logging.info(f"Telebirr Webhook Received: {data}")

        if data.get("tradeStatus") == "COMPLETED" or data.get("code") == 0:
            out_trade_no = data.get("outTradeNo", "")
            parts = out_trade_no.split("_")
            
            if len(parts) >= 2 and parts[1].isdigit():
                user_id = int(parts[1])
                amount = float(data.get("totalAmount", 0))

                if user_id in users_db:
                    users_db[user_id]['wallet_balance'] += amount
                    save_db()

                    if telegram_app:
                        asyncio.run_coroutine_threadsafe(
                            telegram_app.bot.send_message(
                                chat_id=user_id,
                                text=(
                                    f"🎉 **የቴሌብር አውቶማቲክ ዲፖዚት ተሳክቷል!**\n\n"
                                    f"💵 **የገባው መጠን፦** {amount} ETB\n"
                                    f"💰 **አሁናዊ የዋሌት ሂሳብዎ፦** {users_db[user_id]['wallet_balance']} ETB\n\n"
                                    f"አሁን '🎟️ ቲኬት ቁረጥ' የሚለውን በመጫን መግዛት ይችላሉ!"
                                ),
                                parse_mode="Markdown"
                            ),
                            telegram_app.loop
                        )
                    return {"code": 0, "message": "success"}

        return {"code": -1, "message": "failed"}
    except Exception as e:
        logging.error(f"Webhook processing error: {e}")
        return {"code": -1, "message": "error"}

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(web_app, host="0.0.0.0", port=port, log_level="error")

# -------------------------------------------------------------
# TELEBIRR API HELPER FUNCTION
# -------------------------------------------------------------
def generate_telebirr_payment_link(user_id: int, amount: int) -> str:
    out_trade_no = f"TXN_{user_id}_{int(time.time())}"
    return f"https://telebirr.et/pay?trade_no={out_trade_no}&amount={amount}"

# -------------------------------------------------------------
# KEYBOARDS
# -------------------------------------------------------------
def get_main_menu_keyboard(user_id):
    user = users_db.get(user_id, {})
    balance = user.get('wallet_balance', 0)
    
    keyboard = [
        [InlineKeyboardButton(f"💳 የኔ አካውንት (Balance: {balance} ETB)", callback_data="my_account")],
        [InlineKeyboardButton("📥 ገንዘብ አስገባ (Deposit)", callback_data="start_deposit"),
         InlineKeyboardButton("📤 ገንዘብ አውጣ (Withdraw)", callback_data="start_withdraw")],
        [InlineKeyboardButton("🔄 ገንዘብ ላክ (Transfer)", callback_data="start_transfer"),
         InlineKeyboardButton("🎟️ ቲኬት ቁረጥ", callback_data="start_buy_ticket")],
        [InlineKeyboardButton("🎁 የሽልማት ዝርዝር", callback_data="show_prizes"),
         InlineKeyboardButton("👥 የሪፈራል ሊንክ", callback_data="get_referral")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ወደ ዋናው ማውጫ", callback_data="main_menu")]])

def get_phone_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("📱 ስልክ ቁጥሬን ላክ", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)

# -------------------------------------------------------------
# START & ACCOUNT HANDLERS
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    ensure_admin_exists()

    if user_id not in users_db:
        users_db[user_id] = {
            'wallet_balance': 0,
            'ref_balance': 0,
            'tickets': 0, 
            'referrer': None,
            'username': user.username or "",
            'full_name': user.full_name or "",
            'phone': None,
            'ticket_numbers': [],
            'referred_count': 0
        }
        if context.args and context.args[0].isdigit():
            ref_id = int(context.args[0])
            if ref_id != user_id and ref_id in users_db:
                users_db[user_id]['referrer'] = ref_id
                users_db[ref_id]['referred_count'] = users_db[ref_id].get('referred_count', 0) + 1
        save_db()

    welcome_text = (
        f"እንኳን ወደ **ህዳሴ ሎተሪ** በደህና መጡ! 🎟️\n\n"
        f"ለእርስዎ የተከፈተ የቦት አካውንት አልዎት። ገንዘብ ዲፖዚት በማድረግ ቲኬት መቁረጥ፣ ለሌላ ሰው ገንዘብ ማስተላለፍ ወይም 10 ሰው በመጋበዝ ገንዘብዎን ማውጣት ይችላሉ።\n\n"
        f"💰 የቲኬት ዋጋ፦ **{TICKET_PRICE} ETB**\n"
        f"👥 የሪፈራል ቦነስ፦ **{REFERRAL_BONUS} ETB** (በእርስዎ ሊንክ ሰው ሲገባ)\n"
        f"🔒 ገንዘብ ማውጫ አክቲቭ ለማድረግ፦ **{REQUIRED_REFERRALS} ሰው** መጋበዝ ያስፈልጋል!\n\n"
        f"እባክዎን ከታች ካሉት አማራጮች አንዱን ይምረጡ፦"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    u = users_db.get(user_id, {})
    
    tickets_str = ", ".join([f"`{t}`" for t in u.get('ticket_numbers', [])]) if u.get('ticket_numbers') else "ምንም የለም"
    ref_count = u.get('referred_count', 0)
    withdraw_status = "✅ Active" if ref_count >= REQUIRED_REFERRALS else f"🔒 Inactive ({ref_count}/{REQUIRED_REFERRALS} ተጋብዟል)"

    msg = (
        f"👤 **የእርስዎ አካውንት መረጃ**\n\n"
        f"🆔 የእርስዎ ID፦ `{user_id}`\n"
        f"💵 የዋሌት ሂሳብ (Wallet Balance)፦ **{u.get('wallet_balance', 0)} ETB**\n"
        f"🎁 ከሪፈራል ያገኙት ቦነስ፦ **{u.get('ref_balance', 0)} ETB**\n"
        f"👥 የጋበዟቸው ሰዎች ብዛት፦ **{ref_count}**\n"
        f"🔓 ገንዘብ ማውጣት፦ **{withdraw_status}**\n"
        f"🎟️ የቆረጧቸው ቲኬቶች ብዛት፦ **{u.get('tickets', 0)}**\n"
        f"🔢 የቲኬት ቁጥሮችዎ፦ {tickets_str}\n"
        f"📞 ስልክ ቁጥር፦ `{u.get('phone', 'የተመዘገበ የለም')}`"
    )
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())

# -------------------------------------------------------------
# DEPOSIT FLOW
# -------------------------------------------------------------
async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🏦 Commercial Bank (CBE) - Manual", callback_data="dep_cbe")],
        [InlineKeyboardButton("📲 Telebirr - Automatic API", callback_data="dep_telebirr")],
        [InlineKeyboardButton("❌ ሰርዝ", callback_data="main_menu")]
    ]
    await query.edit_message_text("📥 **ገንዘብ ማስገቢያ መንገድ ይምረጡ፦**", reply_markup=InlineKeyboardMarkup(keyboard))
    return DEPOSIT_METHOD

async def deposit_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = "CBE" if query.data == "dep_cbe" else "Telebirr"
    context.user_data['dep_method'] = method

    if method == "Telebirr":
        msg = (
            f"📌 **የተመረጠው፦ Telebirr Automatic Payment**\n\n"
            f"💵 **ወደ አካውንትዎ ማስገባት (Deposit ማድረግ) የሚፈልጉትን የብር መጠን ያስገቡ፦**"
        )
    else:
        msg = (
            f"📌 **የተመረጠው፦ Commercial Bank of Ethiopia (CBE)**\n"
            f"የሂሳብ ቁጥር፦ `{CBE_ACCOUNT}`\n\n"
            f"💵 **ወደ አካውንትዎ ማስገባት የሚፈልጉትን የብር መጠን ያስገቡ፦**"
        )
    await query.edit_message_text(msg, parse_mode="Markdown")
    return DEPOSIT_AMOUNT

async def deposit_amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or not text.isdigit() or int(text) < 10:
        await update.message.reply_text("⚠️ እባክዎን ትክክለኛ የብር መጠን ያስገቡ (ቢያንስ 10 ETB)፦")
        return DEPOSIT_AMOUNT

    amount = int(text)
    context.user_data['dep_amount'] = amount
    method = context.user_data['dep_method']

    if method == "Telebirr":
        user_id = update.effective_user.id
        pay_url = generate_telebirr_payment_link(user_id, amount)
        
        keyboard = [
            [InlineKeyboardButton("📲 በቴሌብር ለመክፈል እዚህ ይጫኑ", url=pay_url)],
            [InlineKeyboardButton("🔙 ወደ ዋናው ማውጫ", callback_data="main_menu")]
        ]
        
        msg = (
            f"💰 **የሚያስገቡት መጠን፦ {amount} ETB**\n\n"
            f"ከታች ያለውን አዝራር ተጭነው በቴሌብር ክፍያውን እንደጨረሱ የዋሌት ሂሳብዎ **በአውቶማቲክ (በሰከንዶች ውስጥ)** ይሞላል! ✨"
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    msg = (
        f"💰 **የሚያስገቡት መጠን፦ {amount} ETB**\n\n"
        f"እባክዎን ክፍያውን ወደዚህ ሂሳብ ይላኩ፦ `{CBE_ACCOUNT}`\n\n"
        f"🔐 **ክፍያውን ከፈጸሙ በኋላ የወጣውን የትራንዛክሽን ቁጥር (Txn ID) በጽሁፍ ያስገቡ ወይም የደረሰኙን የስክሪንሹት (Screenshot) ፎቶ ይላኩ፦**"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return DEPOSIT_PROOF

async def deposit_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    amount = context.user_data.get('dep_amount', 0)
    text_content = update.message.text or update.message.caption or ""

    if update.message.photo:
        file_path = f"temp_{user_id}.jpg"
        try:
            photo_file = await update.message.photo[-1].get_file()
            await photo_file.download_to_drive(file_path)
            extracted_text = pytesseract.image_to_string(Image.open(file_path))
            text_content += " " + extracted_text
        except Exception as e:
            logging.error(f"OCR Error: {e}")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    txn_match = re.search(r'\b(FT[A-Z0-9]{8,12}|[A-Z0-9]{10,14})\b', text_content, re.IGNORECASE)

    if txn_match:
        txn_id = txn_match.group(1).upper()
        if txn_id in used_transactions:
            await update.message.reply_text("⚠️ **ይህ የትራንዛክሽን ቁጥር ቀደም ሲል ጥቅም ላይ ውሏል!**")
            return DEPOSIT_PROOF

        used_transactions.add(txn_id)
        save_used_txns()

        users_db[user_id]['wallet_balance'] += amount
        save_db()

        success_msg = (
            f"🎉 **ዲፖዚትዎ ተሳክቷል!**\n\n"
            f"🔖 **የትራንዛክሽን ቁጥር፦** `{txn_id}`\n"
            f"💵 **በአካውንትዎ ላይ የተጨመረ፦** {amount} ETB\n"
            f"💰 **አሁናዊ የዋሌት ሂሳብዎ፦** {users_db[user_id]['wallet_balance']} ETB\n\n"
            f"አሁን '🎟️ ቲኬት ቁረጥ' የሚለውን በመጫን መግዛት ይችላሉ!"
        )
        await update.message.reply_text(success_msg, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ **የትራንዛክሽን ቁጥር ማግኘት አልተቻለም!** እባክዎን ትክክለኛ የትራንዛክሽን ቁጥር ወይም ግልጽ ፎቶ ይላኩ፦")
        return DEPOSIT_PROOF

# -------------------------------------------------------------
# BUY TICKET FLOW & CHANNEL NOTIFICATION
# -------------------------------------------------------------
async def start_buy_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if not users_db.get(user_id, {}).get('phone'):
        await query.message.reply_text("⚠️ **እባክዎን አስቀድመው ስልክ ቁጥርዎን ያጋሩ!**", reply_markup=get_phone_keyboard())
        return ConversationHandler.END

    balance = users_db[user_id].get('wallet_balance', 0)
    if balance < TICKET_PRICE:
        msg = (
            f"❌ **በዋሌትዎ ላይ በቂ ገንዘብ የለም!**\n\n"
            f"የአንድ ቲኬት ዋጋ፦ **{TICKET_PRICE} ETB**\n"
            f"የእርስዎ የዋሌት ሂሳብ፦ **{balance} ETB**\n\n"
            f"እባክዎን አስቀድመው **'📥 ገንዘብ አስገባ (Deposit)'** የሚለውን ተጠቅመው አካውንትዎን ይሙሉ ።"
        )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())
        return ConversationHandler.END

    max_tickets = balance // TICKET_PRICE
    msg = (
        f"🎟️ **ቲኬት መቁረጫ**\n\n"
        f"የዋሌት ሂሳብዎ፦ **{balance} ETB**\n"
        f"መቁረጥ የሚችሉት ከፍተኛ የቲኬት ብዛት፦ **{max_tickets}**\n\n"
        f"እባክዎን መቁረጥ የሚፈልጉትን የቲኬት ብዛት በቁጥር ያስገቡ፦"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")
    return BUY_TICKET_QTY

async def process_buy_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if not text or not text.isdigit() or int(text) < 1:
        await update.message.reply_text("⚠️ እባክዎን ትክክለኛ የቲኬት ብዛት በቁጥር ያስገቡ፦")
        return BUY_TICKET_QTY

    qty = int(text)
    total_cost = qty * TICKET_PRICE
    balance = users_db[user_id].get('wallet_balance', 0)

    if total_cost > balance:
        await update.message.reply_text(f"❌ **ሂሳብዎ አይበቃም!** የ {qty} ቲኬት ዋጋ {total_cost} ETB ነው። የእርስዎ ሂሳብ {balance} ETB ነው።\nእባክዎን የቲኬቱን ብዛት ቀንስ አድርገው ያስገቡ፦")
        return BUY_TICKET_QTY

    users_db[user_id]['wallet_balance'] -= total_cost
    users_db[user_id]['tickets'] += qty

    referrer_id = users_db[user_id].get('referrer')

    if referrer_id and referrer_id in users_db:
        admin_share = qty * ADMIN_REFERRAL_SHARE
        ref_share = qty * REFERRAL_BONUS

        users_db[ADMIN_ID]['wallet_balance'] += admin_share
        users_db[referrer_id]['wallet_balance'] += ref_share
        users_db[referrer_id]['ref_balance'] += ref_share

        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"🎉 በእርስዎ ሊንክ የገባ ተጠቃሚ {qty} ቲኬት ስለቆረጠ **{ref_share} ETB** ኮሚሽን ወደ ዋሌትዎ ገቢ ሆኗል!"
            )
        except Exception as e:
            logging.warning(f"Failed ref notify: {e}")
    else:
        users_db[ADMIN_ID]['wallet_balance'] += total_cost

    total_issued = sum(len(u.get('ticket_numbers', [])) for u in users_db.values())
    new_tickets = [f"HD-{1000 + total_issued + i}" for i in range(1, qty + 1)]
    users_db[user_id].setdefault('ticket_numbers', []).extend(new_tickets)

    save_db()

    formatted_tickets = ", ".join([f"`{tn}`" for tn in new_tickets])
    msg = (
        f"🎉 **ቲኬት በስኬት ተቆርጧል!**\n\n"
        f"🎟️ **የተሰጡዎት የቲኬት ቁጥሮች፦** {formatted_tickets}\n"
        f"💸 **የተቀነሰ ገንዘብ፦** {total_cost} ETB\n"
        f"💰 **ቀሪ የዋሌት ሂሳብዎ፦** {users_db[user_id]['wallet_balance']} ETB\n\n"
        f"መልካም እድል!"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))

    try:
        channel_post = (
            f"🎉 **አዲስ የሎተሪ ቲኬት ተቆርጧል!** 🎟️\n\n"
            f"🔢 **የቲኬት ቁጥር፦** `{new_tickets[0]}`" + (f" (+{qty-1} ተጨማሪ)" if qty > 1 else "") + "\n"
            f"✨ መልካም እድል ለቲኬቱ ባለቤት!\n\n"
            f"እርስዎስ ዕድልዎን አልሞከሩም? አሁኑኑ ቲኬት ለመቁረጥ ከታች ያለውን ቦት ይጠቀሙ 👇\n"
            f"🤖 **ቦቱን ለመጀመር፦** @{context.bot.username}"
        )
        await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=channel_post, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to auto-post ticket to channel: {e}")

    return ConversationHandler.END

# -------------------------------------------------------------
# AUTOMATED SCHEDULED JOBS (POSTS & BACKUP)
# -------------------------------------------------------------
async def auto_channel_post_job(context: ContextTypes.DEFAULT_TYPE):
    """በየ 6 ሰዓቱ ወደ ቻናሉ አውቶማቲክ የሚላክ የማስተዋወቂያ መልእክት"""
    try:
        post_text = (
            f"🎟️ **እንኳን ወደ ህዳሴ ሎተሪ በደህና መጡ!** 🏆\n\n"
            f"የላቁ የላፕቶፕ ሽልማት የያዘውን ሎተሪያችንን ይቁረጡ!\n\n"
            f"💰 **የአንድ ቲኬት ዋጋ፦** {TICKET_PRICE} ETB ብቻ!\n"
            f"🎁 **የጋበዙትን ያግኙ፦** ጓደኞችዎን በመጋበዝ **{REFERRAL_BONUS} ETB** ኮሚሽን ያግኙ!\n\n"
            f"👉 **አሁኑኑ መጫወት ለመጀመር፦** @{context.bot.username}"
        )
        await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=post_text, parse_mode="Markdown")
        logging.info("Scheduled message posted to channel successfully.")
    except Exception as e:
        logging.error(f"Scheduled channel post error: {e}")

# 2. የመረጃ መጥፋትን ለመከላከል የሚሰራ የአውቶማቲክ ባክአፕ ተግባር
async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE):
    """በየ 1 ሰዓቱ የመረጃ ቋቱን ፋይል (Database) ለአድሚኑ በቴሌግራም የሚልክ"""
    try:
        if os.path.exists(DB_FILE):
            total_users = len(users_db)
            total_tickets = sum(len(u.get('ticket_numbers', [])) for u in users_db.values())
            
            caption = (
                f"📦 **የአውቶማቲክ ዳታቤዝ ባክአፕ (Backup)**\n\n"
                f"👥 አጠቃላይ ተጠቃሚዎች፦ **{total_users}**\n"
                f"🎟️ አጠቃላይ የተቆረጡ ቲኬቶች፦ **{total_tickets}**"
            )
            with open(DB_FILE, "rb") as doc:
                await context.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=doc,
                    caption=caption,
                    parse_mode="Markdown"
                )
            logging.info("Auto backup sent to Admin successfully.")
    except Exception as e:
        logging.error(f"Auto backup error: {e}")

# -------------------------------------------------------------
# WITHDRAWAL FLOW
# -------------------------------------------------------------
async def start_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    u = users_db.get(user_id, {})
    balance = u.get('wallet_balance', 0)
    ref_count = u.get('referred_count', 0)

    if ref_count < REQUIRED_REFERRALS:
        remaining = REQUIRED_REFERRALS - ref_count
        ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
        await query.edit_message_text(
            f"🔒 **ገንዘብ ማውጣት አይችሉም!**\n\n"
            f"ገንዘብ ማውጣትን አክቲቭ ለማድረግ ቢያንስ **{REQUIRED_REFERRALS} ሰዎችን** በሪፈራል ሊንክዎ መጋበዝ አለብዎት።\n\n"
            f"📊 **የእርስዎ የጋበዙት ሁኔታ፦**\n"
            f"• እስካሁን የጋበዟቸው፦ **{ref_count} ሰው**\n"
            f"• የሚቀሮት፦ **{remaining} ሰው**\n\n"
            f"🔗 **የእርስዎ የሪፈራል ሊንክ፦**\n`{ref_link}`\n\n"
            f"እባክዎን ሊንክዎን ለጓደኞችዎ በማጋራት {REQUIRED_REFERRALS} ሰው ያሙሉ።",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    min_required = MIN_WITHDRAW_AMOUNT + WITHDRAW_FEE

    if balance < min_required:
        await query.edit_message_text(
            f"❌ **በቂ የዋሌት ሂሳብ የለዎትም!**\n\n"
            f"📌 **የማውጣት ደንብ፦**\n"
            f"• ማውጣት የሚቻለው አነስተኛ መጠን፦ **{MIN_WITHDRAW_AMOUNT} ETB**\n"
            f"• የአገልግሎት ክፍያ፦ **{WITHDRAW_FEE} ETB**\n"
            f"• በአካውንትዎ ላይ ሊኖር የሚገባው አነስተኛ መጠን፦ **{min_required} ETB**\n\n"
            f"💰 የእርስዎ አሁናዊ ሂሳብ፦ **{balance} ETB**",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    msg = (
        f"📤 **ገንዘብ ማውጫ (Withdrawal)**\n\n"
        f"ያልወጣ የዋሌት ሂሳብዎ፦ **{balance} ETB**\n"
        f"💡 ማስታወሻ፦ ከ 500 ብር ጀምሮ ማውጣት የሚችሉ ሲሆን {WITHDRAW_FEE} ብር የአገልግሎት ክፍያ ይቆረጣል።\n\n"
        f"እባክዎን ማውጣት የሚፈልጉትን የብር መጠን ያስገቡ (ከ 500 ብር ጀምሮ)፦"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")
    return WITHDRAW_AMOUNT

async def withdraw_amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    balance = users_db[user_id].get('wallet_balance', 0)

    if not text or not text.isdigit():
        await update.message.reply_text("⚠️ እባክዎን ትክክለኛ ቁጥር ያስገቡ፦")
        return WITHDRAW_AMOUNT

    requested_amt = int(text)
    total_deduction = requested_amt + WITHDRAW_FEE

    if requested_amt < MIN_WITHDRAW_AMOUNT:
        await update.message.reply_text(f"⚠️ አነስተኛው ማውጣት የሚቻለው የብር መጠን **{MIN_WITHDRAW_AMOUNT} ETB** ነው። እባክዎን እንደገና ያስገቡ፦")
        return WITHDRAW_AMOUNT

    if total_deduction > balance:
        await update.message.reply_text(
            f"⚠️ **በቂ ሂሳብ የለም!**\n"
            f"የጠየቁት፦ {requested_amt} ETB\n"
            f"የአገልግሎት ክፍያ፦ {WITHDRAW_FEE} ETB\n"
            f"አጠቃላይ የሚቆረጠው፦ {total_deduction} ETB\n"
            f"የእርስዎ ሂሳብ፦ {balance} ETB\n\n"
            f"እባክዎን ዝቅ ያለ መጠን ያስገቡ፦"
        )
        return WITHDRAW_AMOUNT

    context.user_data['withdraw_amt'] = requested_amt
    context.user_data['total_deduction'] = total_deduction

    await update.message.reply_text(
        "💳 **የክፍያ መቀበያ መረጃዎን ያስገቡ፦**\n"
        "(ምሳሌ፦ Telebirr 0914112233 ወይም CBE 1000723732108 የተጠቃሚ ስም)"
    )
    return WITHDRAW_DETAILS

async def withdraw_details_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    details = update.message.text
    requested_amt = context.user_data['withdraw_amt']
    total_deduction = context.user_data['total_deduction']

    users_db[user_id]['wallet_balance'] -= total_deduction
    save_db()

    admin_msg = (
        f"🚨 **አዲስ የገንዘብ ማውጣት ጥያቄ!**\n\n"
        f"👤 ተጠቃሚ፦ {user.full_name} (`{user_id}`)\n"
        f"📞 ስልክ፦ `{users_db[user_id].get('phone')}`\n"
        f"👥 የተጋበዙ ሰዎች፦ **{users_db[user_id].get('referred_count', 0)}**\n"
        f"💵 ለተጠቃሚው የሚላከው መጠን፦ **{requested_amt} ETB**\n"
        f"🏷️ የተቆረጠ አገልግሎት ክፍያ፦ **{WITHDRAW_FEE} ETB**\n"
        f"💳 የክፍያ መረጃ፦ `{details}`\n\n"
        f"ክፍያውን ፈጽመው ለማረጋገጥ፦\n`/confirm_withdraw {user_id} {requested_amt}`"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")

    await update.message.reply_text(
        f"✅ **የገንዘብ ማውጣት ጥያቄዎ ተልኳል!**\n\n"
        f"💵 የሚላክሎት መጠን፦ **{requested_amt} ETB**\n"
        f"🏷️ የአገልግሎት ክፍያ፦ **{WITHDRAW_FEE} ETB**\n"
        f"💰 ቀሪ የዋሌት ሂሳብዎ፦ **{users_db[user_id]['wallet_balance']} ETB**\n\n"
        f"አድሚኑ ክፍያውን በቴሌብር/ባንክ ፈጽሞ በአጭር ጊዜ ውስጥ ይልክልዎታል።",
        reply_markup=get_main_menu_keyboard(user_id)
    )
    return ConversationHandler.END

# -------------------------------------------------------------
# WALLET TO WALLET TRANSFER FLOW
# -------------------------------------------------------------
async def start_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balance = users_db[user_id].get('wallet_balance', 0)

    if balance < (1 + TRANSFER_FEE):
        await query.edit_message_text(
            f"❌ **ገንዘብ ማስተላለፍ አይችሉም!**\n\nበዋሌትዎ ላይ በቂ ገንዘብ የለም። (የአገልግሎት ክፍያ {TRANSFER_FEE} ETB ይቆረጣል።)",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    msg = (
        f"🔄 **ከዋሌት ወደ ዋሌት ገንዘብ ማስተላለፊያ**\n\n"
        f"💰 የዋሌት ሂሳብዎ፦ **{balance} ETB**\n"
        f"💡 የአገልግሎት ክፍያ፦ **{TRANSFER_FEE} ETB** ይቆረጣል።\n\n"
        f"እባክዎን ገንዘቡ እንዲላክለት የሚፈልጉትን ሰው **Telegram ID (ቁጥር)** ያስገቡ፦\n"
        f"(ማስታወሻ፦ ተቀባዩ በቦቱ ላይ የተመዘገበ መሆን አለበት። ID ውን በ 'የኔ አካውንት' ውስጥ ማግኘት ይችላል)"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")
    return TRANSFER_RECIPIENT

async def transfer_recipient_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    sender_id = update.effective_user.id

    if not text or not text.isdigit():
        await update.message.reply_text("⚠️ እባክዎን ትክክለኛ የቴሌግራም ID (በቁጥር) ያስገቡ፦")
        return TRANSFER_RECIPIENT

    recipient_id = int(text)

    if recipient_id == sender_id:
        await update.message.reply_text("❌ ወደራስዎ አካውንት ገንዘብ ማስተላለፍ አይችሉም! እባክዎን የሌላ ሰው ID ያስገቡ፦")
        return TRANSFER_RECIPIENT

    if recipient_id not in users_db:
        await update.message.reply_text("❌ **ይህ ተጠቃሚ በቦቱ ላይ አልተመዘገበም!** እባክዎን ትክክለኛ ID ያስገቡ፦")
        return TRANSFER_RECIPIENT

    context.user_data['recipient_id'] = recipient_id
    recipient_name = users_db[recipient_id].get('full_name', 'ተጠቃሚ')

    await update.message.reply_text(
        f"👤 **ተቀባይ፦** {recipient_name} (`{recipient_id}`)\n\n"
        f"💵 እባክዎን ማስተላለፍ የሚፈልጉትን የብር መጠን ያስገቡ፦",
        parse_mode="Markdown"
    )
    return TRANSFER_AMOUNT

async def transfer_amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id
    text = update.message.text
    recipient_id = context.user_data['recipient_id']
    sender_balance = users_db[sender_id].get('wallet_balance', 0)

    if not text or not text.isdigit() or int(text) < 1:
        await update.message.reply_text("⚠️ እባክዎን ትክክለኛ የብር መጠን ያስገቡ፦")
        return TRANSFER_AMOUNT

    amount = int(text)
    total_deduction = amount + TRANSFER_FEE

    if total_deduction > sender_balance:
        await update.message.reply_text(
            f"❌ **በቂ ሂሳብ የለም!**\n"
            f"የሚላከው፦ {amount} ETB\n"
            f"የአገልግሎት ክፍያ፦ {TRANSFER_FEE} ETB\n"
            f"አጠቃላይ የሚቆረጠው፦ {total_deduction} ETB\n"
            f"የእርስዎ ሂሳብ፦ {sender_balance} ETB\n\n"
            f"እባክዎን ዝቅ ያለ መጠን ያስገቡ፦"
        )
        return TRANSFER_AMOUNT

    users_db[sender_id]['wallet_balance'] -= total_deduction
    users_db[recipient_id]['wallet_balance'] += amount
    users_db[ADMIN_ID]['wallet_balance'] += TRANSFER_FEE

    save_db()

    sender_name = update.effective_user.full_name
    try:
        await context.bot.send_message(
            chat_id=recipient_id,
            text=f"📲 **ገንዘብ ገቢ ሆኖልዎታል!**\n\nከ፦ {sender_name}\nየገቢ መጠን፦ **{amount} ETB**\nአሁናዊ የዋሌት ሂሳብዎ፦ **{users_db[recipient_id]['wallet_balance']} ETB**",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.warning(f"Failed to notify transfer recipient: {e}")

    await update.message.reply_text(
        f"✅ **ገንዘብ በስኬት ተላክቷል!**\n\n"
        f"👤 ተቀባይ፦ `{recipient_id}`\n"
        f"💵 የተላከው መጠን፦ **{amount} ETB**\n"
        f"🏷️ የአገልግሎት ክፍያ፦ **{TRANSFER_FEE} ETB**\n"
        f"💰 ቀሪ የዋሌት ሂሳብዎ፦ **{users_db[sender_id]['wallet_balance']} ETB**",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(sender_id)
    )
    return ConversationHandler.END

# -------------------------------------------------------------
# HELPER & ADMIN COMMANDS
# -------------------------------------------------------------
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    contact = update.message.contact
    if contact and contact.user_id == user_id:
        users_db[user_id]['phone'] = contact.phone_number
        save_db()
        await update.message.reply_text("✅ ስልክ ቁጥርዎ ተመዝግቧል!", reply_markup=get_main_menu_keyboard(user_id))

async def confirm_withdraw_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = int(context.args[0])
        amt = int(context.args[1])
        await context.bot.send_message(chat_id=target_id, text=f"🎉 **የ {amt} ETB የገንዘብ ማውጣት ጥያቄዎ ተፈጽሟል!**")
        await update.message.reply_text(f"✅ ክፍያ ለተጠቃሚ {target_id} መላኩ ተረጋገጠ።")
    except Exception as e:
        await update.message.reply_text("❌ አጠቃቀም፦ `/confirm_withdraw <USER_ID> <መጠን>`")

# አድሚኑ በማንኛውም ጊዜ ዳታቤዙን በዶክመንት እንዲቀበል የሚያስችል ትእዛዝ
async def manual_backup_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await auto_backup_job(context)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "show_prizes":
        p_text = "🏆 **የህዳሴ ሎተሪ የሽልማት እጣ፦**\n\n" + "\n".join(PRIZES)
        await query.edit_message_text(p_text, parse_mode="Markdown", reply_markup=get_back_keyboard())
    elif query.data == "get_referral":
        ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
        await query.edit_message_text(
            f"🔗 **የእርስዎ የሪፈራል ሊንክ፦**\n`{ref_link}`\n\n"
            f"• ሰዎች በእርስዎ ሊንክ ሲገቡ የተጋባዥ ቁጥርዎ ይጨምራል።\n"
            f"• **10 ሰው** ሲጋብዙ ገንዘብ ማውጫዎ አክቲቭ ይሆናል! 🔓\n"
            f"• በተጨማሪም ተጋባዦቹ ቲኬት ሲቆርጡ ለእያንዳንዱ ቲኬት **{REFERRAL_BONUS} ETB** ኮሚሽን ያገኛሉ!",
            parse_mode="Markdown",
            reply_markup=get_back_keyboard()
        )
    elif query.data == "main_menu":
        await query.edit_message_text("እንኳን ወደ **ህዳሴ ሎተሪ** በደህና መጡ! 🎟️", parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))

# -------------------------------------------------------------
# ERROR HANDLER
# -------------------------------------------------------------
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Exception while handling an update: {context.error}")

# -------------------------------------------------------------
# MAIN BOT EXECUTION
# -------------------------------------------------------------
def main():
    global telegram_app

    if not BOT_TOKEN:
        logging.error("No BOT_TOKEN found!")
        return

    server_thread = threading.Thread(target=run_web_server, daemon=True)
    server_thread.start()

    app = Application.builder().token(BOT_TOKEN).build()
    telegram_app = app

    job_queue = app.job_queue
    # በየ 6 ሰዓቱ (21600 ሰከንድ) አውቶማቲክ ቻናሉ ላይ እንዲፖስት ማድረግ
    job_queue.run_repeating(auto_channel_post_job, interval=21600, first=10)
    
    # በየ 1 ሰዓቱ (3600 ሰከንድ) አውቶማቲክ ባክአፕ ለአድሚኑ እንዲልክ ማድረግ
    job_queue.run_repeating(auto_backup_job, interval=3600, first=30)

    dep_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_deposit, pattern="^start_deposit$")],
        states={
            DEPOSIT_METHOD: [CallbackQueryHandler(deposit_method_selected, pattern="^(dep_cbe|dep_telebirr)$")],
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_entered)],
            DEPOSIT_PROOF: [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, deposit_proof_received)]
        },
        fallbacks=[CallbackQueryHandler(button_handler, pattern="^main_menu$")]
    )

    ticket_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_buy_ticket, pattern="^start_buy_ticket$")],
        states={BUY_TICKET_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_buy_ticket)]},
        fallbacks=[CallbackQueryHandler(button_handler, pattern="^main_menu$")]
    )

    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_withdraw, pattern="^start_withdraw$")],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_entered)],
            WITHDRAW_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_details_entered)]
        },
        fallbacks=[CallbackQueryHandler(button_handler, pattern="^main_menu$")]
    )

    transfer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_transfer, pattern="^start_transfer$")],
        states={
            TRANSFER_RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_recipient_entered)],
            TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_amount_entered)]
        },
        fallbacks=[CallbackQueryHandler(button_handler, pattern="^main_menu$")]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("backup", manual_backup_admin))
    app.add_handler(dep_conv)
    app.add_handler(ticket_conv)
    app.add_handler(withdraw_conv)
    app.add_handler(transfer_conv)
    
    app.add_handler(CallbackQueryHandler(show_account, pattern="^my_account$"))
    app.add_handler(CommandHandler("confirm_withdraw", confirm_withdraw_admin))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_error_handler(global_error_handler)

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

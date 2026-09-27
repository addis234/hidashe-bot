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
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, ConversationHandler, filters
)

# -------------------------------------------------------------
# CONFIGURATIONS
# -------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8833785126:AAEQgzZ8Wbg4t4-KDlcT1itp-E8DHbNw79M")
ADMIN_ID = 6722504980  # የአድሚን Telegram ID
CHANNEL_USERNAME = "@YourChannelUsername"  # የኦፊሴላዊ ቻናልህ Username

# TELEBIRR / CBE DETAILS
TELEBIRR_APP_ID = os.environ.get("TELEBIRR_APP_ID", "YOUR_APP_ID")
TELEBIRR_APP_KEY = os.environ.get("TELEBIRR_APP_KEY", "YOUR_APP_KEY")
TELEBIRR_SHORTCODE = os.environ.get("TELEBIRR_SHORTCODE", "YOUR_SHORTCODE")

TICKET_PRICE = 50       # የአንድ ቲኬት ዋጋ (ETB)
REFERRAL_BONUS = 10     # ደንበኛው ሰው ሲጋብዝ በሒሳብ መዝገብ የሚያዘው ቦነስ (ETB)
MIN_WITHDRAW_AMOUNT = 500
WITHDRAW_FEE = 10
TRANSFER_FEE = 1
REQUIRED_REFERRALS = 10

# የአካውንት መረጃዎች
MY_CBE_ACCOUNT_FULL = "1000723732108"
MY_CBE_ACCOUNT_END = "2108"
MY_CBE_NAME = "Addis Alemayehu"
MY_TELEBIRR_PHONE = "0981212774"
MY_TELEBIRR_NAME = "Addis"

PRIZES = [
    "🏆 የሎተሪው ዋና እጣ፦ Core i7 11th Generation Laptop 💻"
]

DB_FILE = "users_db.json"
USED_TXNS_FILE = "used_txns.json"
SYSTEM_SMS_FILE = "system_sms.json"  # ከ SMS Forwarder የሚመጡ መረጃዎች ማስቀመጫ

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
TRANSFER_RECIPIENT, TRANSFER_AMOUNT, TRANSFER_PIN = range(6, 9)
SET_PIN_STATE = range(9, 10)

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
                u.setdefault('pin', "1234")  # Default PIN
            return db
        except Exception as e:
            logging.error(f"Error loading DB: {e}")
            return {}
    return {}

def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(users_db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Error saving DB: {e}")

def load_json_file(file_path, default_val):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading {file_path}: {e}")
    return default_val

def save_json_file(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Error saving {file_path}: {e}")

users_db = load_db()
used_transactions = set(load_json_file(USED_TXNS_FILE, []))
system_sms_logs = load_json_file(SYSTEM_SMS_FILE, [])

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
            'referred_count': 0,
            'pin': "1234"
        }
        save_db()

ensure_admin_exists()

# -------------------------------------------------------------
# PAYMENT VALIDATION & SMS FORWARD MATCHING LOGIC
# -------------------------------------------------------------
def process_payment_input(text_content):
    # Regex በመጠቀም የትራንዛክሽን ID ማውጣት
    txn_match = re.search(r'\b(FT[A-Z0-9]{8,12}|[A-Z0-9]{10,14})\b', text_content, re.IGNORECASE)
    if not txn_match:
        return False, "❌ የትራንዛክሽን ቁጥር በምስሉ/በጽሁፉ ላይ ማግኘት አልተቻለም! እባክዎን በትክክል ይላኩ።", 0

    txn_id = txn_match.group(1).upper()

    # የብር መጠን መፈለግ
    amount_match = re.search(r"(?:transferred|paid|ETB)\s*([\d\.]+)", text_content, re.IGNORECASE)
    parsed_amount = float(amount_match.group(1)) if amount_match else 0

    # ከ ሰርቨር/SMS Forwarder ጋር ማመሳከር (ኦንላይን ሳይሆን በ GSM SMS የመጡ)
    matched = False
    if system_sms_logs:
        for sms in system_sms_logs:
            if txn_id in str(sms).upper():
                matched = True
                break
    else:
        # የ SMS logs ከሌሉ ቀጥታ ደረሰኙን መቀበል
        matched = True

    if not matched:
        return False, f"❌ የትራንዛክሽን ቁጥር `{txn_id}` በሰርቨሩ ማረጋገጫ ላይ አልተገኘም። እባክዎን ትንሽ ቆይተው እንደገና ይሞክሩ።", 0

    return True, txn_id, parsed_amount

# -------------------------------------------------------------
# FASTAPI WEB SERVER (SMS Forwarder Endpoint)
# -------------------------------------------------------------
web_app = FastAPI()

@web_app.get("/")
def health_check():
    return {"status": "ok", "message": "Hidasse Lottery Bot Server"}

@web_app.post("/sms/forward")
async def receive_forwarded_sms(request: Request):
    try:
        data = await request.json()
        sms_text = data.get("text", "") or data.get("message", "")
        if sms_text:
            system_sms_logs.append(sms_text)
            save_json_file(SYSTEM_SMS_FILE, system_sms_logs)
            logging.info(f"Forwarded SMS received: {sms_text}")
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Error receiving SMS forward: {e}")
        return {"status": "error"}

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(web_app, host="0.0.0.0", port=port, log_level="error")

# -------------------------------------------------------------
# KEYBOARDS
# -------------------------------------------------------------
def get_main_menu_keyboard(user_id):
    user = users_db.get(user_id, {})
    balance = user.get('wallet_balance', 0)
    ref_bal = user.get('ref_balance', 0)
    keyboard = [
        [InlineKeyboardButton(f"💳 የኔ አካውንት (Wallet: {balance} ETB | Ref: {ref_bal} ETB)", callback_data="my_account")],
        [InlineKeyboardButton("📥 ገንዘብ አስገባ (Deposit)", callback_data="start_deposit"), InlineKeyboardButton("📤 ገንዘብ አውጣ (Withdraw)", callback_data="start_withdraw")],
        [InlineKeyboardButton("🔄 ገንዘብ ላክ (Transfer)", callback_data="start_transfer"), InlineKeyboardButton("🎟️ ቲኬት ቁረጥ", callback_data="start_buy_ticket")],
        [InlineKeyboardButton("🎁 የሽልማት ዝርዝር", callback_data="show_prizes"), InlineKeyboardButton("👥 የሪፈራል ሊንክ", callback_data="get_referral")],
        [InlineKeyboardButton("🔑 PIN ቁጥር ቀይር", callback_data="set_pin")]
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
            'referred_count': 0,
            'pin': "1234"
        }

        # ሪፈራል ሲስተም፦ ሰው ሲጋበዝ በ ሒሳብ መዝገብ (Ref Balance) 10 ብር ማያያዝ
        if context.args and context.args[0].isdigit():
            ref_id = int(context.args[0])
            if ref_id != user_id and ref_id in users_db:
                users_db[user_id]['referrer'] = ref_id
                users_db[ref_id]['referred_count'] = users_db[ref_id].get('referred_count', 0) + 1
                users_db[ref_id]['ref_balance'] = users_db[ref_id].get('ref_balance', 0) + REFERRAL_BONUS
                save_db()

    welcome_text = (
        f"እንኳን ወደ **ህዳሴ ሎተሪ** በደህና መጡ! 🎟️\n\n"
        f"ለእርስዎ የተከፈተ የቦት አካውንት አልዎት።\n"
        f"💰 የቲኬት ዋጋ፦ **{TICKET_PRICE} ETB**\n"
        f"👥 የሪፈራል ቦነስ፦ **{REFERRAL_BONUS} ETB** (በእርስዎ ሊንክ ሰው ሲገባ በአካውንትዎ 'ያልዎት ሒሳብ' ላይ ይቀመጣል)\n"
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
        f"🎁 ያልዎት የሪፈራል ሒሳብ (Ref Balance)፦ **{u.get('ref_balance', 0)} ETB**\n"
        f"👥 የጋበዟቸው ሰዎች ብዛት፦ **{ref_count}**\n"
        f"🔓 ገንዘብ ማውጣት፦ **{withdraw_status}**\n"
        f"🎟️ የቆረጧቸው ቲኬቶች ብዛት፦ **{u.get('tickets', 0)}**\n"
        f"🔢 የቲኬት ቁጥሮችዎ፦ {tickets_str}\n"
        f"🔑 የሚስጥር ቁጥር (PIN)፦ `{u.get('pin', '1234')}`\n"
        f"📞 ስልክ ቁጥር፦ `{u.get('phone', 'የተመዘገበ የለም')}`"
    )
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())

# -------------------------------------------------------------
# SET PIN FLOW
# -------------------------------------------------------------
async def start_set_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔑 **አዲስ ባለ 4 አሃዝ የሚስጥር ቁጥር (PIN) ያስገቡ፦**")
    return SET_PIN_STATE

async def save_pin_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if not text or not text.isdigit() or len(text) != 4:
        await update.message.reply_text("⚠️ እባክዎን ትክክለኛ ባለ 4 አሃዝ ቁጥር ያስገቡ፦")
        return SET_PIN_STATE

    users_db[user_id]['pin'] = text
    save_db()
    await update.message.reply_text("✅ **የሚስጥር ቁጥርዎ በስኬት ተቀይሯል!**", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

# -------------------------------------------------------------
# DEPOSIT FLOW
# -------------------------------------------------------------
async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🏦 Commercial Bank (CBE)", callback_data="dep_cbe")],
        [InlineKeyboardButton("📲 Telebirr", callback_data="dep_telebirr")],
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
            f"📌 **የተመረጠው፦ Telebirr**\n"
            f"የቴሌብር ቁጥር፦ `{MY_TELEBIRR_PHONE}` ({MY_TELEBIRR_NAME})\n\n"
            f"💵 **ወደ አካውንትዎ ማስገባት የሚፈልጉትን የብር መጠን ያስገቡ፦**"
        )
    else:
        msg = (
            f"📌 **የተመረጠው፦ Commercial Bank of Ethiopia (CBE)**\n"
            f"የሂሳብ ቁጥር፦ `{MY_CBE_ACCOUNT_FULL}` ({MY_CBE_NAME})\n\n"
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

    acc_info = f"`{MY_TELEBIRR_PHONE}` ({MY_TELEBIRR_NAME})" if method == "Telebirr" else f"`{MY_CBE_ACCOUNT_FULL}` ({MY_CBE_NAME})"
    msg = (
        f"💰 **የሚያስገቡት መጠን፦ {amount} ETB**\n\n"
        f"እባክዎን ክፍያውን ወደዚህ ሂሳብ ይላኩ፦ {acc_info}\n\n"
        f"🔐 **ክፍያውን ከፈጸሙ በኋላ የወጣውን የትራንዛክሽን SMS በጽሁፍ ወይም የደረሰኙን የስክሪንሹት (Screenshot) ፎቶ ይላኩ፦**"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return DEPOSIT_PROOF

async def deposit_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expected_amount = context.user_data.get('dep_amount', 0)
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

    success, result_msg_or_tx, parsed_amount = process_payment_input(text_content)
    if not success:
        await update.message.reply_text(f"{result_msg_or_tx}\n\nእባክዎን ትክክለኛ የትራንዛክሽን ቁጥር ወይም ደረሰኝ እንደገና ይላኩ፦")
        return DEPOSIT_PROOF

    txn_id = result_msg_or_tx
    if txn_id in used_transactions:
        await update.message.reply_text(f"⚠️ **ይህ የትራንዛክሽን ቁጥር (`{txn_id}`) ቀደም ሲል ጥቅም ላይ ውሏል!**")
        return DEPOSIT_PROOF

    added_amount = parsed_amount if parsed_amount > 0 else expected_amount
    used_transactions.add(txn_id)
    save_json_file(USED_TXNS_FILE, list(used_transactions))

    users_db[user_id]['wallet_balance'] += added_amount
    save_db()

    success_msg = (
        f"🎉 **ዲፖዚትዎ ተሳክቷል!**\n\n"
        f"🔖 **የትራንዛክሽን ቁጥር፦** `{txn_id}`\n"
        f"💵 **በአካውንትዎ ላይ የተጨመረ፦** {added_amount} ETB\n"
        f"💰 **አሁናዊ የዋሌት ሂሳብዎ፦** {users_db[user_id]['wallet_balance']} ETB\n\n"
        f"አሁን '🎟️ ቲኬት ቁረጥ' የሚለውን በመጫን መግዛት ይችላሉ!"
    )
    await update.message.reply_text(success_msg, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

# -------------------------------------------------------------
# BUY TICKET FLOW & ADMIN NOTIFICATION (ነጥብ 1)
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

    max_tickets = int(balance // TICKET_PRICE)
    msg = (
        f"🎟️ **ቲኬት መቁረጫ**\n\n"
        f"የዋሌት ሂሳብዎ፦ **{balance} ETB**\n"
        f"መቁረጥ የሚችሉት ከፍተኛ የቲኬት ብዛት፦ **{max_tickets}**\n\n"
        f"እባክዎን መቁረጥ የሚፈልጉትን የቲኬት ብዛት በቁጥር ያስገቡ፦"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")
    return BUY_TICKET_QTY

async def process_buy_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
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

    # 📢 አድሚኑን ሙሉ መረጃ ማሳወቅ (የ ነጥብ 1 ማስተካከያ)
    try:
        admin_notif = (
            f"🚨 **አዲስ የቲኬት ግዢ ተፈፅሟል!**\n\n"
            f"👤 **ደንበኛ፦** {user.full_name} (@{user.username or 'የለም'})\n"
            f"🆔 **ID፦** `{user_id}`\n"
            f"📞 **ስልክ፦** `{users_db[user_id].get('phone', 'ያልተመዘገበ')}`\n"
            f"🎟️ **የተቆረጡ ቲኬቶች፦** {formatted_tickets}\n"
            f"💵 **የተከፈለው አጠቃላይ ብር፦** {total_cost} ETB"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_notif, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to notify admin: {e}")

    # 📢 በኦፊሴላዊ ቻናል ላይ ማስታወቅ
    try:
        channel_post = (
            f"🎉 **አዲስ የሎተሪ ቲኬት ተቆርጧል!** 🎟️\n\n"
            f"🔢 **የቲኬት ቁጥር፦** `{new_tickets[0]}`" + (f" (+{qty-1} ተጨማሪ)" if qty > 1 else "") + "\n"
            f"✨ መልካም እድል ለቲኬቱ ባለቤት!\n\n"
            f"🤖 **ቦቱን ለመጀመር፦** @{context.bot.username}"
        )
        await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=channel_post, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to auto-post ticket to channel: {e}")

    return ConversationHandler.END

# -------------------------------------------------------------
# WALLET TO WALLET TRANSFER FLOW WITH PIN (ነጥብ 2)
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
        f"እባክዎን ገንዘቡ እንዲላክለት የሚፈልጉትን ሰው **Telegram ID (ቁጥር)** ያስገቡ፦"
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
    sender_balance = users_db[sender_id].get('wallet_balance', 0)

    if not text or not text.isdigit() or int(text) < 1:
        await update.message.reply_text("⚠️ እባክዎን ትክክለኛ የብር መጠን ያስገቡ፦")
        return TRANSFER_AMOUNT

    amount = int(text)
    total_deduction = amount + TRANSFER_FEE

    if total_deduction > sender_balance:
        await update.message.reply_text(
            f"❌ **በቂ ሂሳብ የለም!**\n"
            f"የሚላከው፦ {amount} ETB | አገልግሎት፦ {TRANSFER_FEE} ETB | አጠቃላይ፦ {total_deduction} ETB\n"
            f"የእርስዎ ሂሳብ፦ {sender_balance} ETB\n\nእባክዎን ዝቅ ያለ መጠን ያስገቡ፦"
        )
        return TRANSFER_AMOUNT

    context.user_data['transfer_amount'] = amount
    context.user_data['total_deduction'] = total_deduction

    await update.message.reply_text("🔐 **ገንዘቡን ለማስተላለፍ ባለ 4 አሃዝ የሚስጥር ቁጥርዎን (PIN) ያስገቡ፦**")
    return TRANSFER_PIN

async def transfer_pin_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id
    input_pin = update.message.text
    saved_pin = users_db[sender_id].get('pin', '1234')

    if input_pin != saved_pin:
        await update.message.reply_text("❌ **የተሳሳተ የሚስጥር ቁጥር (PIN)!** እባክዎን እንደገና ይሞክሩ፦")
        return TRANSFER_PIN

    amount = context.user_data['transfer_amount']
    total_deduction = context.user_data['total_deduction']
    recipient_id = context.user_data['recipient_id']

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
# LOTTERY DRAW SYSTEM (ነጥብ 4)
# -------------------------------------------------------------
async def draw_lottery_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    all_tickets = []
    ticket_owner_map = {}

    for uid, udata in users_db.items():
        for t_num in udata.get('ticket_numbers', []):
            all_tickets.append(t_num)
            ticket_owner_map[t_num] = uid

    if not all_tickets:
        await update.message.reply_text("❌ ምንም የተሸጠ ቲኬት የለም!")
        return

    winning_ticket = random.choice(all_tickets)
    winner_id = ticket_owner_map[winning_ticket]
    winner_user = users_db[winner_id]

    announce_text = (
        f"🎉 **የህዳሴ ሎተሪ ዕጣ ወጥቷል!** 🏆\n\n"
        f"🎟️ **የአሸናፊው ቲኬት ቁጥር፦** `{winning_ticket}`\n"
        f"👤 **የአሸናፊው ስም፦** {winner_user.get('full_name', 'ተጠቃሚ')}\n"
        f"🎁 **የተበሰረው ሽልማት፦** Core i7 11th Generation Laptop 💻\n\n"
        f"እንኳን ደስ አለዎት! 🥳"
    )

    try:
        await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=announce_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to announce winner on channel: {e}")

    try:
        await context.bot.send_message(
            chat_id=winner_id,
            text=f"🥳 **እንኳን ደስ አለዎት!**\n\nየቆረጡት ቲኬት (`{winning_ticket}`) የዕጣው አሸናፊ ሆኗል! አድሚኑ በቅርብ ቀን ያገኝዎታል።",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Failed to notify winner directly: {e}")

    await update.message.reply_text(f"✅ ዕጣው በስኬት ወጥቷል! አሸናፊ፦ `{winning_ticket}` (User ID: {winner_id})")

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
            f"🔗 **የእርስዎ የሪፈራል ሊንክ፦**\n`{ref_link}`",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    min_required = MIN_WITHDRAW_AMOUNT + WITHDRAW_FEE
    if balance < min_required:
        await query.edit_message_text(
            f"❌ **በቂ የዋሌት ሂሳብ የለዎትም!**\n\nአነስተኛ ማውጣት የሚቻለው፦ **{MIN_WITHDRAW_AMOUNT} ETB** (+{WITHDRAW_FEE} ETB ክፍያ)\nየእርስዎ ሂሳብ፦ **{balance} ETB**",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    await query.edit_message_text(f"📤 **ማውጣት የሚፈልጉትን የብር መጠን ያስገቡ (ከ {MIN_WITHDRAW_AMOUNT} ETB ጀምሮ)፦**", parse_mode="Markdown")
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

    if requested_amt < MIN_WITHDRAW_AMOUNT or total_deduction > balance:
        await update.message.reply_text("⚠️ **የተሳሳተ መጠን ወይም በቂ ያልሆነ ሂሳብ!** እባክዎን እንደገና ያስገቡ፦")
        return WITHDRAW_AMOUNT

    context.user_data['withdraw_amt'] = requested_amt
    context.user_data['total_deduction'] = total_deduction
    await update.message.reply_text("💳 **የክፍያ መቀበያ መረጃዎን ያስገቡ (Telebirr/CBE ቁጥር እና ስም)፦**")
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
        f"💵 የሚላከው መጠን፦ **{requested_amt} ETB**\n"
        f"💳 የክፍያ መረጃ፦ `{details}`\n\n"
        f"ክፍያውን ፈጽመው ለማረጋገጥ፦ `/confirm_withdraw {user_id} {requested_amt}`"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
    await update.message.reply_text("✅ **የገንዘብ ማውጣት ጥያቄዎ ተልኳል!** በአጭር ጊዜ ውስጥ ገቢ ይደረጋል።", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

# -------------------------------------------------------------
# HELPER & BUTTON HANDLERS
# -------------------------------------------------------------
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    contact = update.message.contact
    if contact and contact.user_id == user_id:
        users_db[user_id]['phone'] = contact.phone_number
        save_db()
        await update.message.reply_text("✅ ስልክ ቁጥርዎ ተመዝግቧል!", reply_markup=get_main_menu_keyboard(user_id))

async def confirm_withdraw_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(context.args[0])
        amt = int(context.args[1])
        await context.bot.send_message(chat_id=target_id, text=f"🎉 **የ {amt} ETB የገንዘብ ማውጣት ጥያቄዎ ተፈጽሟል!**")
        await update.message.reply_text(f"✅ ክፍያ ለተጠቃሚ {target_id} መላኩ ተረጋገጠ።")
    except Exception:
        await update.message.reply_text("❌ አጠቃቀም፦ `/confirm_withdraw <USER_ID> <መጠን>`")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "show_prizes":
        await query.edit_message_text("🏆 **የህዳሴ ሎተሪ የሽልማት እጣ፦**\n\n" + "\n".join(PRIZES), parse_mode="Markdown", reply_markup=get_back_keyboard())
    elif query.data == "get_referral":
        ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
        await query.edit_message_text(
            f"🔗 **የእርስዎ የሪፈራል ሊንክ፦**\n`{ref_link}`\n\n"
            f"• ሰዎች በእርስዎ ሊንክ ሲገቡ በሒሳብ መዝገብዎ **{REFERRAL_BONUS} ETB** ይያዛል! 🔓",
            parse_mode="Markdown", reply_markup=get_back_keyboard()
        )
    elif query.data == "main_menu":
        await query.edit_message_text("እንኳን ወደ **ህዳሴ ሎተሪ** በደህና መጡ! 🎟️", parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))

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
            TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_amount_entered)],
            TRANSFER_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, transfer_pin_entered)]
        },
        fallbacks=[CallbackQueryHandler(button_handler, pattern="^main_menu$")]
    )

    set_pin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_set_pin, pattern="^set_pin$")],
        states={SET_PIN_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_pin_entered)]},
        fallbacks=[CallbackQueryHandler(button_handler, pattern="^main_menu$")]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("draw", draw_lottery_winner))  # የአድሚን እጣ ማውጫ command
    app.add_handler(CommandHandler("confirm_withdraw", confirm_withdraw_admin))
    app.add_handler(dep_conv)
    app.add_handler(ticket_conv)
    app.add_handler(withdraw_conv)
    app.add_handler(transfer_conv)
    app.add_handler(set_pin_conv)
    app.add_handler(CallbackQueryHandler(show_account, pattern="^my_account$"))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

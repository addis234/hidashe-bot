import os
import logging
import json
import re
import threading
import random
import string
import asyncio
from typing import Tuple

import uvicorn
from fastapi import FastAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)

# OCR በሰርቨሩ ላይ መኖር አለመኖሩን መፈተሽ
try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

# -------------------------------------------------------------
# CONFIGURATIONS & ENVIRONMENT VARIABLES
# -------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    logging.warning("BOT_TOKEN environment variable ውስጥ አልተዘጋጀም!")

ADMIN_ID = int(os.environ.get("ADMIN_ID", "6722504980"))
CHANNEL_USERNAME = "@hdase1221"

MY_CBE_NAME = "Addis Alemayehu"
MY_TELEBIRR_NAME = "Addis"

DB_FILE = "users_db.json"
USED_TXNS_FILE = "used_txns.json"

# CONVERSATION STATES
(
    SET_PIN,
    DEPOSIT_METHOD, DEPOSIT_AMOUNT, DEPOSIT_PHONE, DEPOSIT_REF_CODE, DEPOSIT_PROOF,
    TRANSFER_TARGET_ID, TRANSFER_AMOUNT, TRANSFER_PIN,
    WITHDRAW_METHOD, WITHDRAW_ACCOUNT_INFO, WITHDRAW_AMOUNT, WITHDRAW_PIN
) = range(13)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
db_lock = threading.Lock()

# -------------------------------------------------------------
# FASTAPI FOR RENDER HEALTH CHECK
# -------------------------------------------------------------
web_app = FastAPI()

@web_app.get("/")
def read_root():
    return {"status": "ok", "bot": "running"}

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
        [KeyboardButton("🎟 ትኬት ይቁረጡ"), KeyboardButton("💸 ገንዘብ ያውጡ")],
        [KeyboardButton("🔄 ገንዘብ ይላኩ"), KeyboardButton("🎁 የሽልማት ዝርዝር")],
        [KeyboardButton("💼 የኔ ዋሌት"), KeyboardButton("ወደ ቀድሞ ማውጫ ይመለሱ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# -------------------------------------------------------------
# VERIFICATION LOGIC
# -------------------------------------------------------------
def verify_receipt_text(text: str, expected_amount: int, method: str) -> Tuple[bool, str]:
    clean_text = text.lower()

    if "addis" not in clean_text:
        return False, "ገንዘቡን አላስገቡም እባክዎ ገንዘቡን ገቢ በማድረግ ትኬትዎን ይውሰዱ!"

    amount_str = f"{expected_amount:,}"
    amount_pattern = rf"\b({expected_amount}|{amount_str})(\.00)?\b"
    if not re.search(amount_pattern, text):
        return False, "ገንዘቡን አላስገቡም እባክዎ ገንዘቡን ገቢ በማድረግ ትኬትዎን ይውሰዱ!"

    txn_match = re.search(r'\b(FT[A-Za-z0-9]{8,10}|[A-Za-z0-9]{10,12})\b', text)
    if txn_match:
        txn_id = txn_match.group(1).upper()
        if txn_id in used_txns:
            return False, "❌ ይህ የትራንዛክሽን ቁጥር/ደረሰኝ ቀደም ብሎ ጥቅም ላይ ውሏል!"
        save_used_txn(txn_id)

    return True, "✅ ማረጋገጫው ተሳክቷል!"

# -------------------------------------------------------------
# COMMAND & MENU HANDLERS
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "ተጠቃሚ"
    
    # ትኬት ሳይቆርጥ የሪፈራል ኮድ አይሰጠውም (ref_code = None)
    if user_id not in users_db:
        users_db[user_id] = {
            'first_name': first_name,
            'wallet_balance': 0,
            'pin': None,
            'ref_code': None,
            'tickets': [],
            'referred_count': 0,
            'phone': None
        }
        save_db()
    else:
        users_db[user_id]['first_name'] = first_name
        save_db()

    await update.message.reply_text(
        "✨ **እንኳን ወደ ህዳሴ ዲጂታል ሎተሪ በደህና መጡ!** ✨\n\n"
        "የሎተሪ ትኬት በመቁረጥ የተለያዩ አጓጊ ሽልማቶችን ያሸንፉ!\n"
        "📺 የሎተሪ አወጣጥ ሂደቱ ግልጽ እና አጓጊ ሆኖ በቻናላችን ቀጥታ (Live) ይተላለፋል።",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

    if not users_db[user_id].get('pin'):
        await update.message.reply_text("🔒 እባክዎን ለአካውንትዎ አዲስ ባለ 4 አሃዝ የሚስጥር ቁጥር (PIN) ያስገቡ፦")
        return SET_PIN

    return ConversationHandler.END

async def set_pin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not (text.isdigit() and len(text) == 4):
        await update.message.reply_text("❌ የሚስጥር ቁጥር ባለ 4 አሃዝ ቁጥር መሆን አለበት (ምሳሌ፦ 1234)። እባክዎን እንደገና ያስገቡ፦")
        return SET_PIN

    users_db[user_id]['pin'] = text
    save_db()
    await update.message.reply_text("✅ የሚስጥር ቁጥርዎ በጥሩ ሁኔታ ተመዝግቧል!", reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def show_rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🎁 **የሽልማት ዝርዝር፦**\n\n"
        "1️⃣ **Core i7 11th Generation Laptop** 💻\n\n"
        "✨ ሌሎች አጓጊ ሽልማቶችን በ ሁለተኛ ዙር ይጠብቁን!"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return ConversationHandler.END

async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = users_db.get(user_id, {})
    balance = user_data.get('wallet_balance', 0)
    ref_code = user_data.get('ref_code')
    tickets = len(user_data.get('tickets', []))

    ref_display = f"`{ref_code}`" if ref_code else "⚠️ ትኬት ሲቆርጡ የሚሰጥዎት ይሆናል"

    msg = (
        f"💼 **የእርስዎ አካውንት መረጃ**\n\n"
        f"🆔 **የእርስዎ ID፦** `{user_id}`\n"
        f"💰 **የዋሌት መጠን፦** {balance} ETB\n"
        f"🎟 **የቆረጡት ትኬት ብዛት፦** {tickets}\n"
        f"🔗 **የእርስዎ ሪፈራል ኮድ፦** {ref_display}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return ConversationHandler.END

# -------------------------------------------------------------
# 🎟 TICKET BUYING (DEPOSIT) FLOW
# -------------------------------------------------------------
async def start_buy_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("CBE Birr / Bank", callback_data="dep_CBE")],
        [InlineKeyboardButton("Telebirr", callback_data="dep_Telebirr")]
    ]
    await update.message.reply_text("እባክዎን ክፍያ የሚፈጽሙበትን መንገድ ይምረጡ፦", reply_markup=InlineKeyboardMarkup(keyboard))
    return DEPOSIT_METHOD

async def deposit_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.replace("dep_", "")
    context.user_data['dep_method'] = method

    await query.edit_message_text(f"የመረጡት መንገድ፦ **{method}**\n\nእባክዎን ለትኬቱ የሚከፍሉትን የብር መጠን በቁጥር ብቻ ያስገቡ፦", parse_mode="Markdown")
    return DEPOSIT_AMOUNT

async def deposit_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ እባክዎን የብር መጠን በቁጥር ብቻ ያስገቡ፦")
        return DEPOSIT_AMOUNT

    context.user_data['dep_amount'] = int(text)
    await update.message.reply_text("📱 እባክዎን የስልክ ቁጥርዎን ያስገቡ፦")
    return DEPOSIT_PHONE

async def deposit_phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['dep_phone'] = update.message.text.strip()
    await update.message.reply_text("🔗 ከተጋበዙ የሪፈራል ኮድ ያስገቡ (ከሌለዎት **'skip'** ብለው ይጻፉ)፦")
    return DEPOSIT_REF_CODE

async def deposit_ref_code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data['dep_ref_code'] = None if text.lower() == 'skip' else text

    method = context.user_data.get('dep_method', 'CBE')
    amount = context.user_data.get('dep_amount', 0)
    acc_name = MY_CBE_NAME if method == "CBE" else MY_TELEBIRR_NAME

    await update.message.reply_text(
        f"💳 **የክፍያ መረጃ**\n\n"
        f"መጠን፦ **{amount} ETB**\n"
        f"የተቀባይ ስም፦ **{acc_name}**\n\n"
        f"እባክዎን ክፍያውን ፈጽመው የባንኩን/ቴሌብርን SMS ጽሁፍ ወይም ደረሰኝ (Photo) እዚህ ይላኩ፦",
        parse_mode="Markdown"
    )
    return DEPOSIT_PROOF

async def deposit_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expected_amount = context.user_data.get('dep_amount', 0)
    method = context.user_data.get('dep_method', 'CBE')
    phone = context.user_data.get('dep_phone')
    used_ref_code = context.user_data.get('dep_ref_code')

    extracted_text = ""

    if update.message.photo:
        if not OCR_AVAILABLE:
            await update.message.reply_text("⚠️ በምስል ማረጋገጥ በጊዜያዊነት አይሰራም። እባክዎን የባንክ ወይም የቴሌብር SMS ጽሁፉን ኮፒ አድርገው ይላኩ።")
            return DEPOSIT_PROOF

        await update.message.reply_text("🔍 ደረሰኝዎ በመመርመር ላይ ነው...")
        photo_file = await update.message.photo[-1].get_file()
        photo_path = f"temp_{user_id}.jpg"
        await photo_file.download_to_drive(photo_path)

        try:
            image = Image.open(photo_path)
            extracted_text = pytesseract.image_to_string(image)
        except Exception:
            await update.message.reply_text("⚠️ ደረሰኙን ማንበብ አልተቻለም። እባክዎን የትራንዛክሽን SMS ጽሁፉን ይላኩ።")
            if os.path.exists(photo_path):
                os.remove(photo_path)
            return DEPOSIT_PROOF

        if os.path.exists(photo_path):
            os.remove(photo_path)
    elif update.message.text:
        extracted_text = update.message.text

    is_valid, msg = verify_receipt_text(extracted_text, expected_amount, method)

    if not is_valid:
        await update.message.reply_text(msg)
        return DEPOSIT_PROOF

    ticket_no = generate_ticket_number()
    users_db[user_id]['wallet_balance'] += expected_amount
    users_db[user_id]['phone'] = phone
    users_db[user_id].setdefault('tickets', []).append(ticket_no)

    # ትኬት ሲቆርጥ የሪፈራል ኮድ ከሌለው አዲስ የሪፈራል ኮድ ይመደብለታል
    if not users_db[user_id].get('ref_code'):
        users_db[user_id]['ref_code'] = generate_ref_code(user_id)

    my_ref_code = users_db[user_id]['ref_code']

    ref_owner_id = None
    if used_ref_code:
        for uid, udata in users_db.items():
            if udata.get('ref_code') == used_ref_code and uid != user_id:
                ref_owner_id = uid
                users_db[uid]['wallet_balance'] += 10
                users_db[uid]['referred_count'] = users_db[uid].get('referred_count', 0) + 1
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"🎉 በሪፈራል ኮድዎ ሌላ ሰው ትኬት ስለቆረጠ **10 ETB** ኮሚሽን ወደ ዋሌትዎ ገቢ ሆኗል!"
                    )
                except Exception:
                    pass
                break

    save_db()

    await update.message.reply_text(
        f"🎉 **ክፍያዎ ተረጋግጦ ትኬትዎ ተቆርጧል!**\n\n"
        f"🎟 **የእጣ ቁጥር፦** `{ticket_no}`\n"
        f"🔗 **የእርስዎ አዲሱ ሪፈራል ኮድ፦** `{my_ref_code}`\n\n"
        f"✨ **መልካም እድል!**",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

    try:
        admin_msg = (
            f"📥 **አዲስ ትኬት ተቆርጧል!**\n\n"
            f"👤 ተጠቃሚ ID፦ `{user_id}`\n"
            f"📱 ስልክ፦ {phone}\n"
            f"💵 የተከፈለ መጠን፦ {expected_amount} ETB\n"
            f"🎟 የእጣ ቁጥር፦ `{ticket_no}`"
        )
        if ref_owner_id:
            admin_msg += f"\n🎁 ሪፈራል የተጠቀመው ከ፦ `{ref_owner_id}` (10 ETB ተከፍሏል)"

        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Admin Notify Error: {e}")

    return ConversationHandler.END

# -------------------------------------------------------------
# 🔄 P2P TRANSFER FLOW
# -------------------------------------------------------------
async def start_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 እባክዎን ገንዘብ የሚልኩለትን ሰው **የቴሌግራም ID** ያስገቡ፦")
    return TRANSFER_TARGET_ID

async def transfer_target_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ የቴሌግራም ID ቁጥር ብቻ መሆን አለበት። እባክዎን እንደገና ያስገቡ፦")
        return TRANSFER_TARGET_ID

    target_id = int(text)
    if target_id not in users_db:
        await update.message.reply_text("❌ ይህ ተጠቃሚ በቦቱ ውስጥ አልተገኘም። እባክዎን IDውን አረጋግጠው እንደገና ያስገቡ፦")
        return TRANSFER_TARGET_ID

    if target_id == update.effective_user.id:
        await update.message.reply_text("❌ ወደራስዎ አካውንት ማስተላለፍ አይችሉም! እባክዎን የሌላ ሰው ID ያስገቡ፦")
        return TRANSFER_TARGET_ID

    context.user_data['transfer_target'] = target_id
    await update.message.reply_text("💵 ማስተላለፍ የሚፈልጉትን የብር መጠን ያስገቡ፦")
    return TRANSFER_AMOUNT

async def transfer_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ እባክዎን የብር መጠን በቁጥር ብቻ ያስገቡ፦")
        return TRANSFER_AMOUNT

    amount = int(text)
    user_id = update.effective_user.id
    current_bal = users_db[user_id].get('wallet_balance', 0)

    if amount > current_bal:
        await update.message.reply_text(f"❌ በቂ የዋሌት ባላንስ የለዎትም። አሁን ያሎት ባላንስ {current_bal} ETB ነው። እንደገና ያስገቡ፦")
        return TRANSFER_AMOUNT

    context.user_data['transfer_amount'] = amount
    await update.message.reply_text("🔒 ሂደቱን ለማረጋገጥ የሚስጥር ቁጥርዎን (PIN) ያስገቡ፦")
    return TRANSFER_PIN

async def transfer_pin_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    correct_pin = users_db[user_id].get('pin')

    if text != correct_pin:
        await update.message.reply_text("ሚስጥር ቁጥርዎን እንደገና አስተካክለው በማስገባት ይሞክሩ፦")
        return TRANSFER_PIN

    target_id = context.user_data['transfer_target']
    amount = context.user_data['transfer_amount']

    users_db[user_id]['wallet_balance'] -= amount
    users_db[target_id]['wallet_balance'] += amount
    save_db()

    await update.message.reply_text(
        f"✅ **ገንዘብ በትክክል ተላክቷል!**\n\n"
        f"💸 የተላከው መጠን፦ {amount} ETB\n"
        f"👤 የተቀባይ ID፦ `{target_id}`\n"
        f"💰 ቀሪ ባላንስዎ፦ {users_db[user_id]['wallet_balance']} ETB",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎉 **ገንዘብ ገቢ ሆኖልዎታል!**\n\n"
                 f"📥 የተላከዉ መጠን፦ {amount} ETB\n"
                 f"👤 የላኪ ID፦ `{user_id}`\n"
                 f"💰 አጠቃላይ ባላንስዎ፦ {users_db[target_id]['wallet_balance']} ETB",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    return ConversationHandler.END

# -------------------------------------------------------------
# 💸 WITHDRAWAL FLOW
# -------------------------------------------------------------
async def start_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("ንግድ ባንክ (CBE)", callback_data="with_CBE")],
        [InlineKeyboardButton("ቴሌብር (Telebirr)", callback_data="with_Telebirr")]
    ]
    await update.message.reply_text("ገንዘብ ማውጣት የሚፈልጉበትን መንገድ ይምረጡ፦", reply_markup=InlineKeyboardMarkup(keyboard))
    return WITHDRAW_METHOD

async def withdraw_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.replace("with_", "")
    context.user_data['withdraw_method'] = method

    await query.edit_message_text(f"የመረጡት መንገድ፦ **{method}**\n\nእባክዎን **የአካውንት ቁጥር** እና **የአካውንቱን ባለቤት ሙሉ ስም** ያስገቡ፦", parse_mode="Markdown")
    return WITHDRAW_ACCOUNT_INFO

async def withdraw_account_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['withdraw_acc_info'] = update.message.text.strip()
    await update.message.reply_text("💵 ማውጣት የሚፈልጉትን የብር መጠን ያስገቡ፦")
    return WITHDRAW_AMOUNT

async def withdraw_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ እባክዎን የብር መጠን በቁጥር ብቻ ያስገቡ፦")
        return WITHDRAW_AMOUNT

    amount = int(text)
    user_id = update.effective_user.id
    current_bal = users_db[user_id].get('wallet_balance', 0)

    if amount > current_bal:
        await update.message.reply_text(f"❌ በቂ ባላንስ የለዎትም። ያሎት ባላንስ {current_bal} ETB ነው። እንደገና ያስገቡ፦")
        return WITHDRAW_AMOUNT

    context.user_data['withdraw_amount'] = amount
    await update.message.reply_text("🔒 ሂደቱን ለማረጋገጥ የሚስጥር ቁጥርዎን (PIN) ያስገቡ፦")
    return WITHDRAW_PIN

async def withdraw_pin_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    correct_pin = users_db[user_id].get('pin')

    if text != correct_pin:
        await update.message.reply_text("ሚስጥር ቁጥርዎን እንደገና አስተካክለው በማስገባት ይሞክሩ፦")
        return WITHDRAW_PIN

    amount = context.user_data['withdraw_amount']
    method = context.user_data['withdraw_method']
    acc_info = context.user_data['withdraw_acc_info']

    users_db[user_id]['wallet_balance'] -= amount
    save_db()

    remaining_bal = users_db[user_id]['wallet_balance']

    await update.message.reply_text(
        f"✅ **የገንዘብ ማውጣት ጥያቄዎ ለአድሚን ተልኳል!**\n\n"
        f"💸 የተጠየቀው መጠን፦ {amount} ETB\n"
        f"🏦 መንገድ፦ {method}\n"
        f"💰 በዋሌትዎ የቀረ ብር፦ {remaining_bal} ETB",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

    try:
        admin_msg = (
            f"⚠️ **አዲስ የገንዘብ ማውጣት ጥያቄ!**\n\n"
            f"👤 ተጠቃሚ ID፦ `{user_id}`\n"
            f"💵 መጠን፦ **{amount} ETB**\n"
            f"🏦 መንገድ፦ {method}\n"
            f"📋 የአካውንት መረጃ፦ {acc_info}\n"
            f"💰 የተጠቃሚው ቀሪ ባላንስ፦ {remaining_bal} ETB"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Withdraw Admin Notify Error: {e}")

    return ConversationHandler.END

# -------------------------------------------------------------
# 📢 የCHANNEL 3 ሰዓት አውቶማቲክ ማስታወቂያ
# -------------------------------------------------------------
async def post_channel_updates(context: ContextTypes.DEFAULT_TYPE):
    if not users_db:
        return

    top_referrers = []
    ticket_buyers = []

    for uid, udata in users_db.items():
        name = udata.get('first_name', 'ተጠቃሚ')
        ref_cnt = udata.get('referred_count', 0)
        earned = ref_cnt * 10
        if ref_cnt > 0:
            top_referrers.append(f"• **{name}** ➡️ {ref_cnt} ሰው ያስቆረጠ ({earned} ETB የሰራ)")

        t_count = len(udata.get('tickets', []))
        if t_count > 0:
            ticket_buyers.append(f"• **{name}** (የቲኬት ብዛት፦ {t_count})")

    msg = "📢 **የህዳሴ ዲጂታል ሎተሪ ወቅታዊ መረጃ!**\n\n"

    if top_referrers:
        msg += "🔥 **በሪፈራል ብዙ የሰሩ ተጠቃሚዎች፦**\n"
        msg += "\n".join(top_referrers[:5]) + "\n\n"

    if ticket_buyers:
        msg += "🎟 **ትኬት የወጣላቸው ተጠቃሚዎች ስም ዝርዝር፦**\n"
        msg += "\n".join(ticket_buyers[:10]) + "\n\n"

    msg += (
        "💡 እርስዎም ትኬት በመቁረጥ የሪፈራል ኮድዎን በማጋራት በ 1 ሰው 10 ETB መስራት ይችላሉ!\n"
        "📺 የሎተሪ አወጣጥ ሂደቱ በቅርቡ በቻናላችን ላይቭ (Live) ይተላለፋል!"
    )

    try:
        await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Channel Broadcast Error: {e}")

# -------------------------------------------------------------
# 📊 ADMIN STATS
# -------------------------------------------------------------
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    total_tickets = 0
    total_users = len(users_db)

    for uid, udata in users_db.items():
        tickets = udata.get('tickets', [])
        total_tickets += len(tickets)

    msg = (
        f"📊 **የሲስተም አጠቃላይ መረጃ**\n\n"
        f"👥 አጠቃላይ ተጠቃሚዎች፦ {total_users}\n"
        f"🎟 የተቆረጡ ትኬቶች ብዛት፦ {total_tickets}\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ወደ ዋና ማውጫ ተመልሰዋል፦", reply_markup=get_main_keyboard())
    return ConversationHandler.END

# -------------------------------------------------------------
# MAIN APP SETUP
# -------------------------------------------------------------
def main():
    server_thread = threading.Thread(target=run_web_server, daemon=True)
    server_thread.start()

    if not BOT_TOKEN:
        logging.error("BOT_TOKEN አልተዘጋጀም! እባክዎን በ Render Environment Variables ውስጥ ያስገቡ።")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    if app.job_queue:
        app.job_queue.run_repeating(post_channel_updates, interval=10800, first=10)

    menu_button_filter = filters.Regex("^(🎟 ትኬት ይቁረጡ|💸 ገንዘብ ያውጡ|🔄 ገንዘብ ይላኩ|🎁 የሽልማት ዝርዝር|💼 የኔ ዋሌት|ወደ ቀድሞ ማውጫ ይመለሱ)$")

    pin_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SET_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, set_pin_handler)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(menu_button_filter, cancel)
        ],
        per_user=True
    )

    ticket_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎟 ትኬት ይቁረጡ$"), start_buy_ticket)],
        states={
            DEPOSIT_METHOD: [CallbackQueryHandler(deposit_method_selected, pattern="^dep_")],
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, deposit_amount_received)],
            DEPOSIT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, deposit_phone_received)],
            DEPOSIT_REF_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, deposit_ref_code_received)],
            DEPOSIT_PROOF: [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND & ~menu_button_filter, deposit_proof_received)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(menu_button_filter, cancel)
        ],
        per_user=True
    )

    transfer_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔄 ገንዘብ ይላኩ$"), start_transfer)],
        states={
            TRANSFER_TARGET_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, transfer_target_received)],
            TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, transfer_amount_received)],
            TRANSFER_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, transfer_pin_received)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(menu_button_filter, cancel)
        ],
        per_user=True
    )

    withdraw_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 ገንዘብ ያውጡ$"), start_withdraw)],
        states={
            WITHDRAW_METHOD: [CallbackQueryHandler(withdraw_method_selected, pattern="^with_")],
            WITHDRAW_ACCOUNT_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, withdraw_account_received)],
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, withdraw_amount_received)],
            WITHDRAW_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, withdraw_pin_received)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(menu_button_filter, cancel)
        ],
        per_user=True
    )

    app.add_handler(pin_conv)
    app.add_handler(ticket_conv)
    app.add_handler(transfer_conv)
    app.add_handler(withdraw_conv)

    app.add_handler(MessageHandler(filters.Regex("^🎁 የሽልማት ዝርዝር$"), show_rewards))
    app.add_handler(MessageHandler(filters.Regex("^💼 የኔ ዋሌት$"), show_wallet))
    app.add_handler(MessageHandler(filters.Regex("^(ወደ ቀድሞ ማውጫ ይመለሱ|/start)$"), start))
    app.add_handler(CommandHandler("stats", admin_stats))

    logging.info("ቦቱ መስራት ጀምሯል...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

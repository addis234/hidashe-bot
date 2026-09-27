import os
import logging
import json
import random
import re
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
ADMIN_ID = 6722504980
CHANNEL_USERNAME = "@YourChannelUsername"

TICKET_PRICE = 50
REFERRAL_BONUS = 10
MIN_WITHDRAW_AMOUNT = 500
WITHDRAW_FEE = 10
TRANSFER_FEE = 1
REQUIRED_REFERRALS = 10

MY_CBE_ACCOUNT_FULL = "1000723732108"
MY_CBE_NAME = "Addis Alemayehu"
MY_TELEBIRR_PHONE = "0981212774"
MY_TELEBIRR_NAME = "Addis"

PRIZES = ["🏆 የሎተሪው ዋና እጣ፦ Core i7 11th Generation Laptop 💻"]

DB_FILE = "users_db.json"
USED_TXNS_FILE = "used_txns.json"
SYSTEM_SMS_FILE = "system_sms.json"

# CONVERSATION STATES
DEPOSIT_METHOD, DEPOSIT_AMOUNT, DEPOSIT_PROOF = range(3)
WITHDRAW_AMOUNT, WITHDRAW_DETAILS = range(3, 5)
BUY_TICKET_QTY = range(5, 6)
TRANSFER_RECIPIENT, TRANSFER_AMOUNT, TRANSFER_PIN = range(6, 9)
SET_PIN_STATE = range(9, 10)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

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
                u.setdefault('pin', "1234")
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

users_db = load_db()

def ensure_admin_exists():
    if ADMIN_ID not in users_db:
        users_db[ADMIN_ID] = {
            'wallet_balance': 0, 'ref_balance': 0, 'tickets': 0, 'referrer': None,
            'username': "Admin", 'full_name': "System Admin", 'phone': None,
            'ticket_numbers': [], 'referred_count': 0, 'pin': "1234"
        }
        save_db()

ensure_admin_exists()

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

# -------------------------------------------------------------
# CANCEL / FALLBACK HANDLER
# -------------------------------------------------------------
async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
        await query.edit_message_text("ለወጡበት ተግባር ሰርዘዋል። ወደ ዋናው ማውጫ ተመልሰዋል፦", reply_markup=get_main_menu_keyboard(user_id))
    else:
        user_id = update.effective_user.id
        await update.message.reply_text("ወደ ዋናው ማውጫ ተመልሰዋል፦", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

# -------------------------------------------------------------
# DEPOSIT HANDLERS
# -------------------------------------------------------------
async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🏦 Commercial Bank (CBE)", callback_data="dep_cbe")],
        [InlineKeyboardButton("📲 Telebirr", callback_data="dep_telebirr")],
        [InlineKeyboardButton("❌ ሰርዝ", callback_data="cancel_action")]
    ]
    await query.edit_message_text("📥 **ገንዘብ ማስገቢያ መንገድ ይምረጡ፦**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return DEPOSIT_METHOD

async def deposit_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = "CBE" if query.data == "dep_cbe" else "Telebirr"
    context.user_data['dep_method'] = method

    if method == "Telebirr":
        msg = f"📌 **የተመረጠው፦ Telebirr**\nየቴሌብር ቁጥር፦ `{MY_TELEBIRR_PHONE}` ({MY_TELEBIRR_NAME})\n\n💵 **ወደ አካውንትዎ ማስገባት የሚፈልጉትን የብር መጠን ያስገቡ፦**"
    else:
        msg = f"📌 **የተመረጠው፦ CBE**\nየሂሳብ ቁጥር፦ `{MY_CBE_ACCOUNT_FULL}` ({MY_CBE_NAME})\n\n💵 **ወደ አካውንትዎ ማስገባት የሚፈልጉትን የብር መጠን ያስገቡ፦**"
    
    await query.edit_message_text(msg, parse_mode="Markdown")
    return DEPOSIT_AMOUNT

async def deposit_amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or not text.isdigit() or int(text) < 10:
        await update.message.reply_text("⚠️ እባክዎን ትክክለኛ የብር መጠን ያስገቡ (ቢያንስ 10 ETB)፦")
        return DEPOSIT_AMOUNT
    
    amount = int(text)
    context.user_data['dep_amount'] = amount
    method = context.user_data.get('dep_method', 'Telebirr')

    acc_info = f"`{MY_TELEBIRR_PHONE}` ({MY_TELEBIRR_NAME})" if method == "Telebirr" else f"`{MY_CBE_ACCOUNT_FULL}` ({MY_CBE_NAME})"
    msg = (
        f"💰 **የሚያስገቡት መጠን፦ {amount} ETB**\n\n"
        f"እባክዎን ክፍያውን ወደዚህ ሂሳብ ይላኩ፦ {acc_info}\n\n"
        f"🔐 **ክፍያውን ከፈጸሙ በኋላ የወጣውን የትራንዛክሽን ቁጥር/SMS በጽሁፍ ወይም የደረሰኙን photo ይላኩ፦**"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return DEPOSIT_PROOF

async def deposit_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expected_amount = context.user_data.get('dep_amount', 0)
    
    users_db[user_id]['wallet_balance'] += expected_amount
    save_db()

    msg = (
        f"🎉 **ዲፖዚትዎ ተሳክቷል!**\n\n"
        f"💵 **የተጨመረበት ሂሳብ፦** {expected_amount} ETB\n"
        f"💰 **አጠቃላይ የዋሌት ሂሳብዎ፦** {users_db[user_id]['wallet_balance']} ETB"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

# -------------------------------------------------------------
# PIN HANDLERS
# -------------------------------------------------------------
async def start_set_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔑 **አዲስ ባለ 4 አሃዝ የሚስጥር ቁጥር (PIN) ያስገቡ፦**", parse_mode="Markdown")
    return SET_PIN_STATE

async def save_pin_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if not text or not text.isdigit() or len(text) != 4:
        await update.message.reply_text("⚠️ እባክዎን ትክክለኛ ባለ 4 አሃዝ ቁጥር ያስገቡ፦")
        return SET_PIN_STATE

    users_db[user_id]['pin'] = text
    save_db()
    await update.message.reply_text("✅ **የሚስጥር ቁጥርዎ (PIN) በስኬት ተቀይሯል!**", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

# -------------------------------------------------------------
# START & COMMANDS
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    ensure_admin_exists()

    if user_id not in users_db:
        users_db[user_id] = {
            'wallet_balance': 0, 'ref_balance': 0, 'tickets': 0, 'referrer': None,
            'username': user.username or "", 'full_name': user.full_name or "", 'phone': None,
            'ticket_numbers': [], 'referred_count': 0, 'pin': "1234"
        }
        save_db()

    welcome_text = "እንኳን ወደ **ህዳሴ ሎተሪ** በደህና መጡ! 🎟️\n\nእባክዎን ከታች ካሉት አማራጮች ይመረጡ፦"
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "my_account":
        u = users_db.get(user_id, {})
        msg = f"👤 **የእርስዎ አካውንት**\n\n🆔 ID: `{user_id}`\n💵 Wallet: **{u.get('wallet_balance', 0)} ETB**\n🔑 PIN: `{u.get('pin', '1234')}`"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())
    elif query.data == "main_menu":
        await query.edit_message_text("እንኳን ወደ **ህዳሴ ሎተሪ** በደህና መጡ! 🎟️", parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))

# -------------------------------------------------------------
# MAIN APP setup
# -------------------------------------------------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # 1. Deposit Conversation Handler
    dep_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_deposit, pattern="^start_deposit$")],
        states={
            DEPOSIT_METHOD: [CallbackQueryHandler(deposit_method_selected, pattern="^(dep_cbe|dep_telebirr)$")],
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_entered)],
            DEPOSIT_PROOF: [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, deposit_proof_received)]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_handler, pattern="^(cancel_action|main_menu)$"),
            CommandHandler("start", start)
        ],
        per_user=True
    )

    # 2. PIN Conversation Handler
    pin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_set_pin, pattern="^set_pin$")],
        states={
            SET_PIN_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_pin_entered)]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_handler, pattern="^(cancel_action|main_menu)$"),
            CommandHandler("start", start)
        ],
        per_user=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(dep_conv)
    app.add_handler(pin_conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

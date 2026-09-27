import os
import logging
import json
import re
import asyncio
import threading
from PIL import Image
import pytesseract

import uvicorn
from fastapi import FastAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)

# -------------------------------------------------------------
# CONFIGURATIONS
# -------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("CRITICAL ERROR: 'BOT_TOKEN' environment variable is not set.")

ADMIN_ID = int(os.environ.get("ADMIN_ID", "6722504980"))

# የባንክ እና የቴሌብር የተቀባይ ስሞች (ለመፈተሽ የሚያገለግሉ)
MY_CBE_NAME = "Addis Alemayehu"
MY_TELEBIRR_NAME = "Addis"

DB_FILE = "users_db.json"
USED_TXNS_FILE = "used_txns.json"

DEPOSIT_METHOD, DEPOSIT_AMOUNT, DEPOSIT_PROOF = range(3)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
db_lock = threading.Lock()

# -------------------------------------------------------------
# USED TRANSACTIONS DB (ተደጋጋሚ ደረሰኝ ለመከላከል)
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

# -------------------------------------------------------------
# DATABASE FUNCTIONS
# -------------------------------------------------------------
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

# -------------------------------------------------------------
# OCR & TEXT VERIFICATION LOGIC (አውቶማቲክ ማረጋገጫ)
# -------------------------------------------------------------
def verify_receipt_text(text: str, expected_amount: int, method: str) -> tuple[bool, str]:
    """
    ደረሰኙን አምቦ የተቀባይ ስም፣ የብር መጠን እና የትራንዛክሽን ቁጥር ያረጋግጣል
    """
    clean_text = text.lower()

    # 1. የተቀባይ ስም ማረጋገጥ (Receiver Name Check)
    expected_name = MY_CBE_NAME.lower() if method == "CBE" else MY_TELEBIRR_NAME.lower()
    
    # "addis alemayehu" ወይም "addis" በፅሁፉ/በምስሉ ውስጥ መኖር አለበት
    if "addis" not in clean_text:
        return False, f"❌ በደረሰኙ ላይ የተቀባይ ስም ({MY_CBE_NAME} / {MY_TELEBIRR_NAME}) አልተገኘም።"

    # 2. የብር መጠን ማረጋገጥ (Amount Check)
    # በጽሁፉ ውስጥ የተጠየቀው የብር መጠን መኖሩን መፈለግ
    amount_pattern = rf"\b{expected_amount}(\.00)?\b"
    if not re.search(amount_pattern, text):
        return False, f"❌ በደረሰኙ ላይ የተገለጸው የብር መጠን ከጠየቁት ({expected_amount} ETB) ጋር አይጣጣምም።"

    # 3. የትራንዛክሽን ቁጥር መፈለግና መደጋገሙን ማረጋገጥ (Txn ID Check)
    # የቴሌብር ወይም CBE የትራንዛክሽን ቁጥሮችን በRegex መፈለግ (ምሳሌ፦ DIR16I1C7R, FT2309...)
    txn_match = re.search(r'\b([A-Za-z0-9]{8,12})\b', text)
    if txn_match:
        txn_id = txn_match.group(1).upper()
        if txn_id in used_txns:
            return False, "❌ ይህ የትራንዛክሽን ቁጥር/ደረሰኝ ቀደም ብሎ ጥቅም ላይ ውሏል!"
        
        # አዲስ ከሆነ የትራንዛክሽን ቁጥሩን መዝግቦ መያዝ
        save_used_txn(txn_id)

    return True, "✅ ማረጋገጫው ተሳክቷል!"

# -------------------------------------------------------------
# DEPOSIT PROOF HANDLER
# -------------------------------------------------------------
async def deposit_proof_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expected_amount = context.user_data.get('dep_amount', 0)
    method = context.user_data.get('dep_method', 'CBE')

    extracted_text = ""

    # ሀ. ተጠቃሚው የላከው የደረሰኝ PHOTO ከሆነ በOCR ማንበብ
    if update.message.photo:
        await update.message.reply_text("🔍 ደረሰኝዎ በመመርመር ላይ ነው... እባክዎን ትንሽ ይታገሱ።")
        
        photo_file = await update.message.photo[-1].get_file()
        photo_path = f"temp_{user_id}.jpg"
        await photo_file.download_to_drive(photo_path)

        try:
            # በTesseract ምስሉን ወደ ጽሁፍ መቀየር
            image = Image.open(photo_path)
            extracted_text = pytesseract.image_to_string(image)
        except Exception as e:
            logging.error(f"OCR Error: {e}")
            await update.message.reply_text("⚠️ የደረሰኙን ጽሁፍ ማነብ አልተቻለም። እባክዎን ጥራት ያለው ፎቶ ወይም የባንኩን SMS በጽሁፍ ይላኩ።")
            if os.path.exists(photo_path):
                os.remove(photo_path)
            return DEPOSIT_PROOF

        if os.path.exists(photo_path):
            os.remove(photo_path)

    # ለ. ተጠቃሚው የላከው የSMS ጽሁፍ ከሆነ
    elif update.message.text:
        extracted_text = update.message.text

    # ሐ. ደረሰኙን ማረጋገጥ (Verification Logic)
    is_valid, message = verify_receipt_text(extracted_text, expected_amount, method)

    if is_valid:
        # ክፍያውን ማጽደቅና ሂሳብ ላይ መጨመር
        users_db[user_id]['wallet_balance'] += expected_amount
        save_db()

        success_msg = (
            f"🎉 **ክፍያዎ ተረጋግጦ ጸድቋል!**\n\n"
            f"💵 **የተጨመረበት ሂሳብ፦** {expected_amount} ETB\n"
            f"💰 **አጠቃላይ የዋሌት ሂሳብዎ፦** {users_db[user_id]['wallet_balance']} ETB"
        )
        await update.message.reply_text(success_msg, parse_mode="Markdown")
        return ConversationHandler.END
    else:
        # ክፍያው ውድቅ ከሆነ ምክንያት መንገር
        await update.message.reply_text(
            f"{message}\n\nእባክዎን ትክክለኛውን የትራንዛክሽን SMS ወይም ደረሰኝ እንደገና ይላኩ፦"
        )
        return DEPOSIT_PROOF

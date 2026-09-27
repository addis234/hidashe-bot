import os
import logging
import json
import re
import threading
from typing import Tuple

import uvicorn
from fastapi import FastAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    # ለሙከራ እንዲረዳ Render ላይ ባይኖርም እንዳይዘጋ ማድረግ
    logging.warning("BOT_TOKEN is not set in Environment Variables!")

ADMIN_ID = int(os.environ.get("ADMIN_ID", "6722504980"))

MY_CBE_NAME = "Addis Alemayehu"
MY_TELEBIRR_NAME = "Addis"

DB_FILE = "users_db.json"
USED_TXNS_FILE = "used_txns.json"

DEPOSIT_METHOD, DEPOSIT_AMOUNT, DEPOSIT_PROOF = range(3)

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
# DATABASE & TRANSACTIONS MANAGEMENT
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

# -------------------------------------------------------------
# VERIFICATION LOGIC (የተቀባይ ስም እና የብር መጠን ማረጋገጫ)
# -------------------------------------------------------------
def verify_receipt_text(text: str, expected_amount: int, method: str) -> Tuple[bool, str]:
    clean_text = text.lower()

    # 1. የተቀባይ ስም መኖሩን ማረጋገጥ
    if "addis" not in clean_text:
        return False, f"❌ በደረሰኙ ላይ የተቀባይ ስም ({MY_CBE_NAME} / {MY_TELEBIRR_NAME}) አልተገኘም።"

    # 2. የብር መጠኑ እኩል መሆኑን ማረጋገጥ
    amount_pattern = rf"\b{expected_amount}(\.00)?\b"
    if not re.search(amount_pattern, text):
        return False, f"❌ በደረሰኙ ላይ የተገለጸው የብር መጠን ከጠየቁት ({expected_amount} ETB) ጋር አይጣጣምም።"

    # 3. የትራንዛክሽን ቁጥር መደጋገሙን መፈተሽ
    txn_match = re.search(r'\b([A-Za-z0-9]{8,12})\b', text)
    if txn_match:
        txn_id = txn_match.group(1).upper()
        if txn_id in used_txns:
            return False, "❌ ይህ የትራንዛክሽን ቁጥር/ደረሰኝ ቀደም ብሎ ጥቅም ላይ ውሏል!"
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
        except Exception as e:
            logging.error(f"OCR Error: {e}")
            await update.message.reply_text("⚠️ ደረሰኙን ማንበብ አልተቻለም። እባክዎን የትራንዛክሽን SMS ጽሁፉን ይላኩ።")
            if os.path.exists(photo_path):
                os.remove(photo_path)
            return DEPOSIT_PROOF

        if os.path.exists(photo_path):
            os.remove(photo_path)

    elif update.message.text:
        extracted_text = update.message.text

    is_valid, message = verify_receipt_text(extracted_text, expected_amount, method)

    if is_valid:
        if user_id not in users_db:
            users_db[user_id] = {'wallet_balance': 0}
        users_db[user_id]['wallet_balance'] += expected_amount
        save_db()

        await update.message.reply_text(
            f"🎉 **ክፍያዎ ተረጋግጦ ጸድቋል!**\n\n"
            f"💵 **የተጨመረበት ሂሳብ፦** {expected_amount} ETB\n"
            f"💰 **አጠቃላይ ዋሌትዎ፦** {users_db[user_id]['wallet_balance']} ETB",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(f"{message}\n\nእባክዎን ትክክለኛውን ደረሰኝ/SMS እንደገና ይላኩ፦")
        return DEPOSIT_PROOF

# -------------------------------------------------------------
# MAIN APP SETUP
# -------------------------------------------------------------
def main():
    threading.Thread(target=run_web_server, daemon=True).start()

    if not BOT_TOKEN:
        logging.error("BOT_TOKEN አልተዘጋጀም! እባክዎን በ Render Environment Variables ውስጥ ያስገቡ።")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    dep_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: DEPOSIT_METHOD, pattern="^start_deposit$")],
        states={
            DEPOSIT_PROOF: [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, deposit_proof_received)]
        },
        fallbacks=[],
        per_user=True
    )

    app.add_handler(dep_conv)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

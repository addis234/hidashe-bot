import os
import logging
import json
import re
import threading
import asyncio
import signal
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

    # 2. የብር መጠኑ እኩል መሆኑን ማረጋገጥ (ኮማዎችን እና ነጥቦችን ያካተተ)
    amount_str = f"{expected_amount:,}"
    amount_pattern = rf"\b({expected_amount}|{amount_str})(\.00)?\b"
    if not re.search(amount_pattern, text):
        return False, f"❌ በደረሰኙ ላይ የተገለጸው የብር መጠን ከጠየቁት ({expected_amount} ETB) ጋር አይጣጣምም።"

    # 3. የትራንዛክሽን ቁጥር መደጋገሙን መፈተሽ (የCBE እና Telebirr Txn ID ቅርጸት)
    txn_match = re.search(r'\b(FT[A-Za-z0-9]{8,10}|[A-Za-z0-9]{10,12})\b', text)
    if txn_match:
        txn_id = txn_match.group(1).upper()
        if txn_id in used_txns:
            return False, "❌ ይህ የትራንዛክሽን ቁጥር/ደረሰኝ ቀደም ብሎ ጥቅም ላይ ውሏል!"
        save_used_txn(txn_id)

    return True, "✅ ማረጋገጫው ተሳክቷል!"

# -------------------------------------------------------------
# CONVERSATION HANDLERS
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("💳 ብር ገቢ ለማድረግ (Deposit)", callback_data="start_deposit")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("እንኳን ወደ ቦቱ በደህና መጡ! ለመቀጠል ከታች ያለውን ቁልፍ ይጫኑ፦", reply_markup=reply_markup)

async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("CBE Birr / Bank", callback_data="dep_CBE")],
        [InlineKeyboardButton("Telebirr", callback_data="dep_Telebirr")]
    ]
    await query.edit_message_text("እባክዎን የከፈሉበትን መንገድ ይምረጡ፦", reply_markup=InlineKeyboardMarkup(keyboard))
    return DEPOSIT_METHOD

async def deposit_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    method = query.data.replace("dep_", "")
    context.user_data['dep_method'] = method
    
    await query.edit_message_text(f"የመረጡት መንገድ፦ **{method}**\n\nእባክዎን ማስገባት የሚፈልጉትን የብር መጠን በቁጥር ብቻ ያስገቡ (ምሳሌ፦ 500)፦", parse_mode="Markdown")
    return DEPOSIT_AMOUNT

async def deposit_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ እባክዎን ትክክለኛ የብር መጠን በቁጥር ብቻ ያስገቡ (ምሳሌ፦ 500)፦")
        return DEPOSIT_AMOUNT

    amount = int(text)
    if amount < 10:
        await update.message.reply_text("❌ አነስተኛው ገቢ የሚደረግ ብር 10 ETB ነው። እባክዎን እንደገና ያስገቡ፦")
        return DEPOSIT_AMOUNT

    context.user_data['dep_amount'] = amount
    method = context.user_data.get('dep_method', 'CBE')
    account_name = MY_CBE_NAME if method == "CBE" else MY_TELEBIRR_NAME

    await update.message.reply_text(
        f"ለማስገባት የጠየቁት መጠን፦ **{amount} ETB**\n"
        f"የተቀባይ ስም፦ **{account_name}**\n\n"
        f"እባክዎን ክፍያውን ፈጽመው የባንኩን/ቴሌብርን SMS ጽሁፍ ወይም ደረሰኝ (Photo) እዚህ ይላኩ፦",
        parse_mode="Markdown"
    )
    return DEPOSIT_PROOF

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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("የገቢ ማድረግ ሂደቱ ተሰርዟል።")
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

    dep_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_deposit, pattern="^start_deposit$")],
        states={
            DEPOSIT_METHOD: [CallbackQueryHandler(deposit_method_selected, pattern="^dep_")],
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_received)],
            DEPOSIT_PROOF: [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, deposit_proof_received)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(dep_conv)
    
    logging.info("ቦቱ መስራት ጀምሯል...")

    try:
        app.run_polling(drop_pending_updates=True, stop_signals=None)
    except (KeyboardInterrupt, SystemExit):
        logging.info("ቦቱ በመዘጋት ላይ ነው...")
    finally:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
        except Exception as e:
            logging.error(f"Cleanup error: {e}")

if __name__ == "__main__":
    main()

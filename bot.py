import os
import asyncio
import logging
import json
import random
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from PIL import Image
import pytesseract
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
# 0. TESSERACT PATH CONFIGURATION
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

# -------------------------------------------------------------
# STATES FOR CONVERSATION
# -------------------------------------------------------------
SELECT_METHOD, ENTER_AMOUNT, ENTER_PIN_OR_TXN = range(3)

# -------------------------------------------------------------
# 1. RENDER HEALTH CHECK SERVER
# -------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Hidashe Lottery Bot is Live!")

def start_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logging.info(f"Starting Health Check Server on port {port}...")
    server.serve_forever()

# -------------------------------------------------------------
# 2. BOT CONFIGURATION & JSON DATABASE
# -------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 6722504980
PUBLIC_CHANNEL = os.environ.get("PUBLIC_CHANNEL", "") 

TICKET_PRICE = 50  # ETB
REFERRAL_BONUS = 10  # ETB per ticket bought by invited user

CBE_ACCOUNT = "1000723732108"
TELEBIRR_NUMBER = "0914197335"

PRIZES = [
    "1ኛ እጣ፦ Core i7 14th Gen Laptop 💻",
    "2ኛ እጣ፦ Samsung Galaxy A54 📱",
    "3ኛ እጣ፦ Lenovo Tab P11 📲",
    "4ኛ እጣ፦ 10,000 ETB 💵",
    "5ኛ እጣ፦ 8,000 ETB 💵",
    "6ኛ እጣ፦ 6,000 ETB 💵",
    "7ኛ እጣ፦ 4,000 ETB 💵",
    "8ኛ እጣ፦ 3,000 ETB 💵",
    "9ኛ እጣ፦ 2,000 ETB 💵",
    "10ኛ እጣ፦ 1,000 ETB 💵"
]

DB_FILE = "users_db.json"
USED_TXNS_FILE = "used_txns.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                db = {int(k): v for k, v in data.items()}
                for u in db.values():
                    if 'ticket_numbers' not in u:
                        u['ticket_numbers'] = []
                    if 'phone' not in u:
                        u['phone'] = None
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

# -------------------------------------------------------------
# 3. HELPER FUNCTIONS & KEYBOARDS
# -------------------------------------------------------------
def process_ticket_issuance(user_id: int, num_tickets: int):
    buyer = users_db[user_id]
    buyer['tickets'] += num_tickets

    total_tickets_issued = sum(len(u.get('ticket_numbers', [])) for u in users_db.values())
    new_ticket_numbers = []
    for i in range(1, num_tickets + 1):
        t_num = f"HD-{1000 + total_tickets_issued + i}"
        new_ticket_numbers.append(t_num)

    buyer.setdefault('ticket_numbers', []).extend(new_ticket_numbers)

    referrer_id = buyer.get('referrer')
    bonus_issued = 0
    if referrer_id and referrer_id in users_db:
        referrer = users_db[referrer_id]
        bonus_amount = num_tickets * REFERRAL_BONUS
        referrer['balance'] += bonus_amount
        bonus_issued = bonus_amount

    save_db()
    return new_ticket_numbers, referrer_id, bonus_issued

def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎟️ ቲኬት ቁረጥ (በክፍያ ሊንክ)", callback_data="buy_ticket_flow")],
        [InlineKeyboardButton("🎁 የሽልማት ዝርዝር", callback_data="show_prizes")],
        [InlineKeyboardButton("👥 የሪፈራል ሊንክ", callback_data="get_referral")],
        [InlineKeyboardButton("💰 የኔ ሂሳብ (Balance)", callback_data="my_balance")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    keyboard = [[InlineKeyboardButton("🔙 ወደ ዋናው ማውጫ", callback_data="main_menu")]]
    return InlineKeyboardMarkup(keyboard)

def get_phone_keyboard():
    keyboard = [[KeyboardButton("📱 ስልክ ቁጥሬን ላክ", request_contact=True)]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_payment_method_keyboard():
    keyboard = [
        [InlineKeyboardButton("🏦 CBE Birr / Commercial Bank", callback_data="pay_cbe")],
        [InlineKeyboardButton("📲 Telebirr", callback_data="pay_telebirr")],
        [InlineKeyboardButton("❌ ሰርዝ", callback_data="cancel_payment")]
    ]
    return InlineKeyboardMarkup(keyboard)

# -------------------------------------------------------------
# 4. BOT HANDLERS & PAYMENT FLOW
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    args = context.args
    if user_id not in users_db:
        users_db[user_id] = {
            'tickets': 0, 
            'balance': 0, 
            'referrer': None,
            'username': user.username or "",
            'full_name': user.full_name or "",
            'phone': None,
            'ticket_numbers': []
        }
        if args and args[0].isdigit():
            referrer_id = int(args[0])
            if referrer_id != user_id and referrer_id in users_db:
                users_db[user_id]['referrer'] = referrer_id
        save_db()

    welcome_text = (
        f"እንኳን ወደ **ህዳሴ ሎተሪ** በደህና መጡ! 🎟️\n\n"
        f"የአንድ ቲኬት ዋጋ፦ **{TICKET_PRICE} ብር**\n"
        f"የፈለጉትን ያህል ቲኬት መግዛት ይችላሉ!\n\n"
        f"💡 **ማስታወሻ፦** ቲኬት ሲቆርጡ የራስዎ የሪፈራል ሊንክ ይፈጠርልዎታል። "
        f"በእርስዎ ሊንክ ገብተው ሰዎች ቲኬት ሲቆርጡ ለእያንዳንዱ ቲኬት **{REFERRAL_BONUS} ብር** ኮሚሽን ያገኛሉ!\n\n"
        f"እባክዎን ከታች ካሉት አማራጮች አንዱን ይምረጡ፦"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END

async def start_payment_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not users_db.get(user_id, {}).get('phone'):
        phone_prompt = (
            f"⚠️ **ስልክ ቁጥር ያስፈልጋል!**\n\n"
            f"ቲኬት ለመቁረጥ እና በእጣው ወቅት አሸናፊ ሲሆኑ እንድናገኝዎ እባክዎን ከታች ያለውን **'📱 ስልክ ቁጥሬን ላክ'** የሚለውን ቁልፍ በመጫን ስልክ ቁጥርዎን ያጋሩ።"
        )
        await query.message.reply_text(phone_prompt, parse_mode="Markdown", reply_markup=get_phone_keyboard())
        return ConversationHandler.END

    msg = (
        f"💳 **የክፍያ አማራጭ ይምረጡ፦**\n\n"
        f"እባክዎን ክፍያ መፈጸም የሚፈልጉበትን የባንክ/የክፍያ መንገድ ይምረጡ፦"
    )
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_payment_method_keyboard())
    return SELECT_METHOD

async def method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data

    if method == "cancel_payment":
        await query.edit_message_text("❌ የክፍያ ሂደቱ ተሰርዟል።", reply_markup=get_back_keyboard())
        return ConversationHandler.END

    context.user_data['payment_method'] = "CBE" if method == "pay_cbe" else "Telebirr"
    acc_info = CBE_ACCOUNT if method == "pay_cbe" else TELEBIRR_NUMBER

    msg = (
        f"📌 **የተመረጠው የክፍያ መንገድ፦ {context.user_data['payment_method']}**\n"
        f"የሂሳብ ቁጥር/ስልክ፦ `{acc_info}`\n\n"
        f"💵 **እባክዎን መክፈል የሚፈልጉትን የብር መጠን ያስገቡ፦**\n"
        f"(ማስታወሻ፦ የ1 ቲኬት ዋጋ {TICKET_PRICE} ብር ነው)"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")
    return ENTER_AMOUNT

async def amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text.isdigit() or int(text) < TICKET_PRICE:
        await update.message.reply_text(f"⚠️ እባክዎን ትክክለኛ የብር መጠን ያስገቡ (ከ {TICKET_PRICE} ብር ወይም ከዚያ በላይ)፦")
        return ENTER_AMOUNT

    amount = int(text)
    num_tickets = amount // TICKET_PRICE
    context.user_data['amount'] = amount
    context.user_data['num_tickets'] = num_tickets

    acc_info = CBE_ACCOUNT if context.user_data['payment_method'] == "CBE" else TELEBIRR_NUMBER

    msg = (
        f"💰 **የከፈሉት መጠን፦ {amount} ETB** ({num_tickets} ቲኬት)\n\n"
        f"እባክዎን ክፍያውን ወደዚህ ሂሳብ ይላኩ፦ `{acc_info}`\n\n"
        f"🔐 **ክፍያውን ከፈጸሙ በኋላ የወጣውን የትራንዛክሽን ቁጥር (Txn ID) ወይም የማረጋገጫ ኮድ እዚህ ያስገቡ፦**"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    return ENTER_PIN_OR_TXN

async def pin_or_txn_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    txn_id = update.message.text.strip().upper()
    num_tickets = context.user_data.get('num_tickets', 1)

    if txn_id in used_transactions:
        await update.message.reply_text("⚠️ **ይህ የትራንዛክሽን ቁጥር ቀደም ሲል ጥቅም ላይ ውሏል!**\nእባክዎን ትክክለኛ የትራንዛክሽን ቁጥር ያስገቡ።")
        return ENTER_PIN_OR_TXN

    used_transactions.add(txn_id)
    save_used_txns()

    new_tickets, ref_id, ref_bonus = process_ticket_issuance(user_id, num_tickets)
    formatted_tickets = ", ".join([f"`{tn}`" for tn in new_tickets])

    success_msg = (
        f"✅ **ክፍያው በስኬት ተጠናቋል!**\n\n"
        f"🔖 **የትራንዛክሽን ቁጥር፦** `{txn_id}`\n"
        f"🎟️ **የተሰጠዎት የቲኬት ቁጥር፦** {formatted_tickets}\n\n"
        f"🎉 **መልካም እድል!**\n"
        f"የራስዎን የሪፈራል ሊንክ በመውሰድ ሰዎችን መጋበዝ ይችላሉ!"
    )
    await update.message.reply_text(success_msg, parse_mode="Markdown", reply_markup=get_back_keyboard())

    if ref_id and ref_bonus > 0:
        try:
            await context.bot.send_message(
                chat_id=ref_id,
                text=(
                    f"🎉 **እንኳን ደስ አለዎት!**\n\n"
                    f"በእርስዎ ሊንክ የገባ ተጠቃሚ ({num_tickets} ቲኬት) ስለቆረጠ "
                    f"**{ref_bonus} ETB** ቦነስ ኮሚሽን ወደ ሂሳብዎ ገብቷል!"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.warning(f"Failed to notify referrer: {e}")

    return ConversationHandler.END

async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ የክፍያ ሂደቱ ተሰርዟል።", reply_markup=get_back_keyboard())
    return ConversationHandler.END

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    contact = update.message.contact

    if contact and contact.user_id == user_id:
        phone_number = contact.phone_number
        if user_id not in users_db:
            users_db[user_id] = {
                'tickets': 0, 
                'balance': 0, 
                'referrer': None,
                'username': user.username or "",
                'full_name': user.full_name or "",
                'phone': phone_number,
                'ticket_numbers': []
            }
        else:
            users_db[user_id]['phone'] = phone_number
        save_db()

        await update.message.reply_text("✅ ስልክ ቁጥርዎ በስኬት ተመዝግቧል! አሁን '🎟️ ቲኬት ቁረጥ' የሚለውን በመጫን መቀጠል ይችላሉ።", reply_markup=get_main_menu_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "show_prizes":
        prizes_text = "🏆 **የህዳሴ ሎተሪ 10 የሽልማት እጣዎች፦**\n\n"
        for prize in PRIZES:
            prizes_text += f"{prize}\n"
        await query.edit_message_text(prizes_text, parse_mode="Markdown", reply_markup=get_back_keyboard())

    elif query.data == "get_referral":
        user_data = users_db.get(user_id, {'tickets': 0})
        if user_data.get('tickets', 0) < 1:
            msg = (
                f"❌ **የሪፈራል ሊንክ ማግኘት አልተቻለም!**\n\n"
                f"የሪፈራል ሊንክ ለማግኘትና ሰዎችን በመጋበዝ ኮሚሽን ለማግኘት **ቢያንስ 1 ቲኬት** መቁረጥ ይኖርብዎታል።\n\n"
                f"እባክዎን መጀመሪያ ቲኬት ይቁረጡ!"
            )
        else:
            bot_username = context.bot.username
            ref_link = f"https://t.me/{bot_username}?start={user_id}"
            msg = (
                f"🔗 **የእርስዎ የሪፈራል ሊንክ፦**\n`{ref_link}`\n\n"
                f"ይህንን ሊንክ ለወዳጅ ዘመድዎ ያጋሩ! በእርስዎ ሊንክ ገብተው ሰዎች በሚቆርጡት እያንዳንዱ ቲኬት **{REFERRAL_BONUS} ብር** ኮሚሽን ያገኛሉ።"
            )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())

    elif query.data == "my_balance":
        user_data = users_db.get(user_id, {'tickets': 0, 'balance': 0, 'ticket_numbers': []})
        tickets_list = ", ".join(user_data.get('ticket_numbers', [])) if user_data.get('ticket_numbers') else "ምንም የለም"
        msg = (
            f"📊 **የእርስዎ መረጃ፦**\n\n"
            f"🎟️ የቆረጡት ቲኬት ብዛት፦ **{user_data['tickets']}**\n"
            f"🔢 የትኬት ቁጥሮችዎ፦ `{tickets_list}`\n"
            f"💰 ከሪፈራል ያገኙት ቦነስ፦ **{user_data['balance']} ETB**"
        )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())

    elif query.data == "main_menu":
        welcome_text = (
            f"እንኳን ወደ **ህዳሴ ሎተሪ** በደህና መጡ! 🎟️\n\n"
            f"የአንድ ቲኬት ዋጋ፦ **{TICKET_PRICE} ብር**\n"
            f"የፈለጉትን ያህል ቲኬት መግዛት ይችላሉ!\n\n"
            f"እባክዎን ከታች ካሉት አማራጮች አንዱን ይምረጡ፦"
        )
        await query.edit_message_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

# -------------------------------------------------------------
# 5. ADMIN HANDLERS (/approve, /stats, /draw)
# -------------------------------------------------------------
async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        target_user_id = int(context.args[0])
        num_tickets = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 1

        if target_user_id in users_db:
            new_ticket_numbers, ref_id, bonus_amount = process_ticket_issuance(target_user_id, num_tickets)
            buyer = users_db[target_user_id]

            formatted_tickets = ", ".join([f"`{tn}`" for tn in new_ticket_numbers])
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 **ክፍያዎ ጸድቋል!**\n🎟️ **የትኬት ቁጥሮችዎ፦** {formatted_tickets}\n\nመልካም እድል!",
                parse_mode="Markdown"
            )
            await update.message.reply_text(f"✅ ለተጠቃሚ {target_user_id} {num_tickets} ቲኬት ጸድቋል።")
    except Exception as e:
        await update.message.reply_text("❌ አጠቃቀም፦ `/approve <USER_ID> <ብዛት>`")

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    total_users = len(users_db)
    total_tickets = sum(len(u.get('ticket_numbers', [])) for u in users_db.values())
    await update.message.reply_text(f"📊 አጠቃላይ ተጠቃሚ፦ {total_users}\n🎟️ የተሸጡ ቲኬቶች፦ {total_tickets}")

async def draw_lottery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    all_tickets = [(t, uid) for uid, u in users_db.items() for t in u.get('ticket_numbers', [])]
    if len(all_tickets) < 10:
        await update.message.reply_text("⚠️ እጣ ለማውጣት ቢያንስ 10 ቲኬቶች ያስፈልጋሉ።")
        return
    
    winning_tickets = random.sample(all_tickets, 10)
    report = "🎉 **የዕጣ ማውጣት አሸናፊዎች፦**\n\n"
    for rank in range(10):
        t_num, uid = winning_tickets[rank]
        report += f"{PRIZES[rank]} -> `{t_num}` ({users_db[uid].get('full_name')})\n"
    await update.message.reply_text(report, parse_mode="Markdown")

# -------------------------------------------------------------
# 6. MAIN EXECUTION
# -------------------------------------------------------------
def main():
    threading.Thread(target=start_health_check_server, daemon=True).start()

    if not BOT_TOKEN:
        logging.error("No BOT_TOKEN provided!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    pay_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_payment_flow, pattern="^buy_ticket_flow$")],
        states={
            SELECT_METHOD: [CallbackQueryHandler(method_selected, pattern="^(pay_cbe|pay_telebirr|cancel_payment)$")],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_entered)],
            ENTER_PIN_OR_TXN: [MessageHandler(filters.TEXT & ~filters.COMMAND, pin_or_txn_entered)]
        },
        fallbacks=[CommandHandler("cancel", cancel_flow)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(pay_conv_handler)
    app.add_handler(CommandHandler("approve", approve_payment))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("draw", draw_lottery))
    
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(CallbackQueryHandler(button_handler))

    logging.info("Starting Bot Polling...")
    app.run_polling()

if __name__ == "__main__":
    main()

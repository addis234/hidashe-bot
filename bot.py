import os
import asyncio
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# -------------------------------------------------------------
# 1. RENDER HEALTH CHECK SERVER (Time Out & Port Binding Fix)
# -------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Hidashe Lottery Bot is Live!")

def start_health_check_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# -------------------------------------------------------------
# 2. BOT CONFIGURATION & DATA
# -------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 6722504980
TICKET_PRICE = 50  # ETB
REFERRAL_BONUS = 10  # ETB per invited ticket buyer

# Prize Tiers
PRIZES = [
    "1ኛ ደረጃ፡ Laptop",
    "2ኛ ደረጃ፡ Smartphone",
    "3ኛ ደረጃ፡ Tablet",
    "4ኛ ደረጃ፡ 10,000 ETB",
    "5ኛ ደረጃ፡ 5,000 ETB",
    "6ኛ ደረጃ፡ 3,000 ETB",
    "7ኛ ደረጃ፡ 2,000 ETB",
    "8ኛ ደረጃ፡ 1,000 ETB",
    "9ኛ ደረጃ፡ 500 ETB",
    "10ኛ ደረጃ፡ 250 ETB"
]

# Database in memory (For production, use persistent DB)
users_db = {}  # user_id: {'tickets': count, 'balance': ref_earnings, 'referrer': id}

# -------------------------------------------------------------
# 3. BOT HANDLERS
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Check for referral parameter
    args = context.args
    if user_id not in users_db:
        users_db[user_id] = {'tickets': 0, 'balance': 0, 'referrer': None}
        if args and args[0].isdigit():
            referrer_id = int(args[0])
            if referrer_id != user_id and referrer_id in users_db:
                users_db[user_id]['referrer'] = referrer_id

    welcome_text = (
        f"እንኳን ወደ **ህዳሴ ሎተሪ** በደህና መጡ! 🎟️\n\n"
        f"የአንድ ቲኬት ዋጋ፦ **{TICKET_PRICE} ብር**\n"
        f"ጓደኞችዎን በመጋበዝ የእያንዳንዱ ገዢ **10 ብር** ኮሚሽን ያግኙ!\n\n"
        f"እባክዎን ከታች ካሉት አማራጮች አንዱን ይምረጡ፦"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎟️ ቲኬት ቁረጥ", callback_data="buy_ticket")],
        [InlineKeyboardButton("🎁 የሽልማት ዝርዝር", callback_data="show_prizes")],
        [InlineKeyboardButton("👥 የሪፈራል ሊንክ", callback_data="get_referral")],
        [InlineKeyboardButton("💰 የኔ ሂሳብ (Balance)", callback_data="my_balance")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "buy_ticket":
        msg = (
            f"🎟️ **ቲኬት ለመቁረጥ፦**\n\n"
            f"እባክዎን **{TICKET_PRICE} ብር** በCBE/Telebirr ይላኩና የላኩበትን ደረሰኝ (Screenshot/PDF) ወይም የትራንስፎርሜሽን ቁጥር እዚህ ይላኩ።\n\n"
            f"የአድሚን ክፍያ መቀበያ፦ `1000XXXXXXXX`"
        )
        await query.message.edit_text(msg, parse_mode="Markdown")

    elif query.data == "show_prizes":
        prizes_text = "🏆 **የህዳሴ ሎተሪ 10 የሽልማት ደረጃዎች፦**\n\n"
        for idx, prize in enumerate(PRIZES, 1):
            prizes_text += f"{prize}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 ወደ ዋናው ማውጫ", callback_data="main_menu")]]
        await query.message.edit_text(prizes_text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "get_referral":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        msg = (
            f"🔗 **የእርስዎ የሪፈራል ሊንክ፦**\n`{ref_link}`\n\n"
            f"ይህንን ሊንክ ለወዳጅ ዘመድዎ ያጋሩ! በእርስዎ ሊንክ ገብተው ቲኬት ሲቆርጡ **{REFERRAL_BONUS} ብር** ወደ ሂሳብዎ ይገባል።"
        )
        keyboard = [[InlineKeyboardButton("🔙 ወደ ዋናው ማውጫ", callback_data="main_menu")]]
        await query.message.edit_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "my_balance":
        user_data = users_db.get(user_id, {'tickets': 0, 'balance': 0})
        msg = (
            f"📊 **የእርስዎ መረጃ፦**\n\n"
            f"🎟️ የቆረጡት ቲኬት ብዛት፦ **{user_data['tickets']}**\n"
            f"💰 ከሪፈራል ያገኙት ቦነስ፦ **{user_data['balance']} ETB**"
        )
        keyboard = [[InlineKeyboardButton("🔙 ወደ ዋናው ማውጫ", callback_data="main_menu")]]
        await query.message.edit_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "main_menu":
        await start(update, context)

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Notify Admin about new receipt submission
    admin_msg = (
        f"📥 **አዲስ የቲኬት ክፍያ ደረሰኝ ደርሷል!**\n\n"
        f"👤 ላኪ፦ {user.full_name} (@{user.username})\n"
        f"🆔 ID: `{user_id}`\n\n"
        f"እባክዎን ያረጋግጡና በ `/approve {user_id}` ማፅደቅ ይችላሉ።"
    )
    
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
    if update.message.photo or update.message.document:
        await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=user_id, message_id=update.message.message_id)
    
    await update.message.reply_text("✅ ደረሰኝዎ ለቁጥጥር ለአድሚን ተልኳል! ከተረጋገጠ በኋላ ቲኬትዎ ይላክልዎታል።")

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        target_user_id = int(context.args[0])
        if target_user_id in users_db:
            users_db[target_user_id]['tickets'] += 1
            
            # Referral Bonus Logic
            referrer_id = users_db[target_user_id].get('referrer')
            if referrer_id and referrer_id in users_db:
                users_db[referrer_id]['balance'] += REFERRAL_BONUS
                # Notify Referrer
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 **እንኳን ደስ አለዎት!**\nበእርስዎ ሊንክ የገባ ሰው ቲኬት ስለቆረጠ **{REFERRAL_BONUS} ETB** ቦነስ አግኝተዋል!"
                )

            # Notify Buyer
            await context.bot.send_message(
                chat_id=target_user_id,
                text="🎉 **ክፍያዎ ጸድቋል!**\nቲኬትዎ በስኬት ተቆርጧል። መልካም እድል!"
            )
            await update.message.reply_text(f"✅ ለተጠቃሚ {target_user_id} ቲኬቱ ጸድቋል።")
    except Exception as e:
        await update.message.reply_text("❌ እባክዎን ትክክለኛ የተጠቃሚ ID ያስገቡ፦ `/approve <USER_ID>`")

# -------------------------------------------------------------
# 4. MAIN EXECUTION
# -------------------------------------------------------------
def main():
    # Start Health Check Server in a separate thread for Render
    threading.Thread(target=start_health_check_server, daemon=True).start()

    # Initialize Telegram Bot Application
    app = Application.builder().token(BOT_TOKEN).build()

    # Add Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve_payment))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL | filters.TEXT, handle_receipt))

    # Run Bot Polling
    app.run_polling()

if __name__ == "__main__":
    main()

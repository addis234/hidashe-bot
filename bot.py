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
    # Render provides PORT environment variable, defaults to 10000
    port = int(os.environ.get("PORT", 10000))
    # Listen on all interfaces (0.0.0.0)
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logging.info(f"Starting Health Check Server on port {port}...")
    server.serve_forever()

# -------------------------------------------------------------
# 2. BOT CONFIGURATION & DATA
# -------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 6722504980 # Replace with your actual Admin ID
TICKET_PRICE = 50  # ETB
REFERRAL_BONUS = 10  # ETB per invited ticket buyer

# Payment Details (Updated with User Provided Info)
CBE_ACCOUNT = "1000723732108"
TELEBIRR_NUMBER = "0914197335"
ACCOUNT_HOLDER_NAME = "" # አድሚኑ ክፍያውን ሲያረጋግጥ የሚያየው ስም

# Prize Tiers
PRIZES = [
    "1ኛ ደረጃ፦ ዘመናዊ Laptop 💻",
    "2ኛ ደረጃ፦ Smartphone 📱",
    "3ኛ ደረጃ፦ Tablet 📲",
    "4ኛ ደረጃ፦ 10,000 ETB 💵",
    "5ኛ ደረጃ፦ 5,000 ETB 💵",
    "6ኛ ደረጃ፦ 3,000 ETB 💵",
    "7ኛ ደረጃ፦ 2,000 ETB 💵",
    "8ኛ ደረጃ፦ 1,000 ETB 💵",
    "9ኛ ደረጃ፦ 500 ETB 💵",
    "10ኛ ደረጃ፦ 250 ETB 💵"
]

# Database in memory (For production, use persistent DB)
users_db = {}  # user_id: {'tickets': count, 'balance': ref_earnings, 'referrer': id, 'username': str, 'full_name': str}

# -------------------------------------------------------------
# 3. BOT HANDLERS
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Check for referral parameter
    args = context.args
    if user_id not in users_db:
        users_db[user_id] = {
            'tickets': 0, 
            'balance': 0, 
            'referrer': None,
            'username': user.username,
            'full_name': user.full_name
        }
        if args and args[0].isdigit():
            referrer_id = int(args[0])
            # Prevent self-referral and ensure referrer exists
            if referrer_id != user_id and referrer_id in users_db:
                users_db[user_id]['referrer'] = referrer_id
                logging.info(f"User {user_id} referred by {referrer_id}")

    welcome_text = (
        f"እንኳን ወደ **ህዳሴ ሎተሪ** በደህና መጡ! 🎟️\n\n"
        f"የአንድ ቲኬት ዋጋ፦ **{TICKET_PRICE} ብር**\n"
        f"ጓደኞችዎን በመጋበዝ የእያንዳንዱ ገዢ **{REFERRAL_BONUS} ብር** ኮሚሽን ያግኙ!\n\n"
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
            f"እባክዎን **{TICKET_PRICE} ብር** ከታች ባሉት የክፍያ አማራጮች ይላኩ፦\n\n"
            f"▫️ **በCBE (የኢትዮጵያ ንግድ ባንክ)፦**\n"
            f"ቁጥር፦ `{CBE_ACCOUNT}`\n\n"
            f"▫️ **በቴሌብር (Telebirr)፦**\n"
            f"ቁጥር፦ `{TELEBIRR_NUMBER}`\n\n"
            f"ክፍያውን እንደፈጸሙ፣ የላኩበትን **ደረሰኝ (Screenshot/PDF)** ወይም የትራንስፎርሜሽን ቁጥር እዚህ ይላኩ።"
        )
        keyboard = []
        await query.message.edit_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "show_prizes":
        prizes_text = "🏆 **የህዳሴ ሎተሪ 10 የሽልማት ደረጃዎች፦**\n\n"
        for idx, prize in enumerate(PRIZES, 1):
            prizes_text += f"{prize}\n"
        
        keyboard = []
        await query.message.edit_text(prizes_text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "get_referral":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        msg = (
            f"🔗 **የእርስዎ የሪፈራል ሊንክ፦**\n`{ref_link}`\n\n"
            f"ይህንን ሊንክ ለወዳጅ ዘመድዎ ያጋሩ! በእርስዎ ሊንክ ገብተው ቲኬት ሲቆርጡ **{REFERRAL_BONUS} ብር** ወደ ሂሳብዎ ይገባል።"
        )
        keyboard = []
        await query.message.edit_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "my_balance":
        user_data = users_db.get(user_id, {'tickets': 0, 'balance': 0})
        msg = (
            f"📊 **የእርስዎ መረጃ፦**\n\n"
            f"🎟️ የቆረጡት ቲኬት ብዛት፦ **{user_data['tickets']}**\n"
            f"💰 ከሪፈራል ያገኙት ቦነስ፦ **{user_data['balance']} ETB**"
        )
        keyboard = []
        await query.message.edit_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "main_menu":
        await start(update, context)

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Ensure user is in DB
    if user_id not in users_db:
        users_db[user_id] = {
            'tickets': 0, 
            'balance': 0, 
            'referrer': None,
            'username': user.username,
            'full_name': user.full_name
        }

    # Notify Admin about new receipt submission
    admin_msg = (
        f"📥 **አዲስ የቲኬት ክፍያ ደረሰኝ ደርሷል!**\n\n"
        f"👤 ላኪ፦ {user.full_name} (@{user.username})\n"
        f"🆔 ID: `{user_id}`\n\n"
        f"💳 ክፍያ የተፈጸመበት፦ `{ACCOUNT_HOLDER_NAME}`\n"
        f"🏦 CBE: `{CBE_ACCOUNT}`\n"
        f"📲 Telebirr: `{TELEBIRR_NUMBER}`\n\n"
        f"እባክዎን ደረሰኙን ካረጋገጡ በኋላ በአንዱ መንገድ ያፅድቁ፦\n"
        f"1. `/approve {user_id}` (ለ 1 ቲኬት)\n"
        f"2. `/approve {user_id} <ብዛት>` (ለብዙ ቲኬት፣ ለምሳሌ፡ `/approve {user_id} 5`)"
    )
    
    # Send message to Admin
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
    
    # Forward the receipt (photo/document/text) to Admin
    if update.message.photo or update.message.document:
        await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=user_id, message_id=update.message.message_id)
    elif update.message.text:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"💬 የተላከ የጽሁፍ መልዕክት/ቁጥር፦\n`{update.message.text}`", parse_mode="Markdown")
    
    # Inform User
    await update.message.reply_text("✅ ደረሰኝዎ ለቁጥጥር ለአድሚን ተልኳል! ከተረጋገጠ በኋላ ቲኬትዎ ይላክልዎታል።")

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only Admin can use this command
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        # Get target user ID from arguments
        target_user_id = int(context.args[0])
        
        # Get number of tickets (defaults to 1 if not provided)
        num_tickets = 1
        if len(context.args) > 1 and context.args[1].isdigit():
            num_tickets = int(context.args[1])

        if target_user_id in users_db:
            # Add tickets to buyer
            users_db[target_user_id]['tickets'] += num_tickets
            logging.info(f"Admin approved {num_tickets} tickets for user {target_user_id}")
            
            # Referral Bonus Logic
            referrer_id = users_db[target_user_id].get('referrer')
            if referrer_id and referrer_id in users_db:
                bonus_amount = num_tickets * REFERRAL_BONUS
                users_db[referrer_id]['balance'] += bonus_amount
                logging.info(f"Referrer {referrer_id} awarded {bonus_amount} ETB bonus for user {target_user_id}")
                
                # Notify Referrer
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=(
                            f"🎉 **እንኳን ደስ አለዎት!**\n"
                            f"በእርስዎ ሊንክ የገባ ሰው {num_tickets} ቲኬት ስለቆረጠ **{bonus_amount} ETB** ቦነስ ወደ ሂሳብዎ ገብቷል!"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logging.warning(f"Failed to notify referrer {referrer_id}: {e}")

            # Notify Buyer
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=(
                        f"🎉 **ክፍያዎ ጸድቋል!**\n"
                        f"{num_tickets} ቲኬትዎ በስኬት ተቆርጧል። መልካም እድል!"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.warning(f"Failed to notify buyer {target_user_id}: {e}")
                
            await update.message.reply_text(f"✅ ለተጠቃሚ {target_user_id} {num_tickets} ቲኬቱ ጸድቋል።")
        else:
            await update.message.reply_text(f"❌ ተጠቃሚ {target_user_id} በዳታቤዝ ውስጥ አልተገኘም።")
            
    except (IndexError, ValueError) as e:
        await update.message.reply_text(
            "❌ እባክዎን በትክክለኛው ፎርማት ያስገቡ፦\n"
            "`/approve <USER_ID>` (ለ 1 ቲኬት)\n"
            "`/approve <USER_ID> <ብዛት>` (ለብዙ ቲኬት)",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Error in approve_payment: {e}")
        await update.message.reply_text(f"❌ ያልታወቀ ስህተት ተከስቷል፦ {e}")

# -------------------------------------------------------------
# 4. MAIN EXECUTION
# -------------------------------------------------------------
def main():
    # Start Health Check Server in a separate thread for Render
    # This keeps Render from timing out the deployment
    threading.Thread(target=start_health_check_server, daemon=True).start()

    # Ensure BOT_TOKEN is provided
    if not BOT_TOKEN:
        logging.error("No BOT_TOKEN provided! Exiting...")
        return

    # Initialize Telegram Bot Application
    app = Application.builder().token(BOT_TOKEN).build()

    # Add Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve_payment))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Handle receipts (photos, documents, or text confirmation)
    receipt_filter = filters.PHOTO | filters.Document.ALL | filters.TEXT
    app.add_handler(MessageHandler(receipt_filter & ~filters.COMMAND, handle_receipt))

    # Run Bot Polling
    logging.info("Starting Bot Polling...")
    app.run_polling()

if __name__ == "__main__":
    main()

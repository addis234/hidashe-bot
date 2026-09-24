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
# 2. BOT CONFIGURATION & DATA
# -------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 6722504980  # የተስተካከለ የአድሚን ID

TICKET_PRICE = 50  # ETB
REFERRAL_BONUS = 10  # ETB per ticket bought by invited user

# Payment Details
CBE_ACCOUNT = "1000723732108"
TELEBIRR_NUMBER = "0914197335"

# Specific Prize Tiers
PRIZES = [
    "1ኛ ደረጃ፦ Core i7 14th Gen Laptop 💻",
    "2ኛ ደረጃ፦ Samsung Galaxy A54 📱",
    "3ኛ ደረጃ፦ Lenovo Tab P11 📲",
    "4ኛ ደረጃ፦ 10,000 ETB 💵",
    "5ኛ ደረጃ፦ 8,000 ETB 💵",
    "6ኛ ደረጃ፦ 6,000 ETB 💵",
    "7ኛ ደረጃ፦ 4,000 ETB 💵",
    "8ኛ ደረጃ፦ 3,000 ETB 💵",
    "9ኛ ደረጃ፦ 2,000 ETB 💵",
    "10ኛ ደረጃ፦ 1,000 ETB 💵"
]

# Database in memory
# users_db format: user_id: {'tickets': count, 'balance': ref_earnings, 'referrer': id, 'username': str, 'full_name': str}
users_db = {}

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
            'username': user.username or "",
            'full_name': user.full_name or ""
        }
        if args and args[0].isdigit():
            referrer_id = int(args[0])
            if referrer_id != user_id and referrer_id in users_db:
                users_db[user_id]['referrer'] = referrer_id

    welcome_text = (
        f"እንኳን ወደ **ህዳሴ ሎተሪ** በደህና መጡ! 🎟️\n\n"
        f"የአንድ ቲኬት ዋጋ፦ **{TICKET_PRICE} ብር**\n"
        f"የፈለጉትን ያህል ቲኬት መግዛት ይችላሉ!\n\n"
        f"💡 **ማስታወሻ፦** ቲኬት ሲቆርጡ የራስዎ የሪፈራል ሊንክ ይፈጠርልዎታል። "
        f"በእርስዎ ሊንክ ገብተው ሰዎች ቲኬት ሲቆርጡ ለእያንዳንዱ ቲኬት **{REFERRAL_BONUS} ብር** ኮሚሽን ያገኛሉ!\n\n"
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
            f"የአንድ ቲኬት ዋጋ **{TICKET_PRICE} ብር** ሲሆን የፈለጉትን ያህል ብዛት መቁረጥ ይችላሉ።\n\n"
            f"እባክዎን ጠቅላላ ክፍያውን ከታች ባሉት የክፍያ አማራጮች ይላኩ፦\n\n"
            f"▫️ **በCBE (የኢትዮጵያ ንግድ ባንክ)፦**\n"
            f"`{CBE_ACCOUNT}`\n\n"
            f"▫️ **በቴሌብር (Telebirr)፦**\n"
            f"`{TELEBIRR_NUMBER}`\n\n"
            f"ክፍያውን እንደፈጸሙ፣ የላኩበትን **ደረሰኝ (Screenshot/PDF)** ወይም የትራንስፎርሜሽን ቁጥር እዚህ ይላኩ።"
        )
        keyboard = [[InlineKeyboardButton("🔙 ወደ ዋናው ማውጫ", callback_data="main_menu")]]
        await query.message.edit_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "show_prizes":
        prizes_text = "🏆 **የህዳሴ ሎተሪ 10 የሽልማት ደረጃዎች፦**\n\n"
        for prize in PRIZES:
            prizes_text += f"{prize}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 ወደ ዋናው ማውጫ", callback_data="main_menu")]]
        await query.message.edit_text(prizes_text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "get_referral":
        user_data = users_db.get(user_id, {'tickets': 0})
        
        # ⚠️ ቲኬት ያላስቆረጠ ሰው የሪፈራል ሊንክ አያገኝም
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
    
    if user_id not in users_db:
        users_db[user_id] = {
            'tickets': 0, 
            'balance': 0, 
            'referrer': None,
            'username': user.username or "",
            'full_name': user.full_name or ""
        }
    else:
        # Update details in case username changed
        users_db[user_id]['username'] = user.username or ""
        users_db[user_id]['full_name'] = user.full_name or ""

    admin_msg = (
        f"📥 **አዲስ የቲኬት ክፍያ ደረሰኝ ደርሷል!**\n\n"
        f"👤 ላኪ፦ {user.full_name} (@{user.username})\n"
        f"🆔 ID: `{user_id}`\n\n"
        f"እባክዎን ደረሰኙን ካረጋገጡ በኋላ በአንዱ መንገድ ያፅድቁ፦\n"
        f"1. `/approve {user_id}` (ለ 1 ቲኬት)\n"
        f"2. `/approve {user_id} <ብዛት>` (ለምሳሌ፦ `/approve {user_id} 5` ለ 5 ቲኬት)"
    )
    
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
        
        if update.message.photo or update.message.document:
            await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=user_id, message_id=update.message.message_id)
        elif update.message.text:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"💬 የተላከ የጽሁፍ መልዕክት/ቁጥር፦\n`{update.message.text}`", parse_mode="Markdown")
        
        await update.message.reply_text("✅ ደረሰኝዎ ለቁጥጥር ለአድሚን ተልኳል! ከተረጋገጠ በኋላ ቲኬትዎ ይላክልዎታል።")
    except Exception as e:
        logging.error(f"Error sending receipt to admin: {e}")
        await update.message.reply_text("❌ ደረሰኙን ለቀጣሪ መላክ አልተቻለም። እባክዎን አድሚኑ ቦቱን /start ማድረጉን ያረጋግጡ።")

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        target_user_id = int(context.args[0])
        num_tickets = 1
        if len(context.args) > 1 and context.args[1].isdigit():
            num_tickets = int(context.args[1])

        if target_user_id in users_db:
            buyer = users_db[target_user_id]
            buyer['tickets'] += num_tickets
            
            referrer_id = buyer.get('referrer')
            if referrer_id and referrer_id in users_db:
                referrer = users_db[referrer_id]
                bonus_amount = num_tickets * REFERRAL_BONUS
                referrer['balance'] += bonus_amount
                
                # 1. ለጋባዡ መልዕክት መላክ
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=(
                            f"🎉 **እንኳን ደስ አለዎት!**\n\n"
                            f"በእርስዎ ሊንክ የገባው **{buyer['full_name']}** ({num_tickets} ቲኬት) ስለቆረጠ "
                            f"**{bonus_amount} ETB** ቦነስ ኮሚሽን ወደ ሂሳብዎ ገብቷል!"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logging.warning(f"Failed to notify referrer: {e}")

                # 2. ለአድሚኑ (ለእርስዎ) ማስታወቂያ መላክ
                try:
                    admin_ref_notice = (
                        f"🔔 **የሪፈራል ኮሚሽን ማስታወቂያ!**\n\n"
                        f"👤 ገዢ፦ {buyer['full_name']} (@{buyer['username']})\n"
                        f"🎟️ የተቆረጠ ቲኬት፦ {num_tickets}\n\n"
                        f"👥 ጋባዥ፦ {referrer['full_name']} (@{referrer['username']})\n"
                        f"💰 ያገኘው ኮሚሽን፦ {bonus_amount} ETB"
                    )
                    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_ref_notice, parse_mode="Markdown")
                except Exception as e:
                    logging.warning(f"Failed to send admin notification: {e}")

            # ለቲኬት ገዢው ማረጋገጫ መላክ
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=(
                        f"🎉 **ክፍያዎ ጸድቋል!**\n\n"
                        f"**{num_tickets}** ቲኬትዎ በስኬት ተቆርጧል። መልካም እድል!\n"
                        f"አሁን የራስዎን የሪፈራል ሊንክ ከዋናው ማውጫ ላይ በመውሰድ ሰዎችን መጋበዝ ይችላሉ!"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.warning(f"Failed to notify buyer: {e}")
                
            await update.message.reply_text(f"✅ ለተጠቃሚ {target_user_id} ({buyer['full_name']}) {num_tickets} ቲኬት ጸድቋል።")
        else:
            await update.message.reply_text(f"❌ ተጠቃሚ {target_user_id} በዳታቤዝ ውስጥ አልተገኘም።")
            
    except Exception as e:
        await update.message.reply_text("❌ እባክዎን በትክክለኛው ፎርማት ያስገቡ፦ `/approve <USER_ID> <ብዛት>`", parse_mode="Markdown")

# -------------------------------------------------------------
# 4. MAIN EXECUTION
# -------------------------------------------------------------
def main():
    threading.Thread(target=start_health_check_server, daemon=True).start()

    if not BOT_TOKEN:
        logging.error("No BOT_TOKEN provided! Exiting...")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve_payment))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    receipt_filter = filters.PHOTO | filters.Document.ALL | filters.TEXT
    app.add_handler(MessageHandler(receipt_filter & ~filters.COMMAND, handle_receipt))

    logging.info("Starting Bot Polling...")
    app.run_polling()

if __name__ == "__main__":
    main()

import os
import asyncio
import logging
import json
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
# 2. BOT CONFIGURATION & JSON DATABASE
# -------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 6722504980

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

users_db = load_db()

# -------------------------------------------------------------
# 3. KEYBOARD HELPER FUNCTIONS
# -------------------------------------------------------------
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎟️ ቲኬት ቁረጥ", callback_data="buy_ticket")],
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

# -------------------------------------------------------------
# 4. BOT HANDLERS
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

        # Notify admin about user's phone number
        admin_notice = (
            f"📱 **አዲስ የስልክ ቁጥር መዝገብ!**\n\n"
            f"👤 ተጠቃሚ፦ {user.full_name} (@{user.username})\n"
            f"🆔 ID: `{user_id}`\n"
            f"📞 ስልክ፦ `{phone_number}`"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_notice, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Failed to send contact to admin: {e}")

        await update.message.reply_text("✅ ስልክ ቁጥርዎ በስኬት ተመዝግቧል!", reply_markup=ReplyKeyboardRemove())
        
        # Proceed directly to payment details
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
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in users_db:
        users_db[user_id] = {
            'tickets': 0, 
            'balance': 0, 
            'referrer': None,
            'username': query.from_user.username or "",
            'full_name': query.from_user.full_name or "",
            'phone': None,
            'ticket_numbers': []
        }
        save_db()

    try:
        if query.data == "buy_ticket":
            # Check if user has registered phone number
            if not users_db[user_id].get('phone'):
                phone_prompt = (
                    f"⚠️ **ስልክ ቁጥር ያስፈልጋል!**\n\n"
                    f"ቲኬት ለመቁረጥ እና በእጣው ወቅት አሸናፊ ሲሆኑ እንድናገኝዎ እባክዎን ከታች ያለውን **'📱 ስልክ ቁጥሬን ላክ'** የሚለውን ቁልፍ በመጫን ስልክ ቁጥርዎን ያጋሩ።"
                )
                await query.message.reply_text(phone_prompt, parse_mode="Markdown", reply_markup=get_phone_keyboard())
                return

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
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())

        elif query.data == "show_prizes":
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
                f"💡 **ማስታወሻ፦** ቲኬት ሲቆርጡ የራስዎ የሪፈራል ሊንክ ይፈጠርልዎታል። "
                f"በእርስዎ ሊንክ ገብተው ሰዎች ቲኬት ሲቆርጡ ለእያንዳንዱ ቲኬት **{REFERRAL_BONUS} ብር** ኮሚሽን ያገኛሉ!\n\n"
                f"እባክዎን ከታች ካሉት አማራጮች አንዱን ይምረጡ፦"
            )
            await query.edit_message_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

    except Exception as e:
        logging.error(f"Error handling button click: {e}")

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
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
    else:
        users_db[user_id]['username'] = user.username or ""
        users_db[user_id]['full_name'] = user.full_name or ""
    save_db()

    user_phone = users_db[user_id].get('phone', 'አልተመዘገበም')

    admin_msg = (
        f"📥 **አዲስ የቲኬት ክፍያ ደረሰኝ ደርሷል!**\n\n"
        f"👤 ላኪ፦ {user.full_name} (@{user.username})\n"
        f"🆔 ID: `{user_id}`\n"
        f"📞 ስልክ፦ `{user_phone}`\n\n"
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
        await update.message.reply_text("❌ ደረሰኙን ለቁጥጥር መላክ አልተቻለም። እባክዎን አድሚኑ ቦቱን /start ማድረጉን ያረጋግጡ።")

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
            
            # Generate unique ticket numbers
            total_tickets_issued = sum(len(u.get('ticket_numbers', [])) for u in users_db.values())
            new_ticket_numbers = []
            for i in range(1, num_tickets + 1):
                t_num = f"HD-{1000 + total_tickets_issued + i}"
                new_ticket_numbers.append(t_num)
            
            buyer.setdefault('ticket_numbers', []).extend(new_ticket_numbers)

            referrer_id = buyer.get('referrer')
            if referrer_id and referrer_id in users_db:
                referrer = users_db[referrer_id]
                bonus_amount = num_tickets * REFERRAL_BONUS
                referrer['balance'] += bonus_amount
                
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

            save_db()

            formatted_tickets = ", ".join([f"`{tn}`" for tn in new_ticket_numbers])
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=(
                        f"🎉 **ክፍያዎ ጸድቋል!**\n\n"
                        f"**{num_tickets}** ቲኬትዎ በስኬት ተቆርጧል።\n"
                        f"🎟️ **የእርስዎ የትኬት ቁጥሮች፦** {formatted_tickets}\n\n"
                        f"መልካም እድል! አሁን የራስዎን የሪፈራል ሊንክ ከዋናው ማውጫ ላይ በመውሰድ ሰዎችን መጋበዝ ይችላሉ!"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.warning(f"Failed to notify buyer: {e}")
                
            # Calculate total tickets sold across system
            overall_tickets = sum(len(u.get('ticket_numbers', [])) for u in users_db.values())
            await update.message.reply_text(
                f"✅ ለተጠቃሚ {target_user_id} ({buyer['full_name']}) {num_tickets} ቲኬት ጸድቋል።\n"
                f"የትኬት ቁጥሮች፦ {', '.join(new_ticket_numbers)}\n\n"
                f"📊 **አጠቃላይ እስካሁን የተሸጡ ቲኬቶች፦ {overall_tickets}**"
            )
        else:
            await update.message.reply_text(f"❌ ተጠቃሚ {target_user_id} በዳታቤዝ ውስጥ አልተገኘም።")
            
    except Exception as e:
        await update.message.reply_text("❌ እባክዎን በትክክለኛው ፎርማት ያስገቡ፦ `/approve <USER_ID> <ብዛት>`", parse_mode="Markdown")

# -------------------------------------------------------------
# 5. ADMIN STATS HANDLER (/stats)
# -------------------------------------------------------------
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    total_users = len(users_db)
    total_tickets = sum(len(u.get('ticket_numbers', [])) for u in users_db.values())
    total_revenue = total_tickets * TICKET_PRICE

    stats_msg = (
        f"📊 **የህዳሴ ሎተሪ አጠቃላይ ስታቲስቲክስ፦**\n\n"
        f"👥 አጠቃላይ የተመዘገቡ ተጠቃሚዎች፦ **{total_users}**\n"
        f"🎟️ አጠቃላይ የተሸጡ (የተቆረጡ) ቲኬቶች፦ **{total_tickets}**\n"
        f"💰 አጠቃላይ የተሰበሰበ ገቢ፦ **{total_revenue:,} ETB**"
    )
    await update.message.reply_text(stats_msg, parse_mode="Markdown")

# -------------------------------------------------------------
# 6. LOTTERY DRAW HANDLER (/draw)
# -------------------------------------------------------------
async def draw_lottery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    # Collect all sold tickets: list of tuples -> (ticket_number, user_id)
    all_tickets = []
    for uid, udata in users_db.items():
        for t_num in udata.get('ticket_numbers', []):
            all_tickets.append((t_num, uid))

    if len(all_tickets) < 10:
        await update.message.reply_text(f"⚠️ እጣ ለማውጣት ቢያንስ 10 ቲኬቶች መቆረጥ አለባቸው። በአሁኑ ወቅት የተሸጡት ቲኬቶች ብዛት፦ {len(all_tickets)}")
        return

    await update.message.reply_text("🎲 **የህዳሴ ሎተሪ እጣ የማውጣት ሂደት ተጀምሯል...**\nእባክዎን ትንሽ ይታገሱ!")

    # Randomly select 10 unique winning tickets
    winning_tickets = random.sample(all_tickets, 10)
    
    admin_summary = "🎉 **የዕጣው አሸናፊዎች ዝርዝር፦**\n\n"

    for rank, (ticket_num, uid) in enumerate(winning_tickets):
        prize = PRIZES[rank]
        user_info = users_db[uid]
        full_name = user_info.get('full_name', 'አልተጠቀሰም')
        phone = user_info.get('phone', 'አልተመዘገበም')
        username = f"@{user_info.get('username')}" if user_info.get('username') else "የለውም"

        # Notify winner
        winner_msg = (
            f"🎉🎉 **እንኳን ደስ አለዎት!** 🎉🎉\n\n"
            f"በህዳሴ ሎተሪ እጣ አሸናፊ ሆነዋል!\n\n"
            f"🎟️ **የአሸናፊ ትኬት ቁጥርዎ፦** `{ticket_num}`\n"
            f"🏆 **የደረሰዎት ሽልማት፦** {prize}\n\n"
            f"ሽልማቱን ለመረከብ አድሚኑ በስልክ ቁጥርዎ ወይም በቴሌግራም ያገኝዎታል።"
        )
        try:
            await context.bot.send_message(chat_id=uid, text=winner_msg, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Failed to send win notification to {uid}: {e}")

        # Add to admin summary
        admin_summary += (
            f"🎖️ **{prize}**\n"
            f"👤 አሸናፊ፦ {full_name} ({username})\n"
            f"🎟️ የትኬት ቁጥር፦ `{ticket_num}`\n"
            f"📞 ስልክ፦ `{phone}`\n"
            f"-----------------------------------\n"
        )

    # Send winners list to Admin
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_summary, parse_mode="Markdown")

# -------------------------------------------------------------
# 7. MAIN EXECUTION
# -------------------------------------------------------------
def main():
    threading.Thread(target=start_health_check_server, daemon=True).start()

    if not BOT_TOKEN:
        logging.error("No BOT_TOKEN provided! Exiting...")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve_payment))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("draw", draw_lottery))
    
    # Contact Handler
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Receipt Filter
    receipt_filter = filters.PHOTO | filters.Document.ALL | filters.TEXT
    app.add_handler(MessageHandler(receipt_filter & ~filters.COMMAND, handle_receipt))

    logging.info("Starting Bot Polling...")
    app.run_polling()

if __name__ == "__main__":
    main()

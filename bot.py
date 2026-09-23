import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN", "8833785126:AAHR0lV_4WevIgt0T7Pk-CaRztyMyvRsl1o")
ADMIN_ID = 6722504980  # Admin ID

TICKET_PRICE = "50 ብር"
TELEBIRR_NO = "0914197335 (Mulualem)"
BANK_NO = "1000723732108 (Addis Alemayehu - CBE)"
REFERRAL_BONUS = 10  # በአንድ ትኬት የቆረጠ ተጋባዥ የሚሰጥ ኮሚሽን (10 ብር)

# ከ1ኛ እስከ 10ኛ እጣ በምስሉ መሠረት የተስተካከለ የሽልማት ዝርዝር
PRIZES = {
    1: "💻 **1ኛ ዕጣ፦ Core i7, 11th Generation Laptop**",
    2: "📱 **2ኛ ዕጣ፦ Samsung A34**",
    3: "📲 **3ኛ ዕጣ፦ Tablet**",
    4: "💵 **4ኛ ዕጣ፦ 10,000 ብር**",
    5: "💵 **5ኛ ዕጣ፦ 5,000 ብር**",
    6: "💵 **6ኛ ዕጣ፦ 4,000 ብር**",
    7: "💵 **7ኛ ዕጣ፦ 3,000 ብር**",
    8: "💵 **8ኛ ዕጣ፦ 2,000 ብር**",
    9: "💵 **9ኛ ዕጣ፦ 1,500 ብር**",
    10: "💵 **10ኛ ዕጣ፦ 1,000 ብር**"
}

tickets = {}
user_phones = {}
user_names = {}
awaiting_phone = set()

# የሪፈራል መረጃዎችን መያዣ
referred_by = {}        # { user_id: referrer_id }
user_balances = {}      # { referrer_id: total_earned_amount }
successful_invites = {} # { referrer_id: count_of_buyers }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_names[user_id] = update.effective_user.first_name
    
    # ሪፈራል ሊንክ ይዘው ከገቡ
    if context.args:
        try:
            inviter_id = int(context.args[0])
            if inviter_id != user_id and user_id not in referred_by:
                referred_by[user_id] = inviter_id
        except ValueError:
            pass

    await update.message.reply_text(
        "👋 እንኳን ወደ ህዳሴ ሎተሪ በሰላም መጡ!\n\n"
        "ትዕዛዞች:\n"
        "/buy - የሎተሪ ትኬት ለመግዛት\n"
        "/prizes - የእጣዎቹን ሙሉ የሽልማት ዝርዝር ለማየት\n"
        "/myticket - የወሰዱትን ትኬት ለማየት\n"
        "/referral - የራስዎን የመጋበዣ ሊንክ ለማግኘት\n"
        "/mybalance - ያከማቹትን የኮሚሽን ብር ለማየት\n"
        "/draw - ዕጣ ለማውጣት (ለAdmin ብቻ)\n"
        "/alltickets - ሁሉንም የተሸጡ ትኬቶች ለማየት"
    )

async def show_prizes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "🎁 **የህዳሴ ሎተሪ የሽልማት ዝርዝር:**\n\n"
    for rank, prize in PRIZES.items():
        msg += f"{prize}\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def buy_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_names[user_id] = update.effective_user.first_name

    if user_id in tickets:
        await update.message.reply_text(f"እርስዎ አስቀድመው ትኬት ገዝተዋል! የትኬት ቁጥርዎ: {tickets[user_id]}")
        return

    awaiting_phone.add(user_id)
    await update.message.reply_text("📱 እባክዎን መጀመሪያ **የስልክ ቁጥርዎን** ያስገቡ (ለምሳሌ፦ 0911223344)፦")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id in awaiting_phone:
        user_phones[user_id] = text
        awaiting_phone.remove(user_id)

        msg = (
            f"✅ የስልክ ቁጥርዎ ({text}) ተመዝግቧል!\n\n"
            f"🎟 **የትኬት ዋጋ:** {TICKET_PRICE}\n\n"
            f"እባክዎን ክፍያውን በሚከተሉት ሂሳቦች ይላኩ:\n"
            f"📱 **ቴሌብር (Telebirr):** `{TELEBIRR_NO}`\n"
            f"🏦 **ንግድ ባንክ (CBE):** `{BANK_NO}`\n\n"
            f"📸 ክፍያውን እንደፈጸሙ **የደረሰኙን ፎቶ (Screenshot)** እዚህ ቦት ላይ ይላኩ።"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    user_names[user_id] = user_name

    if user_id in tickets:
        await update.message.reply_text(f"ትኬት ወስደዋል! የትኬት ቁጥርዎ: {tickets[user_id]}")
        return

    phone = user_phones.get(user_id, "አልተመዘገበም")

    await update.message.reply_text("⏳ የላኩት ደረሰኝ ደርሶናል! ክፍያው እንደተረጋገጠ የትኬት ቁጥርዎ ይላክልዎታል።")

    keyboard = [[InlineKeyboardButton("✅ ክፍያውን አረጋግጥ (Approve)", callback_data=f"approve_{user_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    inviter_id = referred_by.get(user_id)
    inviter_name = user_names.get(inviter_id, "ያልታወቀ") if inviter_id else None
    ref_info = f"\n🔗 **የተጋበዘው በ፦** {inviter_name} (ID: `{inviter_id}`)" if inviter_id else ""

    caption_text = (
        f"🔔 **አዲስ የክፍያ ጥያቄ!**\n"
        f"ተጠቃሚ: {user_name} (ID: `{user_id}`)"
        f"{ref_info}\n"
        f"📞 ስልክ ቁጥር: `{phone}`\n"
        f"እስካሁን የተሸጡ ትኬቶች: {len(tickets)}\n\n"
        f"ክፍያው መግባቱን አረጋግጠህ ከታች ያለውን ቁልፍ ተጫን።"
    )

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=file_id,
            caption=caption_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    elif update.message.document:
        file_id = update.message.document.file_id
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=file_id,
            caption=caption_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("approve_"):
        user_id = int(query.data.split("_")[1])

        if user_id in tickets:
            await query.edit_message_caption(caption=query.message.caption + "\n\n⚠️ ይህ ሰው አስቀድሞ ትኬት ተሰጥቶታል።")
            return

        ticket_number = random.randint(1000, 9999)
        tickets[user_id] = ticket_number

        buyer_name = user_names.get(user_id, "ተጠቃሚ")

        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ ክፍያዎ ተረጋግጧል!\nየእርስዎ የትኬት ቁጥር: **{ticket_number}**\nመልካም እድል!",
            parse_mode="Markdown"
        )

        # የኮሚሽን/ሪፈራል ቦነስ ማስላት
        inviter_id = referred_by.get(user_id)
        if inviter_id:
            user_balances[inviter_id] = user_balances.get(inviter_id, 0) + REFERRAL_BONUS
            successful_invites[inviter_id] = successful_invites.get(inviter_id, 0) + 1
            
            total_earned = user_balances[inviter_id]
            total_invites = successful_invites[inviter_id]
            inviter_name = user_names.get(inviter_id, "ተጋባዥ")
            inviter_phone = user_phones.get(inviter_id, "አልተመዘገበም")

            # 1. ለጋባዡ ሰው የሚላክ ማሳወቂያ
            try:
                await context.bot.send_message(
                    chat_id=inviter_id,
                    text=(
                        f"🎉 **እንኳን ደስ አለዎት!**\n\n"
                        f"እርስዎ የጋበዙት ደንበኛ ({buyer_name}) ትኬት ስለቆረጠ **{REFERRAL_BONUS} ብር** ኮሚሽን አግኝተዋል!\n"
                        f"👥 አጠቃላይ ያመጧቸው ሰዎች፦ **{total_invites}**\n"
                        f"💰 አጠቃላይ የሰራሁት ኮሚሽን፦ **{total_earned} ብር**"
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

            # 2. ለአድሚን የሚላክ ማሳወቂያ
            admin_ref_notice = (
                f"💰 **የኮሚሽን ክፍያ ማሳወቂያ!**\n\n"
                f"👤 **ጋባዥ (Referrer):** {inviter_name} (ID: `{inviter_id}`)\n"
                f"📞 **የጋባዥ ስልክ፦** `{inviter_phone}`\n"
                f"👤 **የተጋበዘው ትኬት ቆራጭ፦** {buyer_name}\n"
                f"💵 **የዚህ ዙር ኮሚሽን፦** {REFERRAL_BONUS} ብር\n"
                f"📊 **አጠቃላይ ያመጣቸው ሰዎች፦** {total_invites} ሰው\n"
                f"🏆 **አጠቃላይ የሰራው ኮሚሽን፦** **{total_earned} ብር**"
            )
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_ref_notice,
                parse_mode="Markdown"
            )

        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n✅ **ተረጋግጧል! የተሰጠው ትኬት፦ {ticket_number}**"
        )

async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
    earned = user_balances.get(user_id, 0)
    invites = successful_invites.get(user_id, 0)

    msg = (
        f"🔗 **የእርስዎ ልዩ የመጋበዣ (Referral) ሊንክ፦**\n"
        f"`{ref_link}`\n\n"
        f"📌 **ደንብ፦**\n"
        f"ይህንን ሊንክ ለጓደኞችዎ ያጋሩ! እያንዳንዱ ሰው በሊንክዎ ገብቶ የ 50 ብር ትኬት ሲቆርጥ **{REFERRAL_BONUS} ብር** ኮሚሽን ያገኛሉ።\n\n"
        f"📊 **የእርስዎ አጠቃላይ መረጃ፦**\n"
        f"• ያመጧቸው ሰዎች ብዛት፦ **{invites}**\n"
        f"• የሰራሁት አጠቃላይ ኮሚሽን፦ **{earned} ብር**"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    earned = user_balances.get(user_id, 0)
    invites = successful_invites.get(user_id, 0)
    
    await update.message.reply_text(
        f"💰 **የእርስዎ የኮሚሽን ሂሳብ፦**\n\n"
        f"• ትኬት የቆረጡ ተጋባዦች፦ **{invites}** ሰው\n"
        f"• አጠቃላይ የተቀበሉት ኮሚሽን፦ **{earned} ብር**",
        parse_mode="Markdown"
    )

async def draw_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("ይህ ትዕዛዝ ለአድሚን ብቻ የተፈቀደ ነው።")
        return

    if not tickets:
        await update.message.reply_text("ምንም የተመዘገበ ተወዳዳሪ የለም!")
        return

    all_users = list(tickets.keys())
    random.shuffle(all_users)

    num_winners = min(len(all_users), len(PRIZES))
    admin_summary = f"🎊 **የሎተሪ ዕጣው በስኬት ወጥቷል! ({num_winners} አሸናፊዎች):**\n\n"

    for idx in range(num_winners):
        uid = all_users[idx]
        rank = idx + 1
        won_prize = PRIZES[rank]
        t_num = tickets[uid]
        phone = user_phones.get(uid, "አልተጠቀሰም")

        user_msg = (
            f"🎉 እንኳን ደስ አለዎት ከህዳሴ ሎተሪ የ {won_prize} አሸናፊ ሆነዋል!\n"
            f"የወጣሎት ዕጣ ቁጥር: **{t_num}**\n"
            f"ሽልማቱን ለመረከብ በ **0914197335** ይደውሉ።"
        )

        try:
            await context.bot.send_message(chat_id=uid, text=user_msg, parse_mode="Markdown")
        except Exception:
            pass

        admin_summary += (
            f"🏆 {won_prize}\n"
            f"🎟 ትኬት: `{t_num}` | 📱 ስልክ: `{phone}` | ID: `{uid}`\n\n"
        )

    if len(all_users) > num_winners:
        loser_msg = (
            "ውድ ደንበኛችን እጣውን ስለቆረጡ እናመሰግናለን ።\n"
            "በዚህኛው ዙር አልተሳካም በቀጣዩ ዙር እንደሚሳካልዎት ተስፋ እናደርጋለን ።"
        )
        for idx in range(num_winners, len(all_users)):
            l_uid = all_users[idx]
            try:
                await context.bot.send_message(chat_id=l_uid, text=loser_msg)
            except Exception:
                pass

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_summary,
        parse_mode="Markdown"
    )

async def my_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in tickets:
        await update.message.reply_text(f"የእርስዎ ትኬት ቁጥር: {tickets[user_id]}")
    else:
        await update.message.reply_text("እስካሁን ምንም ትኬት አልገዙም። ለመግዛት /buy ይበሉ።")

async def all_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not tickets:
        await update.message.reply_text("እስካሁን የተሸጠ ትኬት የለም።")
        return

    text = f"📋 **የተሸጡ ትኬቶች (አጠቃላይ: {len(tickets)}):**\n\n"
    for uid, tnum in tickets.items():
        phone = user_phones.get(uid, "የለም")
        text += f"• User ID: `{uid}` | ስልክ: `{phone}` -> ትኬት: **{tnum}**\n"

    await update.message.reply_text(text, parse_mode="Markdown")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("prizes", show_prizes))
    app.add_handler(CommandHandler("buy", buy_ticket))
    app.add_handler(CommandHandler("myticket", my_ticket))
    app.add_handler(CommandHandler("referral", referral_cmd))
    app.add_handler(CommandHandler("mybalance", my_balance))
    app.add_handler(CommandHandler("draw", draw_winner))
    app.add_handler(CommandHandler("alltickets", all_tickets))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_receipt))
    app.add_handler(CallbackQueryHandler(button_click))

    print("ቦቱ መስራት ጀምሯል...")
    app.run_polling()

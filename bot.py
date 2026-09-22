import os
import secrets

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6722504980

TICKET_PRICE = 50
REFERRAL_COMMISSION = 5

TELEBIRR_NO = "0914197335 (Mulualem)"
BANK_NO = "1000723732108 (Addis Alemayehu - CBE)"

# =========================
# 10 የሽልማት ዝርዝር
# =========================

PRIZES = {
    1: "💻 Core i7, 11th Generation Laptop",
    2: "📱 Samsung A34",
    3: "📲 Tablet",
    4: "💵 10,000 ብር",
    5: "💵 5,000 ብር",
    6: "💵 4,000 ብር",
    7: "💵 3,000 ብር",
    8: "💵 2,000 ብር",
    9: "💵 1,500 ብር",
    10: "💵 1,000 ብር",
}

# =========================
# የBot መረጃ
# =========================

tickets = {}
user_phones = {}
awaiting_phone = set()

# user_id -> referrer_id
referrals = {}

# user_id -> commission balance
balances = {}


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Referral link
    if context.args:
        try:
            referrer_id = int(context.args[0])

            if referrer_id != user_id and user_id not in referrals:
                referrals[user_id] = referrer_id

        except ValueError:
            pass

    await update.message.reply_text(
        "👋 እንኳን ወደ ህዳሴ ሎተሪ በሰላም መጡ!\n\n"
        "🎟 የትኬት ዋጋ: 50 ብር\n\n"
        "ትዕዛዞች:\n"
        "/buy - ትኬት ለመግዛት\n"
        "/prizes - የሽልማት ዝርዝር\n"
        "/myticket - የትኬት ቁጥር\n"
        "/balance - የኮሚሽን ቀሪ ሂሳብ\n"
        "/referral - የእርስዎን referral link ለማግኘት"
    )


# =========================
# PRIZES
# =========================

async def show_prizes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "🎁 **የህዳሴ ሎተሪ የሽልማት ዝርዝር**\n\n"

    for rank, prize in PRIZES.items():
        msg += f"🏆 **{rank}ኛ እጣ:** {prize}\n"

    await update.message.reply_text(
        msg,
        parse_mode="Markdown"
    )


# =========================
# REFERRAL LINK
# =========================

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    me = await context.bot.get_me()

    link = f"https://t.me/{me.username}?start={user_id}"

    await update.message.reply_text(
        "🔗 **የእርስዎ Referral Link**\n\n"
        f"{link}\n\n"
        "ይህን link ለሌሎች ሰዎች ላክ።\n"
        "እነሱ በዚህ link በኩል ገብተው ትኬት ከገዙ፣ "
        "5 ብር commission ይጨመርልዎታል።",
        parse_mode="Markdown"
    )


# =========================
# BALANCE
# =========================

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    amount = balances.get(user_id, 0)

    await update.message.reply_text(
        f"💰 **የእርስዎ Commission Balance:** {amount} ብር",
        parse_mode="Markdown"
    )


# =========================
# BUY
# =========================

async def buy_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in tickets:
        await update.message.reply_text(
            f"እርስዎ አስቀድመው ትኬት ገዝተዋል።\n"
            f"🎟 ትኬት ቁጥር: {tickets[user_id]}"
        )
        return

    awaiting_phone.add(user_id)

    await update.message.reply_text(
        "📱 እባክዎን የስልክ ቁጥርዎን ያስገቡ።\n\n"
        "ለምሳሌ፦ 0911223344"
    )


# =========================
# PHONE + PAYMENT
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in awaiting_phone:
        return

    text = update.message.text.strip()

    user_phones[user_id] = text
    awaiting_phone.remove(user_id)

    msg = (
        f"✅ የስልክ ቁጥርዎ ({text}) ተመዝግቧል!\n\n"
        f"🎟 **የትኬት ዋጋ: {TICKET_PRICE} ብር**\n\n"
        f"📱 **Telebirr:** `{TELEBIRR_NO}`\n"
        f"🏦 **CBE:** `{BANK_NO}`\n\n"
        "📸 ክፍያውን ከፈጸሙ በኋላ "
        "የደረሰኙን Screenshot እዚህ ይላኩ።"
    )

    await update.message.reply_text(
        msg,
        parse_mode="Markdown"
    )


# =========================
# RECEIPT
# =========================

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    if user_id in tickets:
        await update.message.reply_text(
            f"አስቀድመው ትኬት ወስደዋል።\n"
            f"🎟 {tickets[user_id]}"
        )
        return

    phone = user_phones.get(
        user_id,
        "አልተመዘገበም"
    )

    await update.message.reply_text(
        "⏳ ደረሰኝዎ ደርሶናል።\n"
        "ክፍያው ከተረጋገጠ በኋላ ትኬትዎ ይላክልዎታል።"
    )

    keyboard = [[
        InlineKeyboardButton(
            "✅ ክፍያውን አረጋግጥ",
            callback_data=f"approve_{user_id}"
        )
    ]]

    reply_markup = InlineKeyboardMarkup(keyboard)

    caption = (
        "🔔 **አዲስ የክፍያ ጥያቄ!**\n\n"
        f"👤 ተጠቃሚ: {user_name}\n"
        f"🆔 ID: `{user_id}`\n"
        f"📞 ስልክ: `{phone}`\n"
        f"🎟 የተሸጡ ትኬቶች: {len(tickets)}\n"
    )

    if update.message.photo:

        file_id = update.message.photo[-1].file_id

        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

    elif update.message.document:

        file_id = update.message.document.file_id

        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )


# =========================
# APPROVE PAYMENT
# =========================

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    if not query.data.startswith("approve_"):
        return

    # Admin ብቻ
    if query.from_user.id != ADMIN_ID:
        await query.answer(
            "ይህ ቁልፍ Admin ብቻ ነው።",
            show_alert=True
        )
        return

    user_id = int(
        query.data.split("_")[1]
    )

    if user_id in tickets:

        await query.edit_message_caption(
            caption=(
                query.message.caption +
                "\n\n⚠️ ይህ ተጠቃሚ አስቀድሞ "
                "ትኬት ተሰጥቶታል።"
            )
        )

        return

    # 1000 - 9999 ticket number
    ticket_number = secrets.randbelow(9000) + 1000

    tickets[user_id] = ticket_number

    # =========================
    # REFERRAL COMMISSION
    # =========================

    referrer_id = referrals.get(user_id)

    if referrer_id and referrer_id != user_id:

        balances[referrer_id] = (
            balances.get(referrer_id, 0)
            + REFERRAL_COMMISSION
        )

        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    "🎉 Referral Commission!\n\n"
                    f"አንድ ሰው በእርስዎ referral link "
                    f"ትኬት ገዝቷል።\n\n"
                    f"💰 +{REFERRAL_COMMISSION} ብር\n"
                    f"💳 አጠቃላይ Balance: "
                    f"{balances[referrer_id]} ብር"
                )
            )
        except Exception:
            pass

    # User notification
    await context.bot.send_message(
        chat_id=user_id,
        text=(
            "✅ **ክፍያዎ ተረጋግጧል!**\n\n"
            f"🎟 የትኬት ቁጥርዎ: "
            f"**{ticket_number}**\n\n"
            "መልካም እድል! 🎉"
        ),
        parse_mode="Markdown"
    )

    # Admin message
    commission_text = ""

    if referrer_id:
        commission_text = (
            f"\n💰 Referral Commission: "
            f"+{REFERRAL_COMMISSION} ብር\n"
            f"👤 Referrer ID: `{referrer_id}`"
        )

    await query.edit_message_caption(
        caption=(
            query.message.caption +
            f"\n\n✅ **ተረጋግጧል!**\n"
            f"🎟 ትኬት: **{ticket_number}**"
            f"{commission_text}"
        ),
        parse_mode="Markdown"
    )


# =========================
# MY TICKET
# =========================

async def my_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id in tickets:

        await update.message.reply_text(
            f"🎟 የእርስዎ ትኬት ቁጥር: "
            f"**{tickets[user_id]}**",
            parse_mode="Markdown"
        )

    else:

        await update.message.reply_text(
            "እስካሁን ትኬት አልገዙም።\n"
            "ለመግዛት /buy ይጻፉ።"
        )


# =========================
# DRAW
# =========================

async def draw_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ ይህ ትዕዛዝ Admin ብቻ ነው።"
        )

        return

    if not tickets:

        await update.message.reply_text(
            "ምንም የተመዘገበ ትኬት የለም።"
        )

        return

    users = list(tickets.keys())

    # የአሸናፊዎች ብዛት = 10 ወይም ያሉት ተወዳዳሪዎች
    number_of_winners = min(
        len(users),
        len(PRIZES)
    )

    # Secure random shuffle
    winners = secrets.SystemRandom().sample(
        users,
        number_of_winners
    )

    admin_message = (
        "🎊 **የሎተሪ ዕጣ ውጤት**\n\n"
    )

    for index, user_id in enumerate(winners):

        rank = index + 1

        prize = PRIZES[rank]

        ticket_number = tickets[user_id]

        phone = user_phones.get(
            user_id,
            "አልተጠቀሰም"
        )

        # Winner notification
        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🎉🎉 **እንኳን ደስ አለዎት!** 🎉🎉\n\n"
                    f"🏆 **{rank}ኛ እጣ**\n"
                    f"🎁 {prize}\n\n"
                    f"🎟 የትኬት ቁጥር: "
                    f"**{ticket_number}**\n\n"
                    "ሽልማቱን ለመረከብ "
                    "በ 0914197335 ይደውሉ።"
                ),
                parse_mode="Markdown"
            )

        except Exception:
            pass

        admin_message += (
            f"🏆 **{rank}ኛ:** {prize}\n"
            f"🎟 ትኬት: `{ticket_number}`\n"
            f"📱 ስልክ: `{phone}`\n"
            f"🆔 ID: `{user_id}`\n\n"
        )

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_message,
        parse_mode="Markdown"
    )


# =========================
# ALL TICKETS
# =========================

async def all_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Admin ብቻ ነው።"
        )

        return

    if not tickets:

        await update.message.reply_text(
            "እስካሁን ትኬት የለም።"
        )

        return

    text = (
        f"📋 **የተሸጡ ትኬቶች**\n"
        f"አጠቃላይ: {len(tickets)}\n\n"
    )

    for user_id, ticket_number in tickets.items():

        phone = user_phones.get(
            user_id,
            "የለም"
        )

        text += (
            f"🆔 `{user_id}`\n"
            f"📱 {phone}\n"
            f"🎟 {ticket_number}\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="Markdown"
    )


# =========================
# ADMIN COMMISSION
# =========================

async def commissions(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Admin ብቻ ነው።"
        )

        return

    total_commission = sum(
        balances.values()
    )

    await update.message.reply_text(
        "📊 **Commission Report**\n\n"
        f"👥 Referrers: {len(balances)}\n"
        f"💰 አጠቃላይ Commission: "
        f"{total_commission} ብር",
        parse_mode="Markdown"
    )


# =========================
# MAIN
# =========================

def main():

    if not TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable አልተገኘም።"
        )

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("prizes", show_prizes)
    )

    app.add_handler(
        CommandHandler("buy", buy_ticket)
    )

    app.add_handler(
        CommandHandler("myticket", my_ticket)
    )

    app.add_handler(
        CommandHandler("referral", referral)
    )

    app.add_handler(
        CommandHandler("balance", balance)
    )

    app.add_handler(
        CommandHandler("draw", draw_winner)
    )

    app.add_handler(
        CommandHandler("alltickets", all_tickets)
    )

    app.add_handler(
        CommandHandler("commissions", commissions)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.Document.ALL,
            handle_receipt
        )
    )

    app.add_handler(
        CallbackQueryHandler(button_click)
    )

    print("ቦቱ መስራት ጀምሯል...")

    app.run_polling()


if __name__ == "__main__":
    main()

import os
import sys
import time
import re
import random
import logging
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackContext, CallbackQueryHandler
)

# ✅ Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# ✅ Environment Variables
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
CHANNEL_ID = os.getenv("CHANNEL_ID")

# ✅ Global Variables
start_time = time.time()
allowed_users = {OWNER_ID}
pending_apks = {}
pending_shares = {}

# ✅ Startup Messages
STARTUP_MESSAGES = [
    "👑 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 𝗕𝗮𝗰𝗸, 𝗕𝗼𝘀𝘀.!!",
    "🔥 𝗧𝗵𝗲 𝗞𝗶𝗻𝗴 𝗛𝗮𝘀 𝗔𝗿𝗿𝗶𝘃𝗲𝗱.!!",
    "🚀 𝗥𝗲𝗮𝗱𝘆 𝗳𝗼𝗿 𝗔𝗰𝗧𝗶𝗼𝗻, 𝗠𝗮𝘀𝘁𝗲𝗿.?",
    "⚡ 𝗣𝗼𝘄𝗲𝗿𝗶𝗻𝗴 𝗨𝗽 𝗳𝗼𝗿 𝗬𝗼𝘂!?",
    "💎 𝗬𝗼𝘂𝗿 𝗖𝗼𝗺𝗺𝗮𝗻𝗱𝘀, 𝗬𝗼𝘂𝗿 𝗥𝘂𝗹𝗲𝘀.!!",
    "🌟 𝗢𝗻𝗹𝗶𝗻𝗲 & 𝗔𝘁 𝗬𝗼𝘂𝗿 𝗦𝗲𝗿𝘃𝗶𝗰𝗲.!!",
    "🎯 𝗟𝗼𝗰𝗸𝗲𝗱 & 𝗟𝗼𝗮𝗱𝗲𝗱, 𝗕𝗼𝘀𝘀.!!"
]

TEMPLATE_CAPTION = """*Key* -

BUY:-
```@PRASTUTKARTA```

FEEDBACK:-
```@PRASTUTKARTA```
"""

# ✅ /start
async def start(update: Update, context: CallbackContext):
    if update.effective_user.id not in allowed_users:
        return
    await update.message.reply_text(random.choice(STARTUP_MESSAGES), parse_mode="Markdown")

# ✅ /ping
async def ping(update: Update, context: CallbackContext):
    if update.effective_user.id not in allowed_users:
        return

    current_date = datetime.datetime.now().strftime("%d:%m:%Y")
    total_seconds = int(time.time() - start_time)
    uptime = f"{total_seconds // 86400}D : {(total_seconds % 86400) // 3600}H : {(total_seconds % 3600) // 60}M : {total_seconds % 60}S"
    response_time = round((time.time() - update.message.date.timestamp()) * 1000)

    await update.message.reply_text(
        f"🏓 𝗣𝗼𝗻𝗴!\n\n📅 **Update**: {current_date}\n⏳ **Uptime**: {uptime}\n⚡ **Ping**: {response_time} ms",
        parse_mode="Markdown"
    )

# ✅ /adduser
async def adduser(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        return
    try:
        user_id = int(context.args[0])
        allowed_users.add(user_id)
        await update.message.reply_text(f"✅ User `{user_id}` added!", parse_mode="Markdown")
    except:
        await update.message.reply_text("⚠️ Usage: /adduser 1234567890", parse_mode="Markdown")

# ✅ /removeuser
async def removeuser(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        return
    try:
        user_id = int(context.args[0])
        allowed_users.discard(user_id)
        await update.message.reply_text(f"🚫 User `{user_id}` removed!", parse_mode="Markdown")
    except:
        await update.message.reply_text("⚠️ Usage: /removeuser 1234567890", parse_mode="Markdown")

# ✅ /userlist
async def userlist(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        return

    text = "**👥 Registered Users:**\n\n"
    for user_id in allowed_users:
        try:
            user = await context.bot.get_chat(user_id)
            username = f"@{user.username}" if user.username else "❌ No Username"
            nickname = user.username or str(user_id)
            text += f"👤 **Username:** {username}\n🆔 **User ID:** `{user_id}`\n🏷 **Nickname:** `{nickname}`\n\n"
        except:
            text += f"⚠️ Error fetching user `{user_id}`\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ✅ Unauthorized users
async def unauthorized(update: Update, context: CallbackContext):
    await update.message.reply_text("🚀𝗪𝗵𝗮𝘁 𝗕𝗿𝘂𝗵 , 𝗜𝘁❜𝘀 𝗩𝗲𝗿𝘆 𝗪𝗿𝗼𝗻𝗴 𝗕𝗿𝗼 😂")

# ✅ APK Upload
async def apk_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in allowed_users:
        return

    doc = update.message.document
    if doc.mime_type == "application/vnd.android.package-archive":
        caption = update.message.caption or ""
        match = re.search(r'Key - (.+)', caption)
        if match:
            await send_apk_with_key(update, context, doc.file_id, match.group(1))
        else:
            pending_apks[user_id] = doc.file_id
            await update.message.reply_text("⏳ Send the key now!")

# ✅ Key Handler
async def text_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in allowed_users:
        return

    if user_id in pending_apks:
        file_id = pending_apks.pop(user_id)
        await send_apk_with_key(update, context, file_id, update.message.text)
    else:
        await update.message.reply_text("⚠️ Please send the APK first!")

# ✅ Send APK with Caption
async def send_apk_with_key(update, context, file_id, key):
    if not key.strip():
        await update.message.reply_text("⚠️ No key provided!")
        return

    caption = TEMPLATE_CAPTION.format(key)
    sent = await update.message.reply_document(file_id, caption=caption, parse_mode="Markdown")

    pending_shares[sent.message_id] = (file_id, key)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes", callback_data=f"share_yes|{sent.message_id}"),
         InlineKeyboardButton("❌ No", callback_data=f"share_no|{sent.message_id}")]
    ])
    await update.message.reply_text("📢 Share to the channel?", reply_markup=keyboard)

# ✅ Callback Share
async def share_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in allowed_users:
        return

    data = query.data.split("|")
    action, msg_id = data[0], int(data[1])

    if action == "share_yes":
        if msg_id in pending_shares:
            file_id, key = pending_shares.pop(msg_id)
            caption = TEMPLATE_CAPTION.format(key)
            await context.bot.send_document(CHANNEL_ID, file_id, caption=caption, parse_mode="Markdown")
            await query.edit_message_text("✅ Shared Successfully!")
    else:
        pending_shares.pop(msg_id, None)
        await query.edit_message_text("❌ Declined!")

# ✅ Main Bot
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("adduser", adduser))
    app.add_handler(CommandHandler("removeuser", removeuser))
    app.add_handler(CommandHandler("userlist", userlist))

    app.add_handler(MessageHandler(filters.Document.ALL, apk_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(share_callback, pattern="share_"))

    app.add_handler(MessageHandler(filters.ALL, unauthorized))  # fallback

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
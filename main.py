import json
import time
import datetime
import random
import os
import re
import traceback
import asyncio
from telegram.error import BadRequest
from telegram.constants import ParseMode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, InputMediaDocument
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Get token from Railway environment
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set")

# Load config
with open("config.json") as f:
    config = json.load(f)

OWNER_ID = config["owner_id"]
ALLOWED_USERS = set(config["allowed_users"])
USER_DATA = config["user_data"]

# Load new setups
AUTO_SETUP = config.get("auto_setup", {
    "setup1": {"source_channel": "", "dest_channel": "", "dest_caption": "", "completed_count": 0},
    "setup2": {"source_channel": "", "dest_channel": "", "dest_caption": "", "completed_count": 0},
    "setup3": {"source_channel": "", "dest_channel": "", "dest_caption": "", "completed_count": 0}
})

START_TIME = time.time()
USER_STATE = {}  # Tracks per-user upload state

owner_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Userlist"), KeyboardButton("Help")],
        [KeyboardButton("Ping"), KeyboardButton("Rules")],
        [KeyboardButton("Reset")],
        [KeyboardButton("On"), KeyboardButton("Off")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
    )

allowed_user_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Help")],
        [KeyboardButton("Ping"), KeyboardButton("Rules")],
        [KeyboardButton("Reset")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
    )

def save_config():
    with open("config.json", "w") as f:
        json.dump({
            "owner_id": OWNER_ID,
            "allowed_users": list(ALLOWED_USERS),
            "user_data": USER_DATA,
            "auto_setup": AUTO_SETUP
        }, f, indent=4)

def is_authorized(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ALLOWED_USERS
    
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text(
            "⛔ You are not authorized!\n"
            "📞 Must contact the owner.\n\n"
            "🛠️ Build by: @CeoDarkFury"
        )
        return

    # Initialize or Reset user state
    USER_STATE[user_id] = {
        "current_method": None,
        "status": "selecting_method",
        "session_files": [],
        "saved_key": None,
        "apk_posts": [],
        "waiting_key": False,
        "last_apk_time": None,
        "last_post_link": None,
        "preview_message_id": None
    }

    keyboard = [
        [InlineKeyboardButton("⚡ Method 1", callback_data="method_1")],
        [InlineKeyboardButton("🚀 Method 2", callback_data="method_2")]
    ]

    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Please select your working method:\n\n"
        "⚡ *Method 1:* Manual Key Capture.\n"
        "🚀 *Method 2:* Upload 2-3 APKs together, then Capture One Key.\n\n"
        "_You can change method anytime later._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id == OWNER_ID:
        keyboard = [
            [InlineKeyboardButton("➡️ Next", callback_data="help_next")]
        ]
        await update.message.reply_text(
            "🛠 *Manual Upload Commands:*\n\n"
            "➔ /start - Restart bot interaction\n"
            "➔ /setchannelid - Set Upload Channel\n"
            "➔ /setcaption - Set Upload Caption\n"
            "➔ /resetcaption - Reset Caption\n"
            "➔ /resetchannelid - Reset Channel\n"
            "➔ /reset - Full Reset\n\n"
            "➔ /adduser - Add Allowed User\n"
            "➔ /removeuser - Remove User\n"
            "➔ /userlist - List Users\n"
            "➔ /ping - Bot Status\n"
            "➔ /rules - Bot Rules\n",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif user_id in ALLOWED_USERS:
        await update.message.reply_text(
            "🛠*Available Commands:*\n\n"
            "/start - Restart bot interaction ▶️\n"
            "/ping - Bot status 🏓\n"
            "/rules - Bot rules 📜\n"
            "/reset - Reset your data ♻️\n"
            "/resetcaption - Clear your saved caption 🧹\n"
            "/resetchannelid - Clear your channel ID 🔁\n"
            "/setchannelid - Set your Channel ID 📡\n"
            "/setcaption - Set your Caption ✍️",
            parse_mode="Markdown"
        )

    else:
        await update.message.reply_text("❌ You are not allowed to use this bot.")
        
async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("𝖮𝗍𝗁𝖺 𝖡𝖺𝖺𝖽𝗎 🫵🏼. 𝖢𝗈𝗇𝗍𝖺𝖼𝗍 𝖸𝗈𝗎𝗋 𝖺𝖽𝗆𝗂𝗇 @Ceo_DarkFury 🌝")
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ *Oops\\!* You forgot to give a user ID\\.\n\nTry like this:\n`/adduser \\<user_id\\>` ✍️",
            parse_mode="MarkdownV2"
        )
        return        

    try:
        user_id = int(context.args[0])
        ALLOWED_USERS.add(user_id)
        save_config()
        await update.message.reply_text(f"✅ User `{user_id}` added successfully!", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("Hmm... that doesn't look like a valid user ID. Try a number! 🔢")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🗣️𝖳𝗁𝗂𝗋𝗎𝗆𝖻𝗂 𝖯𝖺𝖺𝗋𝗎𝖽𝖺 𝖳𝗁𝖾𝗏𝖽𝗂𝗒𝖺 𝖯𝖺𝗂𝗒𝖺")
        return

    if not context.args:
        await update.message.reply_text(
            "📝 *Usage:* `/removeuser` \\<user\\_id\\>\\ Don\\'t leave me hanging\\!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    try:
        user_id = int(context.args[0])
        ALLOWED_USERS.discard(user_id)
        save_config()
        await update.message.reply_text(
            f"👋 *User* `{user_id}` *has been kicked out of the VIP list!* 🚪💨",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ That doesn't look like a valid user ID. Numbers only, please! 🔢")

async def userlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("𝖮𝗋𝗎𝗎 𝗉𝖺𝗂𝗒𝖺𝗌𝖺𝗏𝗎𝗄𝗄𝗎🥴 𝖯𝗎𝗋𝖺𝗃𝖺𝗇𝖺𝗆 𝗂𝗅𝖺 𝖽𝖺𝖺 𝗉𝗎𝗇𝖽𝖺 🫵🏼")
        return

    if not ALLOWED_USERS:
        await update.message.reply_text("No allowed users.")
        return

    lines = [f"🧾 <b>Total Allowed Users:</b> {len(ALLOWED_USERS)}\n"]
    for index, user_id in enumerate(ALLOWED_USERS, start=1):
        user_data = USER_DATA.get(str(user_id), {})
        nickname = user_data.get("first_name", "—")
        username = user_data.get("username", "—")
        channel = user_data.get("channel", "—")

        lines.append(
            f"📌 <b>User {index}</b>\n"
            f"├─ 👤 <b>Name:</b> {nickname}\n"
            f"├─ 🧬 <b>Username:</b> {'@' + username if username != '—' else '—'}\n"
            f"├─ 📡 <b>Channel:</b> {channel}\n"
            f"└─ 🆔 <b>ID:</b> <a href=\"tg://openmessage?user_id={user_id}\">{user_id}</a>\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
    
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("𝖵𝖺𝗇𝗍𝗁𝖺 𝗈𝖽𝖺𝗇𝖾 𝖮𝗆𝖻𝗎𝗍𝗁𝖺 𝖽𝖺𝖺 𝖻𝖺𝖺𝖽𝗎🫂")
        return

    uptime_seconds = int(time.time() - START_TIME)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    ping_ms = round(random.uniform(10, 80), 2)
    today = datetime.datetime.now().strftime("%d:%m:%Y")

    msg = (
        "🏓 <b>𝗣𝗼𝗻𝗴!</b>\n\n"
        f"    📅 <b>Update:</b> {today}\n"
        f"    ⏳ <b>Uptime:</b> {days}D : {hours}H : {minutes}M : {seconds}S\n"
        f"    ⚡ <b>Ping:</b> {ping_ms} ms"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("😶‍🌫️𝖮𝗈𝗆𝖻𝗎𝗎𝗎 𝖣𝖺𝖺 𝗍𝗁𝖺𝗒𝖺𝗅𝗂", parse_mode="Markdown")
        return

    await update.message.reply_text(
        "📜 *Bot Rules of Engagement:*\n\n"
        "1️⃣ Please *don't spam* the bot — it's got feelings too! 🤖💔\n"
        "2️⃣ Any violations may result in a *banhammer* drop without warning! 🔨🚫\n\n"
        "💬 *Need help? Got feedback?*\nSlide into the DMs: [@Ceo_DarkFury](https://t.me/Ceo_DarkFury)",
        parse_mode="Markdown"
    )
    
async def reset_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("🫥𝖭𝖺𝖺𝗇𝗍𝗁𝖺𝗇 𝖽𝖺𝖺 𝗅𝖾𝗈𝗈")
        return

    USER_DATA[str(user_id)]["caption"] = ""
    save_config()
    await update.message.reply_text(
        "🧼 *Caption Cleared\\!* \nReady for a fresh start\\? ➕\nUse /SetCaption to drop a new vibe 🎯",
        parse_mode="MarkdownV2"
    )
    
async def reset_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("🗣️𝖮𝗈𝗆𝖻𝗎𝗎𝗎")
        return

    USER_DATA[str(user_id)]["channel"] = ""
    save_config()
    await update.message.reply_text(
        "📡 *Channel ID wiped\\!* ✨\nSet new one: /setchannelid 🛠️🚀",
        parse_mode="MarkdownV2"
    )
    
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("🗣️𝖮𝗈𝗆𝖻𝗎𝗎𝗎")
        return

    for user_id in USER_DATA:
        USER_DATA[user_id]["channel"] = ""
        USER_DATA[user_id]["caption"] = ""
    save_config()
    
    await update.message.reply_text(
        "🧹 *Cleaned up\\!*\n"
        "No more caption or channel\\. 🚮\n"
        "Ready to Setup\\. 🚀",
        parse_mode="MarkdownV2"
    )
    
async def set_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("🗣️ 𝖮𝗈𝗆𝖻𝗎𝗎𝗎")
        return

    USER_STATE[user_id] = {"status": "waiting_channel"}
    await update.message.reply_text(
        "🔧 *Setup Time\\!*\n"
        "Send me your Channel ID now\\. 📡\n"
        "Format: `@yourchannel` or `\\-100xxxxxxxxxx`",
        parse_mode="MarkdownV2"
    )
    
async def set_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("𝖮𝗈𝗆𝖻𝗎𝗎𝗎 😭")
        return

    USER_STATE[user_id] = {"status": "waiting_caption"}
    await update.message.reply_text(
        "📝 *Caption Time\\!*\n"
        "Send me your Caption Including\\. ↙️\n"
        "The Placeholder `Key \\-` 🔑",
        parse_mode="MarkdownV2"
    )
    
# First, in handle_document() where APK is received:
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text(
            "⛔ You are not authorized!\n"
            "📞 Must contact the owner.\n\n"
            "🛠️ Build by: @CeoDarkFury"
        )
        return

    document = update.message.document
    file_id = document.file_id
    file_name = document.file_name or ""

    # --- ✅ Only allow APK files ---
    if not file_name.lower().endswith(".apk"):
        await update.message.reply_text(
            "🛑 *Only APK files are allowed!*\n\n"
            "This file type is not supported.",
            parse_mode="Markdown"
        )
        return

    # --- Now continue with your logic ---
    state = USER_STATE.get(user_id)
    if not state or not state.get("current_method"):
        keyboard = [
            [InlineKeyboardButton("⚡ Choose Method", callback_data="back_to_methods")]
        ]
        await update.message.reply_text(
            "⚠️ *You didn't select any Method yet!*\n\n"
            "Please select Method 1 or Method 2 first.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    method = state.get("current_method")
    
    if method == "method1":
        await process_method1_apk(update, context)
        return

    elif method == "method2":
        await process_method2_apk(update, context)
        return

async def process_method1_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document
    caption = update.message.caption or ""

    match = re.search(r'Key\s*-\s*(\S+)', caption)
    if match:
        key = match.group(1)

        user_info = USER_DATA.get(str(user_id), {})
        saved_caption = user_info.get("caption", "")
        channel_id = user_info.get("channel", "")

        if not saved_caption or not channel_id:
            await update.message.reply_text(
                "⚠️ *Please setup your Channel and Caption first!*",
                parse_mode="Markdown"
            )
            return

        final_caption = saved_caption.replace("Key -", f"Key - <code>{key}</code>")
        await context.bot.send_document(
            chat_id=channel_id,
            document=doc.file_id,
            caption=final_caption,
            parse_mode="HTML"
        )
        await update.message.reply_text("✅ *APK posted successfully!*", parse_mode="Markdown")

    else:
        # If key missing, ask to send key manually
        USER_STATE[user_id]["waiting_key"] = True
        USER_STATE[user_id]["file_id"] = doc.file_id
        await update.message.reply_text("⏳ *Send the Key now!*", parse_mode="Markdown")

async def process_method2_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document
    file_id = doc.file_id
    file_name = doc.file_name or ""

    state = USER_STATE.setdefault(user_id, {})
    session_files = state.setdefault("session_files", [])
    session_filenames = state.setdefault("session_filenames", [])

    # Save the file
    session_files.append(file_id)
    session_filenames.append(file_name)

    # Progress message handling (same as your current)
    message_id = state.get("progress_message_id")
    chat_id = update.message.chat_id

    if message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"✅ {len(session_files)} APKs Received! ☑️\nWaiting 5 seconds for next APK...",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Error editing progress message: {e}")
            message_id = None

    if not message_id:
        sent_msg = await update.message.reply_text(
            f"✅ {len(session_files)} APKs Received! ☑️\nWaiting 5 seconds for next APK...",
            parse_mode="Markdown"
        )
        state["progress_message_id"] = sent_msg.message_id

    USER_STATE[user_id]["last_apk_time"] = time.time()

    context.application.create_task(countdown_and_check(user_id, chat_id, context))

async def method2_send_to_channel(user_id, context):
    user_info = USER_DATA.get(str(user_id), {})
    channel_id = user_info.get("channel")
    saved_caption = user_info.get("caption")
    state = USER_STATE.get(user_id, {})

    session_files = state.get("session_files", [])
    key = state.get("saved_key", "")
    key_mode = state.get("key_mode", "normal")

    if not channel_id or not saved_caption or not session_files or not key:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ <b>Session Data Missing! Please /start again.</b>",
            parse_mode="HTML"
        )
        return

    posted_ids = []
    last_message = None

    for idx, file_id in enumerate(session_files, start=1):
        is_last_apk = (idx == len(session_files))
    
        if key_mode == "quote":
            if len(session_files) == 1 or is_last_apk:
                # Only 1 APK or last APK
                caption = saved_caption.replace("Key -", f"<blockquote>Key - <code>{key}</code></blockquote>")
            else:
                # Middle APKs
                caption = f"<blockquote>Key - <code>{key}</code></blockquote>"
    
        elif key_mode == "mono":
            if len(session_files) == 1 or is_last_apk:
                caption = saved_caption.replace("Key -", f"Key - <code>{key}</code>")
            else:
                caption = f"Key - <code>{key}</code>"
    
        else:  # normal
            if len(session_files) == 1 or is_last_apk:
                caption = saved_caption.replace("Key -", f"Key - {key}")
            else:
                caption = f"Key - {key}"

        sent_message = await context.bot.send_document(
            chat_id=channel_id,
            document=file_id,
            caption=caption,
            parse_mode="HTML"
        )
        posted_ids.append(sent_message.message_id)
        last_message = sent_message

    USER_STATE[user_id]["apk_posts"] = posted_ids

    if len(posted_ids) == 1:
        # 1 APK posted - Session ends quietly
        USER_STATE[user_id]["session_files"] = []
        USER_STATE[user_id]["session_filenames"] = []
        USER_STATE[user_id]["saved_key"] = None
        USER_STATE[user_id]["waiting_key"] = False
        USER_STATE[user_id]["last_apk_time"] = None
        USER_STATE[user_id]["key_mode"] = "normal"
        # DO NOT touch current_method or status
    else:
        # 2-3 APKs, wait for auto recaption
        USER_STATE[user_id]["session_files"] = session_files
        USER_STATE[user_id]["waiting_key"] = False
        USER_STATE[user_id]["last_apk_time"] = None

    if last_message:
        if channel_id.startswith("@"):
            post_link = f"https://t.me/{channel_id.strip('@')}/{last_message.message_id}"
        elif channel_id.startswith("-100"):
            post_link = f"https://t.me/c/{channel_id.replace('-100', '')}/{last_message.message_id}"
        else:
            post_link = "Unknown"

        USER_STATE[user_id]["last_post_link"] = post_link

    buttons = [[InlineKeyboardButton("📄 View Last Post", url=post_link)]]

    if len(posted_ids) >= 2:
        buttons.append([InlineKeyboardButton("✏️ Auto Re-Caption", callback_data="auto_recaption")])

    buttons.append([InlineKeyboardButton("🗑️ Delete APK Post", callback_data="delete_apk_post")])
    buttons.append([InlineKeyboardButton("🔙 Back to Methods", callback_data="back_to_methods")])

    await context.bot.edit_message_text(
        chat_id=user_id,
        message_id=state.get("preview_message_id"),
        text="✅ <b>All APKs Posted Successfully!</b>\n\nManage your posts below:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def auto_recaption(user_id, context):
    user_info = USER_DATA.get(str(user_id), {})
    state = USER_STATE.get(user_id, {})
    channel_id = user_info.get("channel")
    saved_caption = user_info.get("caption", "")
    session_files = state.get("session_files", [])
    key = state.get("saved_key", "")
    key_mode = state.get("key_mode", "normal")
    old_posts = state.get("apk_posts", [])
    preview_message_id = state.get("preview_message_id")

    if not channel_id or not session_files or not key:
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ <b>Session data missing!</b> Cannot re-caption.",
            parse_mode="HTML"
        )
        return

    media = []
    for idx, file_id in enumerate(session_files, start=1):
        is_last_apk = (idx == len(session_files))
    
        if key_mode == "quote":
            if len(session_files) == 1 or is_last_apk:
                caption = saved_caption.replace("Key -", f"<blockquote>Key - <code>{key}</code></blockquote>")
            else:
                caption = f"<blockquote>Key - <code>{key}</code></blockquote>"
    
        elif key_mode == "mono":
            if len(session_files) == 1 or is_last_apk:
                caption = saved_caption.replace("Key -", f"Key - <code>{key}</code>")
            else:
                caption = f"Key - <code>{key}</code>"
    
        else:  # normal
            if len(session_files) == 1 or is_last_apk:
                caption = saved_caption.replace("Key -", f"Key - {key}")
            else:
                caption = f"Key - {key}"
    
        media.append(InputMediaDocument(media=file_id, caption=caption, parse_mode="HTML"))

    # Send corrected media group
    new_posts = await context.bot.send_media_group(chat_id=channel_id, media=media)

    # Delete old wrong posts
    for old_msg_id in old_posts:
        try:
            await context.bot.delete_message(chat_id=channel_id, message_id=old_msg_id)
        except Exception:
            pass

    # Update new post links
    USER_STATE[user_id]["apk_posts"] = [msg.message_id for msg in new_posts]
    last_msg = new_posts[-1]

    if channel_id.startswith("@"):
        post_link = f"https://t.me/{channel_id.strip('@')}/{last_msg.message_id}"
    elif channel_id.startswith("-100"):
        post_link = f"https://t.me/c/{channel_id.replace('-100', '')}/{last_msg.message_id}"
    else:
        post_link = "Unknown"

    USER_STATE[user_id]["last_post_link"] = post_link

    # Build buttons
    buttons = [
        [InlineKeyboardButton("📄 View Last Post", url=post_link)],
        [InlineKeyboardButton("🗑️ Delete APK Post", callback_data="delete_apk_post")],
        [InlineKeyboardButton("🔙 Back to Methods", callback_data="back_to_methods")]
    ]

    # Now Edit the same old message
    try:
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=preview_message_id,
            text="✅ <b>Auto Re-Captioned Successfully!</b>\n\nManage your posts below:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        print(f"Error editing message after auto-recaption: {e}")

    # Important: Session ends quietly after re-caption
    USER_STATE[user_id]["session_files"] = []
    USER_STATE[user_id]["session_filenames"] = []
    USER_STATE[user_id]["saved_key"] = None
    USER_STATE[user_id]["waiting_key"] = False
    USER_STATE[user_id]["last_apk_time"] = None
    USER_STATE[user_id]["key_mode"] = "normal"

async def check_session_timeout(user_id, context):
    await asyncio.sleep(5)

    state = USER_STATE.get(user_id)
    if not state:
        return

    last_apk_time = state.get("last_apk_time")
    if not last_apk_time:
        return

    now = time.time()
    if now - last_apk_time >= 5:
        # Timeout reached, move to key capture
        session = state.get("session_files", [])
        if session:
            await ask_key_for_method2(user_id, context)

async def ask_key_for_method2(user_id, context):
    chat_id = user_id
    USER_STATE[user_id]["waiting_key"] = True

    await context.bot.send_message(
        chat_id=chat_id,
        text="🔑 *Send the Key now!* (Only one Key for 2-3 APKs)",
        parse_mode="Markdown"
    )

async def ask_to_share(update: Update):
    keyboard = [
        [InlineKeyboardButton("✅ Yes", callback_data="share_yes"),
         InlineKeyboardButton("❌ No", callback_data="share_no")]
    ]
    await update.message.reply_text(
        "*𝖱𝖾𝖺𝖽𝗒 𝗍𝗈 𝗌𝗁𝖺𝗋𝖾* 🤔\n"
        "_𝗍𝗁𝗂𝗌 𝖯𝗈𝗌𝗍 𝗍𝗈 𝗒𝗈𝗎𝗋 𝖼𝗁𝖺𝗇𝗇𝖾𝗅 \\? ↙️_\n"
        "*𝖢𝗁𝗈𝗈𝗌𝖾 𝗐𝗂𝗌𝖾𝗅𝗒 \\!* 👇",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def countdown_and_check(user_id, chat_id, context):
    try:
        for remaining in range(5, 0, -1):
            await asyncio.sleep(1)

            state = USER_STATE.get(user_id, {})
            message_id = state.get("progress_message_id")

            if message_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"✅ {len(state.get('session_files', []))} APKs Received! ☑️\nWaiting {remaining} sec for next APK...",
                        parse_mode="Markdown"
                    )
                except telegram.error.BadRequest as e:
                    if "Message is not modified" in str(e):
                        pass  # Safe ignore
                    else:
                        print(f"Countdown edit failed: {e}")
                        break

        # After countdown complete, check if session still active
        state = USER_STATE.get(user_id, {})
        session_files = state.get("session_files", [])
        if session_files and not state.get("waiting_key", False):
            # Now ask for the Key
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=state["progress_message_id"],
                    text="🔑 *Send the Key now!* (Only one Key for 2-3 APKs)",
                    parse_mode="Markdown"
                )
            except Exception as e:
                # If edit fail, send new message
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="🔑 *Send the Key now!* (Only one Key for 2-3 APKs)",
                    parse_mode="Markdown"
                )

            USER_STATE[user_id]["waiting_key"] = True
            USER_STATE[user_id]["progress_message_id"] = None

    except Exception as e:
        print(f"Countdown error: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text.strip().lower()

    # BUTTON TEXT HANDLING
    if message_text == "ping":
        await ping(update, context)
        return
    elif message_text == "help":
        await help_command(update, context)
        return
    elif message_text == "rules":
        await rules(update, context)
        return
    elif message_text == "reset":
        await reset(update, context)
        return
    elif message_text == "userlist" and user_id == OWNER_ID:
        await userlist(update, context)
        return
    elif message_text == "on" and user_id == OWNER_ID:
        await update.message.reply_text("✅ Bot is now *ON*. All systems go! 🚀", parse_mode="Markdown")
        return
    elif message_text == "off" and user_id == OWNER_ID:
        await update.message.reply_text("⛔ Bot is now *OFF*. Shutting down... 📴", parse_mode="Markdown")
        return

    # STATE HANDLING
    state = USER_STATE.get(user_id)
    if not state:
        return

    # Handle Channel Setting
    if state.get("status") == "waiting_channel":
        channel_id = update.message.text.strip()
        USER_DATA[str(user_id)] = USER_DATA.get(str(user_id), {})
        USER_DATA[str(user_id)]["channel"] = channel_id
        save_config()
        USER_STATE[user_id]["status"] = "normal"
    
        keyboard = [
            [InlineKeyboardButton("⚡ Method 1", callback_data="method_1")],
            [InlineKeyboardButton("🚀 Method 2", callback_data="method_2")]
        ]
        await update.message.reply_text(
            f"✅ *Channel ID Saved:* `{channel_id}`\n\n"
            "👋 *Welcome!*\n\n"
            "Please select your working method:\n\n"
            "⚡ *Method 1*: Manual Key Capture\n"
            "🚀 *Method 2*: Upload 2-3 APKs and capture one key",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Handle Caption Setting
    if state.get("status") == "waiting_caption":
        caption = update.message.text.strip()
        if "Key -" not in caption:
            await update.message.reply_text(
                "❗ *Invalid caption!*\n\nYour caption must contain `Key -`.",
                parse_mode="Markdown"
            )
        else:
            USER_DATA[str(user_id)] = USER_DATA.get(str(user_id), {})
            USER_DATA[str(user_id)]["caption"] = caption
            save_config()
            USER_STATE[user_id]["status"] = "normal"
    
            keyboard = [
                [InlineKeyboardButton("⚡ Method 1", callback_data="method_1")],
                [InlineKeyboardButton("🚀 Method 2", callback_data="method_2")]
            ]
            await update.message.reply_text(
                f"<blockquote><b>✅ New Caption Saved!</b>\n\n"
                "" + caption + "</blockquote>\n\n"
                "<b>👋 Welcome!</b>\n\n"
                "Please select your methods:\n\n"
                "<b>⚡ Method 1: Upload One apk 🥇</b>\n"
                "<b>🚀 Method 2: Upload 2-3 apks 🥈</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

    # Handle waiting key for Method 1
    if state.get("waiting_key") and state.get("current_method") == "method1":
        key = update.message.text.strip()
        saved_caption = USER_DATA.get(str(user_id), {}).get("caption", "")
        channel_id = USER_DATA.get(str(user_id), {}).get("channel", "")
        file_id = state.get("file_id")

        if not key or not file_id or not saved_caption or not channel_id:
            await update.message.reply_text(
                "❌ *Missing Data! Please restart.*",
                parse_mode="Markdown"
            )
            return

        final_caption = saved_caption.replace("Key -", f"Key - <code>{key}</code>")
        await context.bot.send_document(
            chat_id=channel_id,
            document=file_id,
            caption=final_caption,
            parse_mode="HTML"
        )
        await update.message.reply_text("✅ *APK posted successfully!*", parse_mode="Markdown")

        USER_STATE[user_id]["waiting_key"] = False
        USER_STATE[user_id]["file_id"] = None
        return

    # Handle waiting key for Method 2
    if state.get("waiting_key") and state.get("current_method") == "method2":
        key = update.message.text.strip()
        session_files = state.get("session_files", [])
    
        if not key or not session_files:
            await update.message.reply_text(
                "❌ *Session Error! Please restart.*",
                parse_mode="Markdown"
            )
            return
    
        USER_STATE[user_id]["saved_key"] = key
        USER_STATE[user_id]["waiting_key"] = False
        USER_STATE[user_id]["progress_message_id"] = None  # STOP Countdown
        USER_STATE[user_id]["quote_applied"] = False  # Important Reset
        USER_STATE[user_id]["mono_applied"] = False  # Important Reset
    
        buttons = [
            [InlineKeyboardButton("✅ Yes", callback_data="method2_yes"),
             InlineKeyboardButton("❌ No", callback_data="method2_no")],
            [InlineKeyboardButton("✍️ Quote Key", callback_data="method2_quote"),
             InlineKeyboardButton("🔤 Normal Key", callback_data="method2_mono")],
            [InlineKeyboardButton("📝 Edit Caption", callback_data="method2_edit"),
             InlineKeyboardButton("👁️ Show Preview", callback_data="method2_preview")]
        ]
    
        sent_message = await update.message.reply_text(
            "🔖 *Key captured!*\n\nChoose what you want to do next:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
        USER_STATE[user_id]["preview_message_id"] = sent_message.message_id
        return

    # Handle waiting new caption after Edit
    if state.get("status") == "waiting_new_caption":
        await method2_edit_caption(update, context)
        return

async def method2_edit_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    new_caption = update.message.text.strip()

    if "Key -" not in new_caption:
        await update.message.reply_text(
            "❌ *Invalid Caption!*\n\nIt must include `Key -` placeholder.",
            parse_mode="Markdown"
        )
        return

    # Save new Caption
    USER_DATA[str(user_id)] = USER_DATA.get(str(user_id), {})
    USER_DATA[str(user_id)]["caption"] = new_caption
    save_config()

    USER_STATE[user_id]["status"] = "normal"

    # Update Preview
    preview_message_id = USER_STATE.get(user_id, {}).get("preview_message_id")
    key = USER_STATE.get(user_id, {}).get("saved_key", "")
    session_files = USER_STATE.get(user_id, {}).get("session_files", [])

    if not preview_message_id or not key or not session_files:
        await update.message.reply_text(
            "⚠️ *No active session found!*",
            parse_mode="Markdown"
        )
        return

    text = "✅ *New Caption Saved!*\n\n"
    final_caption = new_caption.replace("Key -", f"Key - {key}")

    for idx, _ in enumerate(session_files, start=1):
        text += f"📦 APK {idx}: {final_caption}\n"

    buttons = [
        [InlineKeyboardButton("🔙 Back", callback_data="method2_back_fullmenu")]
    ]

    try:
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=preview_message_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except telegram.error.BadRequest as e:
        if "Error editing preview after caption" in str(e):
            pass  # ignore if same
        else:
            raise e  # raise normally if another error

async def method2_convert_quote(user_id, context: ContextTypes.DEFAULT_TYPE):
    state = USER_STATE.get(user_id, {})
    preview_message_id = state.get("preview_message_id")
    key = state.get("saved_key", "")
    session_files = state.get("session_files", [])

    if not preview_message_id or not key or not session_files:
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ *No session found!*",
            parse_mode="Markdown"
        )
        return

    text = "✅ *Key converted to Quote Style!*\n\n"
    for idx, _ in enumerate(session_files, start=1):
        text += f"📦 APK {idx}: <blockquote>Key - <code>{key}</code></blockquote>\n"

    # Mark quote_applied = True (for button hiding)
    USER_STATE[user_id]["quote_applied"] = True

    buttons = build_method2_buttons(user_id)  # Rebuild dynamic buttons

    try:
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=preview_message_id,
            text=text,
            parse_mode="HTML",  # Needed for <code> formatting
            reply_markup=buttons
        )
    except Exception as e:
        print(f"Error converting to quote style: {e}")

async def method2_convert_mono(user_id, context: ContextTypes.DEFAULT_TYPE):
    state = USER_STATE.get(user_id, {})
    preview_message_id = state.get("preview_message_id")
    key = state.get("saved_key", "")
    session_files = state.get("session_files", [])

    if not preview_message_id or not key or not session_files:
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ <code>No session found!</code>",
            parse_mode="Markdown"
        )
        return

    text = "✅ <code>Key converted to Normal Style!</code>\n\n"
    for idx, _ in enumerate(session_files, start=1):
        text += f"📦 APK {idx}: Key - <code>{key}</code>\n"

    # Mark mono_applied = True (for button hiding)
    USER_STATE[user_id]["mono_applied"] = True

    buttons = build_method2_buttons(user_id)  # Rebuild dynamic buttons

    try:
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=preview_message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=buttons
        )
    except telegram.error.BadRequest as e:
        if "Error converting to mono style" in str(e):
            pass  # ignore if same
        else:
            raise e  # raise normally if another error

async def method2_edit_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    new_caption = update.message.text.strip()

    if "Key -" not in new_caption:
        await update.message.reply_text(
            "❌ *Invalid Caption!*\n\nMust contain `Key -` placeholder.",
            parse_mode="Markdown"
        )
        return

    # Save new caption
    USER_DATA[str(user_id)] = USER_DATA.get(str(user_id), {})
    USER_DATA[str(user_id)]["caption"] = new_caption
    save_config()

    USER_STATE[user_id]["status"] = "normal"
    USER_STATE[user_id]["quote_applied"] = False
    USER_STATE[user_id]["mono_applied"] = False

    preview_message_id = USER_STATE.get(user_id, {}).get("preview_message_id")
    key = USER_STATE.get(user_id, {}).get("saved_key", "")
    session_files = USER_STATE.get(user_id, {}).get("session_files", [])

    if not preview_message_id or not key or not session_files:
        await update.message.reply_text(
            "⚠️ *No active session found!*",
            parse_mode="Markdown"
        )
        return

    # Build the new text
    text = "✅ *New Caption Saved!*\n\n"
    for idx, _ in enumerate(session_files, start=1):
        text += f"📦 APK {idx}: Key - {key}\n"

    # Only show Back button after editing caption
    buttons = [
        [InlineKeyboardButton("🔙 Back", callback_data="method2_back_fullmenu")]
    ]

    try:
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=preview_message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except BadRequest as e:
        if "message is not modified" in str(e):
            pass  # ignore same message error
        else:
            raise e  # if other error, show normally

async def method2_show_preview(user_id, context):
    user_state = USER_STATE.get(user_id, {})
    session_files = user_state.get("session_files", [])
    session_filenames = user_state.get("session_filenames", [])
    key = user_state.get("saved_key", "")
    saved_caption = USER_DATA.get(str(user_id), {}).get("caption", "")
    key_mode = user_state.get("key_mode", "normal")

    if not session_files or not key:
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ <b>No active APK session found!</b>",
            parse_mode="HTML"
        )
        return

    preview_text = "🔖 <b>Captured APKs Preview:</b>\n\n"

    for idx, (file_id, file_name) in enumerate(zip(session_files, session_filenames), start=1):
        try:
            file_size = None
            if hasattr(context.bot, "get_file"):
                file_info = await context.bot.get_file(file_id)
                file_size = file_info.file_size
        except Exception as e:
            print(f"Failed to fetch file size: {e}")
            file_size = None

        file_size_mb = round(file_size / (1024 * 1024), 1) if file_size else "?"

        # Build Key Text based on selected mode
        if key_mode == "quote":
            key_text = f"<blockquote>Key - <code>{key}</code></blockquote>"
        elif key_mode == "mono":
            key_text = f"<code>Key - {key}</code>"
        else:
            key_text = f"Key - {key}"

        # Check if it's last APK
        if idx == len(session_files):
            # Last APK use full user saved caption + key
            if "Key -" in saved_caption:
                final_caption = saved_caption.replace("Key -", key_text)
            else:
                final_caption = saved_caption + f"\n{key_text}"

            preview_text += f"➤ <b>{file_name}</b>"
            if file_size_mb != "?":
                preview_text += f" ({file_size_mb} MB)"
            preview_text += f"\n✍️ {final_caption}\n\n"
        else:
            # Other APKs simple Key
            preview_text += f"➤ <b>{file_name}</b>"
            if file_size_mb != "?":
                preview_text += f" ({file_size_mb} MB)"
            preview_text += f"\n🔑 {key_text}\n\n"

    # Inline Keyboard
    keyboard = [
        [InlineKeyboardButton("✅ Yes", callback_data="method2_yes"),
         InlineKeyboardButton("❌ No", callback_data="method2_no")],
        [InlineKeyboardButton("✍️ Quote Key", callback_data="method2_quote"),
         InlineKeyboardButton("🔤 Normal Key", callback_data="method2_mono")],
        [InlineKeyboardButton("📝 Edit Caption", callback_data="method2_edit"),
         InlineKeyboardButton("👁️ Show Preview", callback_data="method2_preview")]
    ]

    try:
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=user_state.get("preview_message_id"),
            text=preview_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print(f"Error in showing preview: {e}")

def build_method2_buttons(user_id):
    state = USER_STATE.get(user_id, {})
    
    buttons = [
        [InlineKeyboardButton("✅ Yes", callback_data="method2_yes"),
         InlineKeyboardButton("❌ No", callback_data="method2_no")]
    ]

    quote_applied = state.get("quote_applied", False)
    mono_applied = state.get("mono_applied", False)

    row = []

    if not quote_applied:
        row.append(InlineKeyboardButton("✍️ Quote Key", callback_data="method2_quote"))

    if not mono_applied:
        row.append(InlineKeyboardButton("🔤 Normal Key", callback_data="method2_mono"))

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("📝 Edit Caption", callback_data="method2_edit"),
        InlineKeyboardButton("👁️ Show Preview", callback_data="method2_preview")
    ])

    return InlineKeyboardMarkup(buttons)

async def method2_back_fullmenu(user_id, context):
    preview_message_id = USER_STATE.get(user_id, {}).get("preview_message_id")

    buttons = [
        [InlineKeyboardButton("✅ Yes", callback_data="method2_yes"),
         InlineKeyboardButton("❌ No", callback_data="method2_no")],
        [InlineKeyboardButton("✍️ Quote Key", callback_data="method2_quote"),
         InlineKeyboardButton("🔤 Normal Key", callback_data="method2_mono")],
        [InlineKeyboardButton("📝 Edit Caption", callback_data="method2_edit"),
         InlineKeyboardButton("👁️ Show Preview", callback_data="method2_preview")]
    ]

    await context.bot.edit_message_text(
        chat_id=user_id,
        message_id=preview_message_id,
        text="🔖 *Key captured!*\n\nChoose what you want to do next:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    state = USER_STATE.get(user_id, {})
    preview_message_id = state.get("preview_message_id")
    
    # --- Cooldown Anti Spam ---
    now = time.time()
    if not hasattr(context, "user_cooldowns"):
        context.user_cooldowns = {}
    if user_id in context.user_cooldowns and now - context.user_cooldowns[user_id] < 1:
        await query.answer("⌛ Wait a second...", show_alert=False)
        return
    context.user_cooldowns[user_id] = now

    # --- Help Buttons Handling ---
    if data == "help_next":
        keyboard = [
            [InlineKeyboardButton("⬅️ Back", callback_data="help_back")]
        ]
        await query.edit_message_text(
            "⚙️ *Auto Channel Monitor Commands:*\n\n"
            "➔ /setsource1 - Set Source 1\n"
            "➔ /setdest1 - Set Destination 1\n"
            "➔ /setdestcaption1 - Set Caption 1\n"
            "➔ /resetsetup1 - Reset Setup 1\n\n"
            "➔ /setsource2 - Set Source 2\n"
            "➔ /setdest2 - Set Destination 2\n"
            "➔ /setdestcaption2 - Set Caption 2\n"
            "➔ /resetsetup2 - Reset Setup 2\n\n"
            "➔ /setsource3 - Set Source 3\n"
            "➔ /setdest3 - Set Destination 3\n"
            "➔ /setdestcaption3 - Set Caption 3\n"
            "➔ /resetsetup3 - Reset Setup 3\n\n"
            "➔ /viewsetup - View All Setups",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data == "help_back":
        keyboard = [
            [InlineKeyboardButton("➡️ Next", callback_data="help_next")]
        ]
        await query.edit_message_text(
            "🛠 *Manual Upload Commands:*\n\n"
            "➔ /start - Restart bot interaction\n"
            "➔ /setchannelid - Set Upload Channel\n"
            "➔ /setcaption - Set Upload Caption\n"
            "➔ /resetcaption - Reset Caption\n"
            "➔ /resetchannelid - Reset Channel\n"
            "➔ /reset - Full Reset\n\n"
            "➔ /adduser - Add Allowed User\n"
            "➔ /removeuser - Remove User\n"
            "➔ /userlist - List Users\n"
            "➔ /ping - Bot Status\n"
            "➔ /rules - Bot Rules\n",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # --- Check user session ---
    if user_id not in USER_STATE:
        await query.edit_message_text(
            "⏳ *Session expired or invalid!* ❌\nPlease restart using /start.",
            parse_mode="Markdown"
        )
        return

    state = USER_STATE[user_id]
    channel_id = USER_DATA.get(str(user_id), {}).get("channel")

    # --- Set Channel or Caption ---
    if data == "set_channel":
        USER_STATE[user_id]["status"] = "waiting_channel"
        await query.edit_message_text(
            "📡 *Please send your Channel ID now!* Example: `@yourchannel` or `-100xxxxxxxxxx`",
            parse_mode="Markdown"
        )
        return

    if data == "set_caption":
        USER_STATE[user_id]["status"] = "waiting_caption"
        await query.edit_message_text(
            "📝 *Please send your Caption now!* Must contain: `Key -`",
            parse_mode="Markdown"
        )
        return

    # --- Method 1 Selected ---
    if data == "method_1":
        USER_STATE[user_id]["current_method"] = "method1"
        USER_STATE[user_id]["status"] = "normal"

        buttons = [
            [InlineKeyboardButton("🌟 Bot Admin", url="https://t.me/TrailKeyHandlerBOT?startchannel=true")],
            [InlineKeyboardButton("📡 Set Channel", callback_data="set_channel")],
            [InlineKeyboardButton("📝 Set Caption", callback_data="set_caption")]
        ]

        if channel_id and USER_DATA.get(str(user_id), {}).get("caption"):
            buttons.append([InlineKeyboardButton("📤 Send One APK", callback_data="send_apk_method1")])

        buttons.append([InlineKeyboardButton("🔙 Back to Methods", callback_data="back_to_methods")])

        await query.edit_message_text(
            "✅ *Method 1 Selected!*\n\nManual key capture system activated.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # --- Method 2 Selected ---
    if data == "method_2":
        USER_STATE[user_id]["current_method"] = "method2"
        USER_STATE[user_id]["status"] = "normal"

        buttons = [
            [InlineKeyboardButton("🌟 Bot Admin", url="https://t.me/TrailKeyHandlerBOT?startchannel=true")],
            [InlineKeyboardButton("📡 Set Channel", callback_data="set_channel")],
            [InlineKeyboardButton("📝 Set Caption", callback_data="set_caption")]
        ]

        if channel_id and USER_DATA.get(str(user_id), {}).get("caption"):
            buttons.append([InlineKeyboardButton("📤 Send 2-3 APKs", callback_data="send_apk_method2")])

        buttons.append([InlineKeyboardButton("🔙 Back to Methods", callback_data="back_to_methods")])

        await query.edit_message_text(
            "✅ *Method 2 Selected!*\n\nMulti APK Upload system activated.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # --- Method 2 Confirmations ---
    if data == "method2_yes":
        await method2_send_to_channel(user_id, context)
        return

    if data == "method2_no":
        USER_STATE[user_id]["session_files"] = []
        USER_STATE[user_id]["session_filenames"] = []
        await query.edit_message_text("❌ *Session canceled!*", parse_mode="Markdown")
        return

    if data == "method2_quote":
        USER_STATE[user_id]["key_mode"] = "quote"
        await method2_convert_quote(user_id, context)
        return
    
    if data == "method2_mono":
        USER_STATE[user_id]["key_mode"] = "mono"
        await method2_convert_mono(user_id, context)
        return

    if data == "method2_edit":
        USER_STATE[user_id]["status"] = "waiting_new_caption"
        await query.edit_message_text(
            "📝 *Send new Caption now!* (Must include `Key -`)",
            parse_mode="Markdown"
        )
        return

    if data == "method2_preview":
        await method2_show_preview(user_id, context)
        return
    
    if data == "auto_recaption":
        await auto_recaption(user_id, context)
        return
    
    # --- Back to Methods ---
    if data == "back_to_methods":
        USER_STATE[user_id]["current_method"] = None
        USER_STATE[user_id]["status"] = "selecting_method"

        keyboard = [
            [InlineKeyboardButton("⚡ Method 1", callback_data="method_1")],
            [InlineKeyboardButton("🚀 Method 2", callback_data="method_2")]
        ]

        await query.edit_message_text(
            "🔄 *Method Selection Reset!*\n\nPlease select again:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
        
    if data == "delete_apk_post":
        apk_posts = USER_STATE.get(user_id, {}).get("apk_posts", [])
    
        keyboard = []
        for idx, _ in enumerate(apk_posts):
            keyboard.append([InlineKeyboardButton(f"🗑️ Delete APK {idx+1}", callback_data=f"delete_apk_{idx+1}")])
    
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_manage_post")])
    
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=USER_STATE[user_id]["preview_message_id"],
            text="🗑️ *Select which APK you want to delete:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "back_to_manage_post":
        buttons = [
            [InlineKeyboardButton("📄 View Last Post", url=USER_STATE[user_id]["last_post_link"])],
            [InlineKeyboardButton("🗑️ Delete APK Post", callback_data="delete_apk_post")],
            [InlineKeyboardButton("🔙 Back to Methods", callback_data="back_to_methods")]
        ]
    
        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=USER_STATE[user_id]["preview_message_id"],
            text="✅ *Manage your posted APKs:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
        
    if data.startswith("delete_apk_"):
        apk_number = int(data.split("_")[-1])
        apk_posts = USER_STATE.get(user_id, {}).get("apk_posts", [])
        channel_id = USER_DATA.get(str(user_id), {}).get("channel")
    
        if apk_number <= len(apk_posts):
            msg_id = apk_posts[apk_number - 1]
    
            try:
                await context.bot.delete_message(chat_id=channel_id, message_id=msg_id)
            except Exception as e:
                print(f"Delete failed: {e}")
    
            # Remove deleted
            apk_posts[apk_number - 1] = None
            apk_posts = [m for m in apk_posts if m]
            USER_STATE[user_id]["apk_posts"] = apk_posts
    
            if not apk_posts:
                # All posts deleted
                USER_STATE[user_id]["session_files"] = []
                USER_STATE[user_id]["session_filenames"] = []
                USER_STATE[user_id]["saved_key"] = None
                USER_STATE[user_id]["apk_posts"] = []
                USER_STATE[user_id]["last_apk_time"] = None
                USER_STATE[user_id]["waiting_key"] = False
                USER_STATE[user_id]["preview_message_id"] = None
    
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=query.message.message_id,
                    text="✅ *All APKs deleted!*\nNew season started.",
                    parse_mode="Markdown"
                )
                return
    
            # If posts remaining, show delete menu again
            keyboard = []
            for idx, _ in enumerate(apk_posts):
                keyboard.append([InlineKeyboardButton(f"🗑️ Delete APK {idx+1}", callback_data=f"delete_apk_{idx+1}")])
    
            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_manage_post")])
    
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=query.message.message_id,
                text=f"✅ *Deleted APK {apk_number} Successfully!*\nSelect another to delete:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
    
    if data == "method2_back_fullmenu":
        preview_message_id = USER_STATE.get(user_id, {}).get("preview_message_id")
        key = USER_STATE.get(user_id, {}).get("saved_key", "")
        session_files = USER_STATE.get(user_id, {}).get("session_files", [])
    
        if not preview_message_id or not key or not session_files:
            await query.edit_message_text(
                text="⚠️ *Session expired or not found!*",
                parse_mode="Markdown"
            )
            return
    
        text = "🔖 *Key captured!*\n\nChoose what you want to do next:"
    
        try:
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=preview_message_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=build_method2_buttons(user_id)
            )
        except Exception as e:
            print(f"Error going back to Full Menu: {e}")
    
# Setup 1 - Set Source Channel
async def set_source1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can set this!")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/setsource1 @channelname or -100xxxx`", parse_mode="Markdown")
        return
    AUTO_SETUP["setup1"]["source_channel"] = context.args[0]
    save_config()
    await update.message.reply_text(f"✅ Setup 1 Source Channel set to: `{context.args[0]}`", parse_mode="Markdown")

# Setup 1 - Set Destination Channel
async def set_dest1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can set this!")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/setdest1 @channelname or -100xxxx`", parse_mode="Markdown")
        return
    AUTO_SETUP["setup1"]["dest_channel"] = context.args[0]
    save_config()
    await update.message.reply_text(f"✅ Setup 1 Destination Channel set to: `{context.args[0]}`", parse_mode="Markdown")

# Setup 1 - Set Destination Caption
async def set_destcaption1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can set this!")
        return
    text = update.message.text.split(' ', 1)
    if len(text) < 2:
        await update.message.reply_text("Usage: `/setdestcaption1 Caption with Key - placeholder`", parse_mode="Markdown")
        return
    caption = text[1]
    if "Key -" not in caption:
        await update.message.reply_text("❗ Caption must include `Key -` placeholder!", parse_mode="Markdown")
        return
    AUTO_SETUP["setup1"]["dest_caption"] = caption
    save_config()
    await update.message.reply_text("✅ Setup 1 Destination Caption saved!", parse_mode="Markdown")

# Setup 2 - Set Source Channel
async def set_source2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can set this!")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/setsource2 @channelname or -100xxxx`", parse_mode="Markdown")
        return
    AUTO_SETUP["setup2"]["source_channel"] = context.args[0]
    save_config()
    await update.message.reply_text(f"✅ Setup 2 Source Channel set to: `{context.args[0]}`", parse_mode="Markdown")

# Setup 2 - Set Destination Channel
async def set_dest2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can set this!")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/setdest2 @channelname or -100xxxx`", parse_mode="Markdown")
        return
    AUTO_SETUP["setup2"]["dest_channel"] = context.args[0]
    save_config()
    await update.message.reply_text(f"✅ Setup 2 Destination Channel set to: `{context.args[0]}`", parse_mode="Markdown")

# Setup 2 - Set Destination Caption
async def set_destcaption2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can set this!")
        return
    text = update.message.text.split(' ', 1)
    if len(text) < 2:
        await update.message.reply_text("Usage: `/setdestcaption2 Caption with Key - placeholder`", parse_mode="Markdown")
        return
    caption = text[1]
    if "Key -" not in caption:
        await update.message.reply_text("❗ Caption must include `Key -` placeholder!", parse_mode="Markdown")
        return
    AUTO_SETUP["setup2"]["dest_caption"] = caption
    save_config()
    await update.message.reply_text("✅ Setup 2 Destination Caption saved!", parse_mode="Markdown")

# Setup 3 - Set Source Channel
async def set_source3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can set this!")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/setsource3 @channelname or -100xxxx`", parse_mode="Markdown")
        return
    AUTO_SETUP["setup3"]["source_channel"] = context.args[0]
    save_config()
    await update.message.reply_text(f"✅ Setup 3 Source Channel set to: `{context.args[0]}`", parse_mode="Markdown")

# Setup 3 - Set Destination Channel
async def set_dest3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can set this!")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/setdest3 @channelname or -100xxxx`", parse_mode="Markdown")
        return
    AUTO_SETUP["setup3"]["dest_channel"] = context.args[0]
    save_config()
    await update.message.reply_text(f"✅ Setup 3 Destination Channel set to: `{context.args[0]}`", parse_mode="Markdown")

# Setup 3 - Set Destination Caption
async def set_destcaption3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can set this!")
        return
    text = update.message.text.split(' ', 1)
    if len(text) < 2:
        await update.message.reply_text("Usage: `/setdestcaption3 Caption with Key - placeholder`", parse_mode="Markdown")
        return
    caption = text[1]
    if "Key -" not in caption:
        await update.message.reply_text("❗ Caption must include `Key -` placeholder!", parse_mode="Markdown")
        return
    AUTO_SETUP["setup3"]["dest_caption"] = caption
    save_config()
    await update.message.reply_text("✅ Setup 3 Destination Caption saved!", parse_mode="Markdown")

async def view_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Only Owner can view setup!")
        return

    text = ""
    total = 0

    for i in range(1, 4):
        setup = AUTO_SETUP.get(f"setup{i}", {})

        source = setup.get("source_channel")
        dest = setup.get("dest_channel", "Not Set")
        caption = "Saved" if setup.get("dest_caption") else "Not Set"
        completed = setup.get("completed_count", 0)

        if source:
            total += 1

            # Escape for MarkdownV2
            source = re.sub(r'([_\*\~\`\>\#\+\-\=\|\{\}\.\!])', r'\\\1', source)
            dest = re.sub(r'([_\*\~\`\>\#\+\-\=\|\{\}\.\!])', r'\\\1', dest)

            text += (
                f"📌 Setup {i}\n"
                f"├─ 👤 Source : {source}\n"
                f"├─ 🧬 Destination : {dest}\n"
                f"├─ 📝 Caption : {caption}\n"
                f"└─ 🔢 Completed : {completed} Keys\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
            )

    if total == 0:
        await update.message.reply_text("❌ No setup configured yet.")
    else:
        header = f"🧾 *Total Setup : {total}*\n\n"
        await update.message.reply_text(header + text, parse_mode="MarkdownV2")

async def reset_setup1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can reset setup 1!")
        return

    AUTO_SETUP["setup1"] = {
        "source_channel": "",
        "dest_channel": "",
        "dest_caption": "",
        "completed_count": 0
    }
    save_config()
    await update.message.reply_text("✅ Setup 1 has been reset successfully!")

async def reset_setup2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can reset setup 2!")
        return

    AUTO_SETUP["setup2"] = {
        "source_channel": "",
        "dest_channel": "",
        "dest_caption": "",
        "completed_count": 0
    }
    save_config()
    await update.message.reply_text("✅ Setup 2 has been reset successfully!")

async def reset_setup3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Only owner can reset setup 3!")
        return

    AUTO_SETUP["setup3"] = {
        "source_channel": "",
        "dest_channel": "",
        "dest_caption": "",
        "completed_count": 0
    }
    save_config()
    await update.message.reply_text("✅ Setup 3 has been reset successfully!")

async def auto_handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return

    message = update.channel_post
    chat_id = str(message.chat.id)
    source_username = f"@{message.chat.username}" if message.chat.username else None
    doc = message.document
    caption = message.caption or ""

    print(f"✅ Received channel post from {source_username or chat_id}")
    if not doc:
        print("❌ No document attached.")
        return

    if not doc.file_name.endswith(".apk"):
        print("❌ Not an APK file. Ignoring.")
        return

    file_size = doc.file_size
    file_size_mb = file_size / (1024 * 1024)

    matched_setup = None
    setup_number = None

    for i in range(1, 4):
        setup = AUTO_SETUP.get(f"setup{i}")
        if not setup or not setup.get("source_channel"):
            continue

        src = setup["source_channel"]

        if src.startswith("@") and source_username and src.lower() == source_username.lower():
            matched_setup = setup
            setup_number = i
            break
        elif src == chat_id:
            matched_setup = setup
            setup_number = i
            break

    if not matched_setup:
        print("❌ No matching setup found for this source channel.")
        return

    print(f"✅ Matched to Setup {setup_number}")

    # Size filter
    if setup_number == 1 and not (1 <= file_size_mb <= 50):
        print("❌ Size not matched for Setup 1.")
        return
    if setup_number == 2 and not (80 <= file_size_mb <= 2048):
        print("❌ Size not matched for Setup 2.")
        return

    if not caption:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text="⚠️ *Alert!*\n➔ *APK received without caption.*\n🚫 *Processing skipped!*",
            parse_mode="Markdown"
        )
        print("❌ Caption missing. Error sent to owner.")
        return

    match = re.search(r'Key\s*-\s*(\S+)', caption)
    if not match:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text="⚠️ *Warning!*\n➔ *Key missing in caption.*\n⛔ *File not processed!*",
            parse_mode="Markdown"
        )
        print("❌ Key missing in caption. Error sent to owner.")
        return

    key = match.group(1)
    dest_caption = matched_setup["dest_caption"].replace("Key -", f"Key - `{key}`")
    dest_channel = matched_setup["dest_channel"]

    # Send initial countdown message
    countdown_msg = await context.bot.send_message(
        chat_id=OWNER_ID,
        text=f"⏳ Waiting to process APK... 20 seconds left.",
        parse_mode="Markdown"
    )

    # Countdown edit
    for sec in range(19, 0, -1):
        await asyncio.sleep(1)
        try:
            await context.bot.edit_message_text(
                chat_id=OWNER_ID,
                message_id=countdown_msg.message_id,
                text=f"⏳ Waiting to process APK... {sec} seconds left.",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Countdown edit failed: {e}")

    # After countdown complete
    await asyncio.sleep(1)

    try:
        sent_msg = await context.bot.send_document(
            chat_id=dest_channel,
            document=doc.file_id,
            caption=dest_caption,
            parse_mode="Markdown",
            disable_notification=True
        )

        matched_setup["completed_count"] += 1
        save_config()

        # Post link generator
        if str(dest_channel).startswith("@"):
            post_link = f"https://t.me/{dest_channel.strip('@')}/{sent_msg.message_id}"
        elif str(dest_channel).startswith("-100"):
            post_link = f"https://t.me/c/{str(dest_channel)[4:]}/{sent_msg.message_id}"
        else:
            post_link = "Unknown"

        # Escape for MarkdownV2
        def escape(text):
            return re.sub(r'([_\*~`>\#+\-=|{}.!])', r'\\\1', str(text))

        source_name = source_username if source_username else chat_id
        source = escape(source_name)
        dest = escape(dest_channel)
        key_escape = escape(key)
        post_link_escape = escape(post_link)

        key_escape = f"`{key_escape}`"

        # Final edit success message
        await context.bot.edit_message_text(
            chat_id=OWNER_ID,
            message_id=countdown_msg.message_id,
            text=(
                f"📌 Setup {setup_number} Completed\n"
                f"├─ 👤 Source : {source}\n"
                f"├─ 🧬 Destination : {dest}\n"
                f"├─ 📡 Key : {key_escape}\n"
                f"└─ 🆔 Post Link : [Click Here]({post_link_escape})\n"
                "━━━━━━━━━━━━━━━━━━━━"
            ),
            parse_mode="MarkdownV2",
            disable_web_page_preview=True
        )

        print("✅ Successfully forwarded and notified owner.")

    except Exception as e:
        error_message = traceback.format_exc()
        await context.bot.edit_message_text(
            chat_id=OWNER_ID,
            message_id=countdown_msg.message_id,
            text=f"❌ *Error Sending APK!*\n\n`{error_message}`",
            parse_mode="MarkdownV2"
        )
        print("❌ Error while sending document:\n", error_message)

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Main owner/user commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("rules", rules))

    # Manual upload system
    app.add_handler(CommandHandler("setchannelid", set_channel_id))
    app.add_handler(CommandHandler("setcaption", set_caption))
    app.add_handler(CommandHandler("resetcaption", reset_caption))
    app.add_handler(CommandHandler("resetchannelid", reset_channel))
    app.add_handler(CommandHandler("reset", reset))

    # Manage allowed users
    app.add_handler(CommandHandler("adduser", add_user))
    app.add_handler(CommandHandler("removeuser", remove_user))
    app.add_handler(CommandHandler("userlist", userlist))

    # Auto setup commands
    app.add_handler(CommandHandler("setsource1", set_source1))
    app.add_handler(CommandHandler("setdest1", set_dest1))
    app.add_handler(CommandHandler("setdestcaption1", set_destcaption1))

    app.add_handler(CommandHandler("setsource2", set_source2))
    app.add_handler(CommandHandler("setdest2", set_dest2))
    app.add_handler(CommandHandler("setdestcaption2", set_destcaption2))

    app.add_handler(CommandHandler("setsource3", set_source3))
    app.add_handler(CommandHandler("setdest3", set_dest3))
    app.add_handler(CommandHandler("setdestcaption3", set_destcaption3))

    # Reset single setup commands
    app.add_handler(CommandHandler("resetsetup1", reset_setup1))
    app.add_handler(CommandHandler("resetsetup2", reset_setup2))
    app.add_handler(CommandHandler("resetsetup3", reset_setup3))

    # View setup command
    app.add_handler(CommandHandler("viewsetup", view_setup))   # <<< ADD this line carefully!

    # Auto forward and manual upload
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS, auto_handle_channel_post))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

    # Handle callback buttons (for help menu etc.)
    app.add_handler(CallbackQueryHandler(handle_callback))

    app.run_polling()

if __name__ == "__main__":
    main()

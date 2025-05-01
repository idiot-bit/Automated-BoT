import json
import time
import random
import os
import re
import sys
import traceback
import asyncio
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram.error import BadRequest, Forbidden
from telegram.constants import ParseMode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, InputMediaDocument
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes, ApplicationBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Get token from Railway environment
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set")

def load_state():
    global USER_STATE, AUTO4_STATE, AUTO_SETUP, USER_DATA
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            USER_STATE = data.get("user_state", {})
            AUTO4_STATE.update(data.get("auto4_state", {}))
            AUTO_SETUP.update(data.get("auto_setup", {}))
            USER_DATA.update(data.get("user_data", {}))
    else:
        USER_STATE = {}
        AUTO4_STATE = {
            "pending_apks": [],
            "timer": None,
            "waiting_since": None,
            "countdown_msg_id": None,
            "setup_mode": 1
        }

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump({
            "user_state": USER_STATE,
            "auto4_state": AUTO4_STATE,
            "auto_setup": AUTO_SETUP,
            "user_data": USER_DATA
        }, f, indent=4)

# Load config
with open("config.json") as f:
    config = json.load(f)

OWNER_ID = config.get("owner_id")
ALLOWED_USERS = set(config.get("allowed_users", []))
USER_DATA = config.get("user_data", {})
BOT_ADMIN_LINK = config.get("bot_admin_link", "")

# Load bot toggle state
BOT_ACTIVE = config.get("bot_active", True)

STATE_FILE = "state.json"

# Load new setups
AUTO_SETUP = config.get("auto_setup", {
    "setup1": {
        "source_channel": "",
        "dest_channel": "",
        "dest_caption": "",
        "key_mode": "auto",
        "style": "mono",
        "enabled": False,
        "completed_count": 0
    },
    "setup2": {
        "source_channel": "",
        "dest_channel": "",
        "dest_caption": "",
        "key_mode": "auto",
        "style": "mono",
        "enabled": False,
        "completed_count": 0
    },
    "setup3": {
        "source_channel": "",
        "dest_channel": "",
        "dest_caption": "",
        "key_mode": "auto",
        "style": "mono",
        "enabled": False,
        "completed_count": 0
    },
    "setup4": {
        "source_channel": "",
        "dest_channel": "",
        "dest_caption": "",
        "key_mode": "auto",
        "style": "mono",
        "enabled": False,
        "completed_count": 0,
        "processed_count": 0
    }
})

load_state()

START_TIME = time.time()
BROADCAST_SESSION = {}  # {user_id: {"message": MessageObject}}
UPDATE_DATE = datetime.fromtimestamp(START_TIME, ZoneInfo("Asia/Kolkata")).strftime("%d-%m-%Y")
LAST_ERROR_TIME = 0
ERROR_COOLDOWN = 3600  # 1 hour in seconds

owner_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("UserStats")],
        [KeyboardButton("Userlist"), KeyboardButton("Help")],
        [KeyboardButton("Ping"), KeyboardButton("Rules")],
        [KeyboardButton("Reset"), KeyboardButton("Settings")],
        [KeyboardButton("Broadcast")],
        [KeyboardButton("On"), KeyboardButton("Off")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
    )

allowed_user_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Channel")],
        [KeyboardButton("Caption")],
        [KeyboardButton("Viewsetup")],
        [KeyboardButton("Help"), KeyboardButton("Reset")],
        [KeyboardButton("Ping"), KeyboardButton("Rules")]
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
            "auto_setup": AUTO_SETUP,
            "bot_active": BOT_ACTIVE,
            "bot_admin_link": BOT_ADMIN_LINK
        }, f, indent=4)

def save_auto_setup():
    with open("config.json", "r") as f:
        data = json.load(f)
        data["auto_setup"] = AUTO_SETUP
        with open("config.json", "w") as f:
            json.dump(data, f, indent=4)

def save_bot_config():
    with open("config.json", "w") as f:
        json.dump({
            "owner_id": OWNER_ID,
            "allowed_users": list(ALLOWED_USERS),
            "user_data": USER_DATA,
            "auto_setup": AUTO_SETUP,
            "bot_active": BOT_ACTIVE,
            "bot_admin_link": BOT_ADMIN_LINK
        }, f, indent=4)

async def autosave_task():
    while True:
        await asyncio.sleep(60)  # Save every 60 seconds
        save_state()

async def backup_config(context=None, query=None):
    now = datetime.now(ZoneInfo("Asia/Kolkata"))

    date_str = now.strftime("%d-%m-%Y")
    time_str = now.strftime("%I:%M%p").lower()
    zip_filename = f"Backup_{date_str}_{time_str}.zip"

    # Save config.json
    with open("config.json", "w") as f:
        json.dump({
            "owner_id": OWNER_ID,
            "allowed_users": list(ALLOWED_USERS),
            "user_data": USER_DATA,
            "auto_setup": AUTO_SETUP,
            "bot_active": BOT_ACTIVE,
            "bot_admin_link": BOT_ADMIN_LINK
        }, f, indent=4)

    # Save state.json
    save_state()

    # Create ZIP file
    with zipfile.ZipFile(zip_filename, "w") as zipf:
        for filename in ["config.json", "state.json", "main.py", "requirements.txt", "Procfile"]:
            if os.path.exists(filename):
                zipf.write(filename)

    # Send ZIP file to owner
    if context:
        try:
            caption = (
                f"🧩 <b>Bot Backup Completed</b>\n"
                f"📅 <b>Date:</b> {date_str}\n"
                f"⏰ <b>Time:</b> {time_str}"
            )
            with open(zip_filename, "rb") as f:
                await context.bot.send_document(
                    chat_id=OWNER_ID,
                    document=f,
                    caption=caption,
                    parse_mode="HTML"
                )
        except Exception as e:
            print(f"Failed to send backup: {e}")

    # Edit original message if triggered by inline button
    if query:
        await query.edit_message_text(
            text="✅ Full backup ZIP sent to your PM!",
            reply_markup=get_main_inline_keyboard()
        )

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
    
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("🛠 Method 3", callback_data="method_3")])

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
        await update.message.reply_text(
            "<b>🧰 BOT CONTROL PANEL – OWNER ACCESS</b>\n\n"
            "<b>📌 Core Management</b>\n"
            "• /start — Restart bot session\n"
            "• /ping — Check bot uptime\n"
            "• /rules — View bot usage policy\n\n"
            "<b>📤 Upload Configuration</b>\n"
            "• /setchannelid — Set target channel\n"
            "• /setcaption — Define custom caption\n"
            "• /resetcaption — Clear caption\n"
            "• /resetchannelid — Clear channel setting\n"
            "• /reset — Full user data reset\n\n"
            "<b>👥 User Access Control</b>\n"
            "• /adduser — Grant user access\n"
            "• /removeuser — Revoke access\n"
            "• /userlist — View allowed users",
            parse_mode="HTML"
        )

    elif user_id in ALLOWED_USERS:
        await update.message.reply_text(
            "<b>🧩 USER MENU</b>\n\n"
            "<b>🔧 Essentials</b>\n"
            "• /start — Start interaction\n"
            "• /ping — Bot status\n"
            "• /rules — Usage guidelines\n\n"
            "<b>⚙️ Settings</b>\n"
            "• /setchannelid — Set your upload channel\n"
            "• /setcaption — Set your caption\n"
            "• /resetchannelid — Reset channel\n"
            "• /resetcaption — Reset caption\n"
            "• /reset — Reset all settings",
            parse_mode="HTML"
        )

    else:
        await update.message.reply_text("🚫 Access Denied: You are not authorized to use this bot.")
        
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

        # ✨ NEW: Save first_name and username properly
        try:
            user = await context.bot.get_chat(user_id)
            USER_DATA[str(user_id)] = {
                "first_name": user.first_name or "—",
                "username": user.username or "—",
                "channel": USER_DATA.get(str(user_id), {}).get("channel", "—")
            }
        except Exception as e:
            print(f"Failed to fetch user info: {e}")
            # Fallback if cannot fetch
            USER_DATA[str(user_id)] = {
                "first_name": "—",
                "username": "—",
                "channel": "—"
            }

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
        if update.message:
            await update.message.reply_text("𝖮𝗋𝗎𝗎 𝗉𝖺𝗂𝗒𝖺𝗌𝖺𝗏𝗎𝗄𝗄𝗎🥴 𝖯𝗎𝗋𝖺𝗃𝖺𝗇𝖺𝗆 𝗂𝗅𝖺 𝖽𝖺𝖺 𝗉𝗎𝗇𝖽𝖺 🫵🏼")
        elif update.callback_query:
            await update.callback_query.message.reply_text("𝖮𝗋𝗎𝗎 𝗉𝖺𝗂𝗒𝖺𝗌𝖺𝗏𝗎𝗄𝗄𝗎🥴 𝖯𝗎𝗋𝖺𝗃𝖺𝗇𝖺𝗆 𝗂𝗅𝖺 𝖽𝖺𝖺 𝗉𝗎𝗇𝖽𝖺 🫵🏼")
        return

    if not ALLOWED_USERS:
        if update.message:
            await update.message.reply_text("No allowed users.")
        elif update.callback_query:
            await update.callback_query.message.reply_text("No allowed users.")
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

    text = "\n".join(lines)

    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("𝖵𝖺𝗇𝗍𝗁𝖺 𝗈𝖽𝖺𝗇𝖾 𝖮𝗆𝖻𝗎𝗍𝗁𝖺 𝖽𝖺𝖺 𝖻𝖺𝖺𝖽𝗎🫂")
        return

    uptime_seconds = int(time.time() - START_TIME)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    ping_ms = round(random.uniform(10, 60), 2)
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    date_str = now.strftime("%d-%m-%Y")
    time_str = now.strftime("%I:%M %p")

    msg = (
        "<b>⚙️ 𝗦𝗬𝗦𝗧𝗘𝗠 𝗦𝗧𝗔𝗧𝗨𝗦 𝗥𝗘𝗣𝗢𝗥𝗧</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>Date:</b> <code>{date_str}</code>\n"
        f"⏰ <b>Time:</b> <code>{time_str}</code>\n"
        f"🧾 <b>Update:</b> <code>{UPDATE_DATE}</code>\n"
        f"⏱️ <b>Uptime:</b> <code>{days}D {hours}H {minutes}M {seconds}S</code>\n"
        f"⚡ <b>Latency:</b> <code>{ping_ms} ms</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧠 <i>Powered by</i> <a href='https://t.me/Ceo_DarkFury'>@Ceo_DarkFury</a>"
    )

    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)

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
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("🗣️𝖮𝗈𝗆𝖻𝗎𝗎𝗎")
        return

    # Reset only this user's data
    USER_DATA[str(user_id)] = {
        "channel": "",
        "caption": ""
    }
    save_config()

    # Decide which keyboard to show
    if user_id == OWNER_ID:
        reply_markup = owner_keyboard
    else:
        reply_markup = allowed_user_keyboard

    await update.message.reply_text(
        "🧹 *Your data cleaned\\!*\n"
        "No more caption or channel\\. 🚮\n"
        "Ready to Setup\\. 🚀",
        parse_mode="MarkdownV2",
        reply_markup=reply_markup
    )
    
async def set_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.effective_message.reply_text("🗣️ 𝖮𝗈𝗆𝖻𝗎𝗎𝗎")
        return

    USER_STATE[user_id] = {"status": "waiting_channel"}
    await update.effective_message.reply_text(
        "🔧 <b>Setup Time!</b><br>"
        "Send me your Channel ID now. 📡<br>"
        "Format: <code>@yourchannel</code> or <code>-100xxxxxxxxxx</code><br><br>"
        "⚠️ Make sure the bot is added as ADMIN in that channel!",
        parse_mode="HTML"
    )
    
async def set_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.effective_message.reply_text("𝖮𝗈𝗆𝖻𝗎𝗎𝗎 😭")
        return

    USER_STATE[user_id] = {"status": "waiting_caption"}
    await update.effective_message.reply_text(
        "📝 *Caption Time\\!*\n"
        "Send me your Caption Including\\. ↙️\n"
        "The Placeholder `Key \\-` 🔑",
        parse_mode="MarkdownV2"
    )

async def user_viewsetup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized Access.")
        return

    user_data = USER_DATA.get(str(user_id), {})
    channel = user_data.get("channel")
    caption = user_data.get("caption")
    apk_count = USER_STATE.get(user_id, {}).get("apk_posted_count", 0)
    key_count = USER_STATE.get(user_id, {}).get("key_used_count", 0)

    # Channel and caption display
    channel_display = channel if channel else "NoT !"
    caption_status = "SaveD !" if caption else "NoT !"

    msg = (
        f"<pre>┌────── 𝗦𝗬𝗦𝗧𝗘𝗠 𝗦𝗧𝗔𝗧𝗨𝗦 ──────┐\n"
        f"User ID     : {user_id}\n"
        f"Uplink Key  : ✅ AUTHORIZED\n"
        f"Session     : LIVE\n"
        f"├───────────────────────────┤\n"
        f" SESSION\n"
        f" Channel : {channel_display}\n"
        f" Caption : {caption_status}\n"
        f"├───────────────────────────┤\n"
        f"📊 STATS SYNTHESIS\n"
        f"🔢 Total Keys     : {key_count} Injected\n"
        f"📦 APKs Processed : {apk_count} Delivered\n"
        f"└──────── END OF REPORT ────────┘</pre>"
    )

    await update.message.reply_text(msg, parse_mode="HTML")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # --- New Broadcast Receiving (for photos/images) ---
    if user_id == OWNER_ID and BROADCAST_SESSION.get(user_id, {}).get("waiting_for_message"):
        BROADCAST_SESSION[user_id]["message"] = update.message
        BROADCAST_SESSION[user_id]["waiting_for_message"] = False

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm", callback_data="confirm_broadcast"),
             InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")]
        ])
        
        await update.message.reply_text(
            "📨 *Preview Received!*\n\n✅ Confirm to send broadcast\n❌ Cancel to abort",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # --- New Broadcast Receiving (for documents like APK, PDF, etc.) ---
    if user_id == OWNER_ID and BROADCAST_SESSION.get(user_id, {}).get("waiting_for_message"):
        BROADCAST_SESSION[user_id]["message"] = update.message
        BROADCAST_SESSION[user_id]["waiting_for_message"] = False
    
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm", callback_data="confirm_broadcast"),
             InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")]
        ])
        
        await update.message.reply_text(
            "📨 *Preview Received!*\n\n✅ Confirm to send broadcast\n❌ Cancel to abort",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
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

async def auto4_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    doc = message.document

    if not doc or not doc.file_name.lower().endswith(".apk"):
        return

    chat_id = str(update.effective_chat.id)
    source_channel = str(AUTO_SETUP["setup4"].get("source_channel"))

    if chat_id != source_channel or not AUTO_SETUP["setup4"].get("enabled", False):
        return

    caption = message.caption or ""

    AUTO4_STATE["pending_apks"].append({
        "file_id": doc.file_id,
        "caption": caption,
        "message_id": message.message_id,
        "chat_id": chat_id,
        "timestamp": time.time(),
        "caption_entities": message.caption_entities and [e.to_dict() for e in message.caption_entities]
    })

    if not AUTO4_STATE["timer"]:
        AUTO4_STATE["waiting_since"] = time.time()
        AUTO4_STATE["timer"] = asyncio.create_task(process_auto4_delayed(context))

async def process_auto4_delayed(context: ContextTypes.DEFAULT_TYPE):
    try:
        countdown_msg = await context.bot.send_message(
            OWNER_ID,
            "<b>⏳ Auto 4 - 20 seconds left...</b>",
            parse_mode="HTML"
        )

        for i in range(19, 0, -1):
            await asyncio.sleep(1)
            try:
                await context.bot.edit_message_text(
                    chat_id=OWNER_ID,
                    message_id=countdown_msg.message_id,
                    text=f"<b>⏳ Auto 4 - {i} seconds left...</b>",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        await asyncio.sleep(1)

        source_channel = AUTO_SETUP["setup4"]["source_channel"]
        valid_apks = []

        for apk in AUTO4_STATE["pending_apks"]:
            try:
                await context.bot.forward_message(
                    chat_id=OWNER_ID,
                    from_chat_id=source_channel,
                    message_id=apk["message_id"]
                )
                valid_apks.append(apk)
            except Exception:
                pass

        if not valid_apks:
            await context.bot.edit_message_text(
                chat_id=OWNER_ID,
                message_id=countdown_msg.message_id,
                text="❌ <b>Auto 4: All APKs deleted. Declined.</b>",
                parse_mode="HTML"
            )
            return

        key = None
        setup_type = "Setup 1" if len(valid_apks) == 1 else "Setup 2"

        # Key extraction
        await asyncio.sleep(3 if setup_type == "Setup 2" else 0)
        for apk in (valid_apks[::-1] if setup_type == "Setup 2" else valid_apks):
            caption = apk["caption"]
            match = re.search(r'Key\s*-\s*(\S+)', caption)
            if match:
                key = match.group(1)
                break
            if "caption_entities" in apk:
                for entity in apk["caption_entities"]:
                    if entity["type"] == "code":
                        offset = entity["offset"]
                        length = entity["length"]
                        key = caption[offset:offset + length]
                        break
            if key:
                break

        if key:
            await send_auto4_apks(valid_apks, key, context, countdown_msg, setup_type)
        else:
            await context.bot.edit_message_text(
                chat_id=OWNER_ID,
                message_id=countdown_msg.message_id,
                text=f"❌ <b>Auto 4 {setup_type}: No key found in any APK.</b>",
                parse_mode="HTML"
            )

    except Exception as e:
        await context.bot.send_message(
            OWNER_ID,
            f"⚠️ Auto 4 Error:\n<code>{e}</code>",
            parse_mode="HTML"
        )
    finally:
        AUTO4_STATE.update({
            "pending_apks": [],
            "timer": None,
            "setup_mode": 1,
            "waiting_since": None
        })
    
async def send_auto4_apks(apks, key, context: ContextTypes.DEFAULT_TYPE, countdown_msg, setup_type):
    dest_channel = AUTO_SETUP["setup4"].get("dest_channel")
    caption_template = AUTO_SETUP["setup4"].get("dest_caption")
    style = AUTO_SETUP["setup4"].get("style", "mono")
    source_channel = AUTO_SETUP["setup4"].get("source_channel")

    if not dest_channel or not caption_template:
        await context.bot.edit_message_text(
            chat_id=OWNER_ID,
            message_id=countdown_msg.message_id,
            text="❌ <b>Auto4: Destination channel or caption missing.</b>",
            parse_mode="HTML"
        )
        return

    post_link = "Unavailable"
    success_count = 0

    for apk in apks:
        if style == "quote":
            caption_final = f"<blockquote>Key - <code>{key}</code></blockquote>"
        else:
            caption_final = caption_template.replace("Key -", f"Key - <code>{key}</code>")

        try:
            msg = await context.bot.send_document(
                chat_id=dest_channel,
                document=apk["file_id"],
                caption=caption_final,
                parse_mode="HTML"
            )
            if post_link == "Unavailable":
                post_link = f"https://t.me/c/{str(dest_channel).lstrip('-100')}/{msg.message_id}"
            success_count += 1
        except Exception as e:
            await context.bot.send_message(OWNER_ID, f"❌ Failed to send APK: <code>{e}</code>", parse_mode="HTML")

    AUTO_SETUP["setup4"]["completed_count"] += 1
    save_config()

    summary = (
        f"✅ <b>Auto 4 Completed</b>\n"
        f"├─ 👤 Source : <code>{source_channel}</code>\n"
        f"├─ 🎯 Destination : <code>{dest_channel}</code>\n"
        f"├─ 📡 Key : <code>{key}</code>\n"
        f"└─ 🔗 Post Link : <a href='{post_link}'>Click Here</a>"
    )
    
    await context.bot.edit_message_text(
        chat_id=OWNER_ID,
        message_id=countdown_msg.message_id,
        text=summary,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

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

        # Track usage counts
        state = USER_STATE.setdefault(user_id, {})
        state["apk_posted_count"] = state.get("apk_posted_count", 0) + 1
        state["key_used_count"] = state.get("key_used_count", 0) + 1

        # NEW: Track 6h / 24h / weekly stats
        state["hourly_keys"] = state.get("hourly_keys", 0) + 1
        state["hourly_apks"] = state.get("hourly_apks", 0) + 1
        state["daily_keys"] = state.get("daily_keys", 0) + 1
        state["daily_apks"] = state.get("daily_apks", 0) + 1
        state["weekly_keys"] = state.get("weekly_keys", 0) + 1
        state["weekly_apks"] = state.get("weekly_apks", 0) + 1
        state["monthly_keys"] = state.get("monthly_keys", 0) + 1
        state["monthly_apks"] = state.get("monthly_apks", 0) + 1
        state["last_method"] = "Method 1"
        state["last_style"] = "normal"
        state["last_used_time"] = time.time()

        await update.message.reply_text("✅ *APK posted successfully!*", parse_mode="Markdown")

    else:
        USER_STATE[user_id]["waiting_key"] = True
        USER_STATE[user_id]["file_id"] = doc.file_id
        await update.message.reply_text("⏳ *Send the Key now!*", parse_mode="Markdown")

async def process_method2_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document
    file_id = doc.file_id
    file_name = doc.file_name or ""

    state = USER_STATE.setdefault(user_id, {})

    # Reset previous session if waiting_key is True
    if state.get("waiting_key"):
        state["session_files"] = []
        state["session_filenames"] = []
        state["saved_key"] = None
        state["waiting_key"] = False
        state["quote_applied"] = False
        state["mono_applied"] = False
        state["progress_message_id"] = None

    session_files = state.setdefault("session_files", [])
    session_filenames = state.setdefault("session_filenames", [])

    session_files.append(file_id)
    session_filenames.append(file_name)

    chat_id = update.message.chat_id
    message_id = state.get("progress_message_id")

    if message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"✅ {len(session_files)} APKs Received! ☑️\nWaiting 5 seconds for next APK...",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"[Progress Message Error] User: {user_id} | Error: {e}")
            message_id = None

    if not message_id:
        sent_msg = await update.message.reply_text(
            f"✅ {len(session_files)} APKs Received! ☑️\nWaiting 5 seconds for next APK...",
            parse_mode="Markdown"
        )
        state["progress_message_id"] = sent_msg.message_id

    state["last_apk_time"] = time.time()

    # NEW: Track last method usage immediately
    state["last_method"] = "Method 2"
    state["last_style"] = state.get("key_mode", "normal")
    state["last_used_time"] = time.time()

    if len(session_files) >= 3 and not state.get("waiting_key") and not state.get("key_prompt_sent"):
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=state.get("progress_message_id"),
                text="🔑 *Send the Key now!* (Only one Key for 2–3 APKs)",
                parse_mode="Markdown"
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text="🔑 *Send the Key now!* (Only one Key for 2–3 APKs)",
                parse_mode="Markdown"
            )
        state["waiting_key"] = True
        state["key_prompt_sent"] = True
        state["progress_message_id"] = None
    else:
        context.application.create_task(countdown_and_check(user_id, chat_id, context))

async def send_user_stats_report(context: ContextTypes.DEFAULT_TYPE, hours=6):
    now = time.time()
    for user_id in ALLOWED_USERS:
        state = USER_STATE.get(user_id, {})
        user_data = USER_DATA.get(str(user_id), {})

        # Check if user was active in the last N hours
        last_used = state.get("last_used_time", 0)
        active = (now - last_used) <= (hours * 3600)

        channel = user_data.get("channel", "NoT !")
        caption = "SaveD !" if user_data.get("caption") else "NoT !"
        key_mode = state.get("last_method", "—").replace("method", "Method ").title()
        style = state.get("last_style", "normal")

        # Select correct stats based on report type
        if hours == 6:
            keys = state.get("hourly_keys", 0)
            apks = state.get("hourly_apks", 0)
        elif hours == 24:
            keys = state.get("daily_keys", 0)
            apks = state.get("daily_apks", 0)
        elif hours == 168:
            keys = state.get("weekly_keys", 0)
            apks = state.get("weekly_apks", 0)
        elif hours == 720:
            keys = state.get("monthly_keys", 0)
            apks = state.get("monthly_apks", 0)
        else:
            keys = 0
            apks = 0

        status = "Active" if active else "Inactive"

        # Report title based on hours
        report_label = {
            6: "𝟲 𝗛𝗢𝗨𝗥𝗦 𝗥𝗘𝗣𝗢𝗥𝗧",
            24: "𝗗𝗔𝗜𝗟𝗬 𝗥𝗘𝗣𝗢𝗥𝗧",
            168: "𝗪𝗘𝗘𝗞𝗟𝗬 𝗥𝗘𝗣𝗢𝗥𝗧",
            720: "𝗠𝗢𝗡𝗧𝗛𝗟𝗬 𝗥𝗘𝗣𝗢𝗥𝗧"
        }.get(hours, f"{hours}𝗛 𝗥𝗘𝗣𝗢𝗥𝗧")

        msg = (
            f"<pre>"
            f"┌──── {report_label} ─────┐\n"
            f"│ CHANNEL        >> {channel}\n"
            f"│ CAPTION        >> {caption}\n"
            f"│ KEY_MODE       >> {key_mode}\n"
            f"│ STYLE          >> {style}\n"
            f"│ STATUS         >> {status}\n"
            f"│ KEYS_SENT      >> {keys}\n"
            f"│ TOTAL_APKS     >> {apks}\n"
            f"└──────── 𝗘𝗡𝗗 𝗢𝗙 𝗥𝗘𝗣𝗢𝗥𝗧 ────────┘"
            f"</pre>"
        )

        try:
            await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
        except Exception as e:
            print(f"Failed to send report to {user_id}: {e}")

async def reset_stats(hours=6):
    for user_id in ALLOWED_USERS:
        if user_id not in USER_STATE:
            continue
        if hours == 6:
            USER_STATE[user_id]["hourly_keys"] = 0
            USER_STATE[user_id]["hourly_apks"] = 0
        elif hours == 24:
            USER_STATE[user_id]["daily_keys"] = 0
            USER_STATE[user_id]["daily_apks"] = 0
        elif hours == 168:  # weekly
            USER_STATE[user_id]["weekly_keys"] = 0
            USER_STATE[user_id]["weekly_apks"] = 0
        elif hours == 720:
            USER_STATE[user_id]["monthly_keys"] = 0
            USER_STATE[user_id]["monthly_apks"] = 0
        
async def schedule_stat_reports(application: Application):
    while True:
        now = datetime.now(ZoneInfo("Asia/Kolkata"))

        # 6-Hour Report: 2am, 8am, 2pm
        if now.hour in [2, 8, 14] and now.minute == 0:
            await send_user_stats_report(application.bot, hours=6)
            await reset_stats(hours=6)

        # Daily Report: 8pm
        if now.hour == 20 and now.minute == 0:
            await send_user_stats_report(application.bot, hours=24)
            await reset_stats(hours=24)

        # Weekly Report: Sunday 10am
        if now.weekday() == 6 and now.hour == 10 and now.minute == 0:
            await send_user_stats_report(application.bot, hours=168)
            await reset_stats(hours=168)

        # Monthly Report: Last day of month at 10pm
        tomorrow = now + timedelta(days=1)
        if now.hour == 22 and now.minute == 0 and tomorrow.day == 1:
            await send_user_stats_report(application.bot, hours=720)
            await reset_stats(hours=720)

        await asyncio.sleep(55)  # safer than 60, prevents skipping exact minutes

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
            caption = (
                saved_caption.replace("Key -", f"<blockquote>Key - <code>{key}</code></blockquote>")
                if is_last_apk or len(session_files) == 1
                else f"<blockquote>Key - <code>{key}</code></blockquote>"
            )
        elif key_mode == "mono":
            caption = (
                saved_caption.replace("Key -", f"Key - <code>{key}</code>")
                if is_last_apk or len(session_files) == 1
                else f"Key - <code>{key}</code>"
            )
        else:
            caption = (
                saved_caption.replace("Key -", f"Key - {key}")
                if is_last_apk or len(session_files) == 1
                else f"Key - {key}"
            )

        sent_message = await context.bot.send_document(
            chat_id=channel_id,
            document=file_id,
            caption=caption,
            parse_mode="HTML"
        )
        posted_ids.append(sent_message.message_id)
        last_message = sent_message

    # Track total APKs and Keys processed
    USER_STATE[user_id]["apk_posted_count"] = USER_STATE.get(user_id, {}).get("apk_posted_count", 0) + len(posted_ids)
    USER_STATE[user_id]["key_used_count"] = USER_STATE.get(user_id, {}).get("key_used_count", 0) + 1

    USER_STATE[user_id]["apk_posts"] = posted_ids

    if len(posted_ids) == 1:
        USER_STATE[user_id]["session_files"] = []
        USER_STATE[user_id]["session_filenames"] = []
        USER_STATE[user_id]["saved_key"] = None
        USER_STATE[user_id]["waiting_key"] = False
        USER_STATE[user_id]["last_apk_time"] = None
        USER_STATE[user_id]["key_mode"] = "normal"
    else:
        USER_STATE[user_id]["session_files"] = session_files
        USER_STATE[user_id]["waiting_key"] = False
        USER_STATE[user_id]["last_apk_time"] = None
        USER_STATE[user_id]["key_prompt_sent"] = False

    if last_message:
        if channel_id.startswith("@"):
            post_link = f"https://t.me/{channel_id.strip('@')}/{last_message.message_id}"
        elif channel_id.startswith("-100"):
            post_link = f"https://t.me/c/{channel_id.replace('-100', '')}/{last_message.message_id}"
        else:
            post_link = "Unknown"

        USER_STATE[user_id]["last_post_link"] = post_link

    buttons = [
        [InlineKeyboardButton("📄 View Last Post", url=post_link)]
    ]
    
    if len(posted_ids) >= 2:
        buttons.append([
            InlineKeyboardButton("✏️ 𝖠𝗎𝗍𝗈 𝖠𝗅𝗅 𝖠𝗉𝗄 𝖢𝖺𝗉𝗍𝗂𝗈𝗇", callback_data="auto_recaption"),
            InlineKeyboardButton("✨ 𝖠𝗎𝗍𝗈 𝖫𝖺𝗌𝗍 𝖠𝗉𝗄 𝖢𝖺𝗉𝗍𝗂𝗈𝗇", callback_data="auto_last_caption")
        ])
        buttons.append([
            InlineKeyboardButton("🔑 𝖠𝗎𝗍𝗈 𝖫𝖺𝗌𝗍 𝖠𝗉𝗄 𝖮𝗇𝗅𝗒 𝖪𝖾𝗒", callback_data="last_caption_key")
        ])
    
    buttons.append([
        InlineKeyboardButton("🗑️ Delete APK Post", callback_data="delete_apk_post"),
        InlineKeyboardButton("🧹 Erase All", callback_data="erase_all")
    ])
    
    buttons.append([
        InlineKeyboardButton("🔙 Back to Methods", callback_data="back_to_methods")
    ])

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
            text="✅ <b>𝖠𝗎𝗍𝗈 𝖠𝗅𝗅 𝖠𝗉𝗄 𝖢𝖺𝗉𝗍𝗂𝗈𝗇ed Successfully!</b>\n\nManage your posts below:",
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

async def auto_last_caption(user_id, context):
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
        await context.bot.send_message(chat_id=user_id, text="⚠️ No session data found.")
        return

    for msg_id in old_posts:
        try:
            await context.bot.delete_message(chat_id=channel_id, message_id=msg_id)
        except:
            pass

    media = []
    for idx, file_id in enumerate(session_files, start=1):
        if idx == len(session_files):
            if key_mode == "quote":
                final_caption = saved_caption.replace("Key -", f"<blockquote>Key - <code>{key}</code></blockquote>")
            elif key_mode == "mono":
                final_caption = saved_caption.replace("Key -", f"Key - <code>{key}</code>")
            else:
                final_caption = saved_caption.replace("Key -", f"Key - {key}")
            media.append(InputMediaDocument(media=file_id, caption=final_caption, parse_mode="HTML"))
        else:
            media.append(InputMediaDocument(media=file_id))

    new_posts = await context.bot.send_media_group(chat_id=channel_id, media=media)
    USER_STATE[user_id]["apk_posts"] = [m.message_id for m in new_posts]
    last_msg = new_posts[-1]

    post_link = (
        f"https://t.me/{channel_id.strip('@')}/{last_msg.message_id}"
        if channel_id.startswith("@")
        else f"https://t.me/c/{channel_id.replace('-100', '')}/{last_msg.message_id}"
    )
    USER_STATE[user_id]["last_post_link"] = post_link

    buttons = [
        [InlineKeyboardButton("📄 View Last Post", url=post_link)],
        [InlineKeyboardButton("🗑️ Delete APK Post", callback_data="delete_apk_post")],
        [InlineKeyboardButton("🔙 Back to Methods", callback_data="back_to_methods")]
    ]
    await context.bot.edit_message_text(
        chat_id=user_id,
        message_id=preview_message_id,
        text="✅ <b>𝖠𝗎𝗍𝗈 𝖫𝖺𝗌𝗍 𝖠𝗉𝗄 𝖢𝖺𝗉𝗍𝗂𝗈𝗇 Successfully!</b>\n\nManage your posts below:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    USER_STATE[user_id]["session_files"] = []
    USER_STATE[user_id]["session_filenames"] = []
    USER_STATE[user_id]["saved_key"] = None
    USER_STATE[user_id]["waiting_key"] = False
    USER_STATE[user_id]["last_apk_time"] = None

async def last_caption_key(user_id, context):
    user_info = USER_DATA.get(str(user_id), {})
    state = USER_STATE.get(user_id, {})
    channel_id = user_info.get("channel")
    session_files = state.get("session_files", [])
    key = state.get("saved_key", "")
    key_mode = state.get("key_mode", "normal")
    old_posts = state.get("apk_posts", [])
    preview_message_id = state.get("preview_message_id")

    if not channel_id or not session_files or not key:
        await context.bot.send_message(chat_id=user_id, text="⚠️ No session data found.")
        return

    for msg_id in old_posts:
        try:
            await context.bot.delete_message(chat_id=channel_id, message_id=msg_id)
        except:
            pass

    media = []
    for idx, file_id in enumerate(session_files, start=1):
        if idx == len(session_files):
            if key_mode == "quote":
                caption = f"<blockquote>Key - <code>{key}</code></blockquote>"
            elif key_mode == "mono":
                caption = f"Key - <code>{key}</code>"
            else:
                caption = f"Key - {key}"
            media.append(InputMediaDocument(media=file_id, caption=caption, parse_mode="HTML"))
        else:
            media.append(InputMediaDocument(media=file_id))

    new_posts = await context.bot.send_media_group(chat_id=channel_id, media=media)
    USER_STATE[user_id]["apk_posts"] = [m.message_id for m in new_posts]
    last_msg = new_posts[-1]

    post_link = (
        f"https://t.me/{channel_id.strip('@')}/{last_msg.message_id}"
        if channel_id.startswith("@")
        else f"https://t.me/c/{channel_id.replace('-100', '')}/{last_msg.message_id}"
    )
    USER_STATE[user_id]["last_post_link"] = post_link

    buttons = [
        [InlineKeyboardButton("📄 View Last Post", url=post_link)],
        [InlineKeyboardButton("🗑️ Delete APK Post", callback_data="delete_apk_post")],
        [InlineKeyboardButton("🔙 Back to Methods", callback_data="back_to_methods")]
    ]
    await context.bot.edit_message_text(
        chat_id=user_id,
        message_id=preview_message_id,
        text="✅ <b>𝖠𝗎𝗍𝗈 𝖫𝖺𝗌𝗍 𝖠𝗉𝗄 𝖮𝗇𝗅𝗒 𝖪𝖾𝗒 Successfully!</b>\n\nManage your posts below:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    USER_STATE[user_id]["session_files"] = []
    USER_STATE[user_id]["session_filenames"] = []
    USER_STATE[user_id]["saved_key"] = None
    USER_STATE[user_id]["waiting_key"] = False
    USER_STATE[user_id]["last_apk_time"] = None

async def erase_all_session(user_id, context):
    state = USER_STATE.get(user_id, {})
    state["session_files"] = []
    state["session_filenames"] = []
    state["saved_key"] = None
    state["waiting_key"] = False
    state["key_prompt_sent"] = False
    state["last_apk_time"] = None
    state["progress_message_id"] = None

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

async def settings_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    keyboard = [
        [InlineKeyboardButton("👥 View Users", callback_data="view_users"),
         InlineKeyboardButton("🔧 View Auto Setup", callback_data="view_autosetup")],
        [InlineKeyboardButton("🔄 Backup Config", callback_data="backup_config")],
        [InlineKeyboardButton("♻️ Force Reset All", callback_data="force_reset")],
        [InlineKeyboardButton("🌟 Bot Admin Link", callback_data="bot_admin_link")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_methods")]
    ]
    await update.message.reply_text(
        "🛠️ <b>Settings Panel</b>\nManage your bot below:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    try:
        await query.answer()
    except Exception:
        await query.message.reply_text("⏳ Session expired or invalid! ❌\nPlease restart using /start.")
        return

    data = query.data

    if data == "view_users":
        if not ALLOWED_USERS:
            await query.edit_message_text(
                "❌ No allowed users found.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="settings_back")]
                ])
            )
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
                f"└─ 🆔 <b>ID:</b> <code>{user_id}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="settings_back")]
            ]),
            disable_web_page_preview=True
        )
        return

    elif data == "view_autosetup":
        await query.edit_message_text(
            "<b>🔧 Select a setup to view details:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Auto Setup 1", callback_data="viewsetup1")],
                [InlineKeyboardButton("Auto Setup 2", callback_data="viewsetup2")],
                [InlineKeyboardButton("Auto Setup 3", callback_data="viewsetup3")],
                [InlineKeyboardButton("Auto Setup 4", callback_data="viewsetup4")],
                [InlineKeyboardButton("🔙 Back", callback_data="settings_back")]
            ])
        )
        return
    
    elif data.startswith("viewsetup"):
        setup_num = data[-1]
        s = AUTO_SETUP.get(f"setup{setup_num}", {})
    
        total_keys = s.get("completed_count", 0)
        total_apks = s.get("processed_count", total_keys)  # fallback
        source = s.get("source_channel", "Not Set")
        dest = s.get("dest_channel", "Not Set")
        caption_ok = "✅" if s.get("dest_caption") else "❌"
        key_mode = s.get("key_mode", "auto").capitalize()
        style = s.get("style", "mono").capitalize()
        status = "✅ ON" if s.get("enabled") else "⛔ OFF"
    
        msg = (
            f"<pre>"
            f"┌──── AUTO {setup_num} SYSTEM DIAG ─────┐\n"
            f"│ SOURCE        >>  {source}\n"
            f"│ DESTINATION   >>  {dest}\n"
            f"│ CAPTION       >>  {caption_ok}\n"
            f"│ KEY_MODE      >>  {key_mode}\n"
            f"│ STYLE         >>  {style}\n"
            f"│ STATUS        >>  {status}\n"
            f"│ KEYS_SENT     >>  {total_keys}\n"
            f"│ TOTAL_APKS    >>  {total_apks} APK{'s' if total_apks != 1 else ''}\n"
            f"└──────── END OF REPORT ────────┘"
            f"</pre>"
        )
    
        await query.edit_message_text(
            text=msg,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="view_autosetup")]
            ])
        )
        return
    
    elif data == "backup_config" and query.from_user.id == OWNER_ID:
        await query.delete_message()
        await backup_config(context=context)
        return

    elif data == "force_reset":
        await query.edit_message_text(
            "⚠️ <b>Are you sure you want to reset all sessions?</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes", callback_data="confirm_reset"),
                 InlineKeyboardButton("❌ No", callback_data="settings_back")]
            ])
        )
        return

    elif data == "confirm_reset":
        for user in USER_STATE:
            USER_STATE[user] = {}
        save_state()
        await query.edit_message_text(
            "♻️ <b>All sessions have been reset.</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="settings_back")]
            ])
        )
        return

    elif data == "settings_back":
        await query.edit_message_text(
            "🛠️ <b>Settings Panel</b>\nManage your bot below:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 View Users", callback_data="view_users"),
                 InlineKeyboardButton("🔧 View Auto Setup", callback_data="view_autosetup")],
                [InlineKeyboardButton("🔄 Backup Config", callback_data="backup_config")],
                [InlineKeyboardButton("♻️ Force Reset All", callback_data="force_reset")],
                [InlineKeyboardButton("🌟 Bot Admin Link", callback_data="bot_admin_link")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_methods")]
            ])
        )
    
    elif data == "bot_admin_link" and query.from_user.id == OWNER_ID:
        USER_STATE[user_id]["awaiting_admin_link"] = True
        await query.edit_message_text("🔗 Send the new Bot Admin link (must start with https://)")
        return
    
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
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🧹 Erase All", callback_data="erase_all_session")]
                        ])
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
        if session_files and not state.get("waiting_key", False) and not state.get("key_prompt_sent", False):
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
            USER_STATE[user_id]["key_prompt_sent"] = True
            USER_STATE[user_id]["progress_message_id"] = None

    except Exception as e:
        print(f"Countdown error: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BOT_ACTIVE  # ← ADD THIS LINE

    user_id = update.effective_user.id
    message_text = update.message.text.strip().lower()
    
    if not BOT_ACTIVE and user_id != OWNER_ID:
        await update.message.reply_text("🚫 The bot is currently turned off by the admin.")
        return
    
    # --- New Broadcast Receiving (for text messages) ---
    if user_id == OWNER_ID and BROADCAST_SESSION.get(user_id, {}).get("waiting_for_message"):
        BROADCAST_SESSION[user_id]["message"] = update.message
        BROADCAST_SESSION[user_id]["waiting_for_message"] = False
    
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm", callback_data="confirm_broadcast"),
             InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")]
        ])
        
        await update.message.reply_text(
            "📨 *Preview Received!*\n\n✅ Confirm to send broadcast\n❌ Cancel to abort",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return
    
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
    elif message_text == "viewsetup":
        await user_viewsetup(update, context)
        return
    elif message_text.lower() == "on" and user_id == OWNER_ID:
        BOT_ACTIVE = True
        save_bot_config()
        await update.message.reply_text("✅ Bot is now active. Users can interact again.")
        return
    elif message_text.lower() == "off" and user_id == OWNER_ID:
        BOT_ACTIVE = False
        save_bot_config()
        await update.message.reply_text("⛔ Bot is now inactive. User interaction is disabled.")
        return
    elif message_text == "settings" and user_id == OWNER_ID:
        await settings_panel(update, context)
        return
    elif message_text == "broadcast" and user_id == OWNER_ID:
        await update.message.reply_text(
            "📣 *Broadcast Mode Started!*\n\n"
            "Please send the message (text/photo/document/file) you want to broadcast.",
            parse_mode="Markdown"
        )
        BROADCAST_SESSION[user_id] = {"waiting_for_message": True}
        return
    elif message_text == "channel":
        user_channel = USER_DATA.get(str(user_id), {}).get("channel", "Not Set")
        formatted_channel = (user_channel[:26] + '…') if len(user_channel) > 28 else user_channel
        await update.message.reply_text(
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "<b>      📡 CHANNEL INFO       </b>\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>📎 Current:</b> <code>{formatted_channel}</code>",
            parse_mode="HTML"
        )
        return
    elif message_text == "caption":
        user_caption = USER_DATA.get(str(user_id), {}).get("caption", "Not Set")
    
        await update.message.reply_text(
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            "<b>     📝 CAPTION TEMPLATE     </b>\n"
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<code>{user_caption}</code>" if user_caption != "Not Set" else "<i>No caption set.</i>",
            parse_mode="HTML"
        )
        return
    elif message_text == "userstats" and user_id == OWNER_ID:
        from datetime import datetime
    
        lines = [
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>",
            "<b>    🧠 𝗔𝗟𝗟 𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦 𝗥𝗘𝗣𝗢𝗥𝗧    </b>",
            "<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>"
        ]
    
        if not ALLOWED_USERS:
            lines.append("\n<b>⚠️ No authorized users found.</b>")
        else:
            for index, uid in enumerate(ALLOWED_USERS, start=1):
                user = USER_DATA.get(str(uid), {})
                state = USER_STATE.get(uid, {})
                name = user.get("first_name", "—")
                uname = user.get("username", "—")
                caption = "✅ Yes" if user.get("caption") else "❌ No"
                channel = user.get("channel", "—")
                apk_count = state.get("apk_posted_count", 0)
                key_count = state.get("key_used_count", 0)
                last_method = state.get("last_method", "—")
    
                lines.extend([
                    "",
                    f"<b>👤 User {index}</b> — <code>{uid}</code>",
                    f"<b>├─ 🔖 Name:</b> {name}",
                    f"<b>├─ 🧬 Username:</b> @{uname}" if uname != "—" else "<b>├─ 🧬 Username:</b> —",
                    f"<b>├─ 📝 Caption:</b> {caption}",
                    f"<b>├─ 📡 Channel:</b> {channel}",
                    f"<b>├─ 📦 APKs Sent:</b> {apk_count}",
                    f"<b>├─ 🔑 Keys Used:</b> {key_count}",
                    f"<b>└─ ⚙️ Method:</b> {last_method}",
                    "<b>━━━━━━━━━━━━━━━━━━━━━━━</b>"
                ])
    
        lines.append("")
        lines.append(f"<b>📊 Total Users Tracked:</b> {len(ALLOWED_USERS)}")
        lines.append(f"<b>📅 Report Generated:</b> {datetime.now().strftime('%Y-%m-%d')}")
        lines.append("<b>🧠 Powered by</b> <a href='https://t.me/Ceo_DarkFury'>@Ceo_DarkFury</a>")
    
        report_text = "\n".join(lines)
        await update.message.reply_text(report_text, parse_mode="HTML", disable_web_page_preview=True)
        return
    
    
    # STATE HANDLING
    state = USER_STATE.get(user_id)
    if not state:
        return

    # ========= Method 1 & 2 ========= #

    # Handle Channel Setting (used in Method 1 & 2)
    if state and state.get("status") == "waiting_channel":
        channel_id = message_text

        # Validate format first
        if not (channel_id.startswith("@") or channel_id.startswith("-100")):
            await update.message.reply_text(
                "❌ Invalid Channel ID.\nMust start with @username or -100..."
            )
            return

        # Now Try to Verify if Bot is Admin
        try:
            chat_info = await context.bot.get_chat(channel_id)
            member = await context.bot.get_chat_member(chat_info.id, context.bot.id)
        except Exception as e:
            await update.message.reply_text(
                "❌ Cannot find this channel!\nMake sure the bot is added into the channel as admin!"
            )
            return

        if member.status not in ["administrator", "creator"]:
            await update.message.reply_text(
                "❌ Bot is not admin in that channel!\nPlease make bot admin and try again."
            )
            return

        # All OK: Save Channel
        USER_DATA[str(user_id)] = USER_DATA.get(str(user_id), {})
        USER_DATA[str(user_id)]["channel"] = channel_id
        save_config()
        USER_STATE[user_id]["status"] = "normal"

        # After setting channel, show method selection (Method 1 / Method 2)
        keyboard = [
            [InlineKeyboardButton("⚡ Method 1", callback_data="method_1")],
            [InlineKeyboardButton("🚀 Method 2", callback_data="method_2")]
        ]
        await update.message.reply_text(
            f"✅ *Channel ID Saved Successfully!* `{channel_id}`\n\n"
            "👋 *Welcome!*\n\n"
            "Please select your working method:\n\n"
            "⚡ *Method 1*: Manual Key Capture\n"
            "🚀 *Method 2*: Upload 2-3 APKs and capture one key",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Handle Caption Setting (used in Method 1 & 2)
    if state.get("status") == "waiting_caption":
        caption = update.message.text.strip()
        if "Key -" not in caption:
            await update.message.reply_text(
                "❗ *Invalid caption!*\n\nYour caption must contain `Key -`.",
                parse_mode="Markdown"
            )
            return
    
        USER_DATA[str(user_id)] = USER_DATA.get(str(user_id), {})
        USER_DATA[str(user_id)]["caption"] = caption
        save_config()
        USER_STATE[user_id]["status"] = "normal"
    
        keyboard = [
            [InlineKeyboardButton("⚡ Method 1", callback_data="method_1")],
            [InlineKeyboardButton("🚀 Method 2", callback_data="method_2")]
        ]
        await update.message.reply_text(
            f"<blockquote><b>✅ New Caption Saved!</b>\n\n{caption}</blockquote>\n\n"
            "<b>👋 Welcome!</b>\n\n"
            "Please select your methods:\n\n"
            "<b>⚡ Method 1: Upload One apk 🥇</b>\n"
            "<b>🚀 Method 2: Upload 2-3 apks 🥈</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # ========= Method 3 (Auto 1, 2, 3) ========= #
        
    elif state.get("status", "").startswith("waiting_source"):
        setup_num = state["status"][-1]
        text = update.message.text.strip()
    
        if not (text.startswith("@") or text.startswith("-100")):
            await update.message.reply_text("❌ Invalid Source Channel ID.\nMust start with @username or -100...")
            return
    
        try:
            if text.startswith("@"):
                chat = await context.bot.get_chat(text)
                resolved_id = str(chat.id)
                AUTO_SETUP[f"setup{setup_num}"]["source_channel"] = resolved_id
            else:
                AUTO_SETUP[f"setup{setup_num}"]["source_channel"] = text
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to resolve channel: {e}")
            return
    
        USER_STATE[user_id]["status"] = "normal"
        save_config()
    
        keyboard = [
            [InlineKeyboardButton("📡 Set Source", callback_data=f"setsource{setup_num}"),
             InlineKeyboardButton("🎯 Set Destination", callback_data=f"setdest{setup_num}")],
            [InlineKeyboardButton("✍️ Set Caption", callback_data=f"setdestcaption{setup_num}")],
            [InlineKeyboardButton("🤖 Automated", callback_data=f"automated{setup_num}"),
             InlineKeyboardButton("🧠 Key Manual", callback_data=f"manual{setup_num}")],
            [InlineKeyboardButton("📌 Quote Key", callback_data=f"quote{setup_num}"),
             InlineKeyboardButton("🔤 Mono Key", callback_data=f"mono{setup_num}")],
            [InlineKeyboardButton("✅ On", callback_data=f"on{setup_num}"),
             InlineKeyboardButton("⛔ Off", callback_data=f"off{setup_num}")],
            [InlineKeyboardButton("👁️ View Setup", callback_data=f"viewsetup{setup_num}"),
             InlineKeyboardButton("🧹 Reset Setup", callback_data=f"resetsetup{setup_num}")],
            [InlineKeyboardButton("🔙 Back to Auto Menu", callback_data="method_3")]
        ]
    
        await update.message.reply_text(
            f"✅ Source Channel saved for Auto {setup_num}!\n\nChoose your next action:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return
    
    # ------------------------------
    
    elif state.get("status", "").startswith("waiting_dest"):
        setup_num = state["status"][-1]
        text = update.message.text.strip()
    
        if not (text.startswith("@") or text.startswith("-100")):
            await update.message.reply_text("❌ Invalid Destination Channel ID.\nMust start with @username or -100...")
            return
    
        try:
            if text.startswith("@"):
                chat = await context.bot.get_chat(text)
                resolved_id = str(chat.id)
                AUTO_SETUP[f"setup{setup_num}"]["dest_channel"] = resolved_id
            else:
                AUTO_SETUP[f"setup{setup_num}"]["dest_channel"] = text
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to resolve channel: {e}")
            return
    
        USER_STATE[user_id]["status"] = "normal"
        save_config()
    
        keyboard = [
            [InlineKeyboardButton("📡 Set Source", callback_data=f"setsource{setup_num}"),
             InlineKeyboardButton("🎯 Set Destination", callback_data=f"setdest{setup_num}")],
            [InlineKeyboardButton("✍️ Set Caption", callback_data=f"setdestcaption{setup_num}")],
            [InlineKeyboardButton("🤖 Automated", callback_data=f"automated{setup_num}"),
             InlineKeyboardButton("🧠 Key Manual", callback_data=f"manual{setup_num}")],
            [InlineKeyboardButton("📌 Quote Key", callback_data=f"quote{setup_num}"),
             InlineKeyboardButton("🔤 Mono Key", callback_data=f"mono{setup_num}")],
            [InlineKeyboardButton("✅ On", callback_data=f"on{setup_num}"),
             InlineKeyboardButton("⛔ Off", callback_data=f"off{setup_num}")],
            [InlineKeyboardButton("👁️ View Setup", callback_data=f"viewsetup{setup_num}"),
             InlineKeyboardButton("🧹 Reset Setup", callback_data=f"resetsetup{setup_num}")],
            [InlineKeyboardButton("🔙 Back to Auto Menu", callback_data="method_3")]
        ]
    
        await update.message.reply_text(
            f"✅ Destination Channel saved for Auto {setup_num}!\n\nChoose your next action:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return
    
    # ------------------------------
    
    elif state.get("status", "").startswith("waiting_caption"):
        setup_num = state["status"][-1]
        text = update.message.text.strip()
    
        if "Key -" not in text:
            await update.message.reply_text("❌ Destination Caption must include 'Key -' placeholder.")
            return
    
        AUTO_SETUP[f"setup{setup_num}"]["dest_caption"] = text
        USER_STATE[user_id]["status"] = "normal"
        save_config()
    
        keyboard = [
            [InlineKeyboardButton("📡 Set Source", callback_data=f"setsource{setup_num}"),
             InlineKeyboardButton("🎯 Set Destination", callback_data=f"setdest{setup_num}")],
            [InlineKeyboardButton("✍️ Set Caption", callback_data=f"setdestcaption{setup_num}")],
            [InlineKeyboardButton("🤖 Automated", callback_data=f"automated{setup_num}"),
             InlineKeyboardButton("🧠 Key Manual", callback_data=f"manual{setup_num}")],
            [InlineKeyboardButton("📌 Quote Key", callback_data=f"quote{setup_num}"),
             InlineKeyboardButton("🔤 Mono Key", callback_data=f"mono{setup_num}")],
            [InlineKeyboardButton("✅ On", callback_data=f"on{setup_num}"),
             InlineKeyboardButton("⛔ Off", callback_data=f"off{setup_num}")],
            [InlineKeyboardButton("👁️ View Setup", callback_data=f"viewsetup{setup_num}"),
             InlineKeyboardButton("🧹 Reset Setup", callback_data=f"resetsetup{setup_num}")],
            [InlineKeyboardButton("🔙 Back to Auto Menu", callback_data="method_3")]
        ]
    
        await update.message.reply_text(
            f"✅ Destination Caption saved for Auto {setup_num}!\n\nChoose your next action:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
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
    
    if USER_STATE.get(user_id, {}).get("awaiting_admin_link"):
        link = update.message.text.strip()
        if link.startswith("https://"):
            global BOT_ADMIN_LINK
            BOT_ADMIN_LINK = link
            config["bot_admin_link"] = link
            save_config()
            USER_STATE[user_id]["awaiting_admin_link"] = False
    
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 View Users", callback_data="view_users"),
                 InlineKeyboardButton("🔧 View Auto Setup", callback_data="view_autosetup")],
                [InlineKeyboardButton("🔗 Bot Admin Link", callback_data="admin_link")],
                [InlineKeyboardButton("🔄 Backup Config", callback_data="backup_config")],
                [InlineKeyboardButton("♻️ Force Reset All", callback_data="force_reset")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_methods")]
            ])
    
            await update.message.reply_text(
                "✅ Bot Admin link updated!",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text("❌ Invalid link. It must start with https://")
        return
    
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

    # Delete the old preview message
    try:
        await context.bot.delete_message(chat_id=user_id, message_id=preview_message_id)
    except Exception as e:
        print(f"Failed to delete old message: {e}")

    # Send a new message with updated caption and keyboard
    new_msg = await context.bot.send_message(
        chat_id=user_id,
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    # Update new message ID in session
    USER_STATE[user_id]["preview_message_id"] = new_msg.message_id

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

    if data == "confirm_broadcast":
        await send_broadcast(update, context)
        return

    if data == "cancel_broadcast":
        BROADCAST_SESSION.pop(user_id, None)
        await update.callback_query.edit_message_text(
            "❌ Broadcast Cancelled.",
            parse_mode="Markdown"
        )
        return

    # --- THEN handle Normal User Sessions ---
    if user_id not in USER_STATE:
        await update.callback_query.edit_message_text(
            "⏳ Session expired or invalid! ❌\nPlease restart using /start.",
            parse_mode="Markdown"
        )
        return

    # --- define auto keyboard generator here ---
    def get_auto_keyboard(setup_num):
        keyboard = [
            [InlineKeyboardButton("📡 Set Source", callback_data=f"setsource{setup_num}"),
             InlineKeyboardButton("🎯 Set Destination", callback_data=f"setdest{setup_num}")],
            [InlineKeyboardButton("✍️ Set Caption", callback_data=f"setdestcaption{setup_num}")]
        ]
    
        # Only show key mode buttons for Auto 1–3
        if setup_num in ("1", "2", "3"):
            keyboard.append([
                InlineKeyboardButton("🤖 Automated", callback_data=f"automated{setup_num}"),
                InlineKeyboardButton("🧠 Key Manual", callback_data=f"manual{setup_num}")
            ])
    
        # Key style buttons (shown for all autos)
        keyboard.append([
            InlineKeyboardButton("📌 Quote Key", callback_data=f"quote{setup_num}"),
            InlineKeyboardButton("🔤 Mono Key", callback_data=f"mono{setup_num}")
        ])
    
        # On/Off toggle
        keyboard.append([
            InlineKeyboardButton("✅ On", callback_data=f"on{setup_num}"),
            InlineKeyboardButton("⛔ Off", callback_data=f"off{setup_num}")
        ])
    
        # View/Reset + back button
        keyboard.append([
            InlineKeyboardButton("👁️ View Setup", callback_data=f"viewsetup{setup_num}"),
            InlineKeyboardButton("🧹 Reset Setup", callback_data=f"resetsetup{setup_num}")
        ])
    
        keyboard.append([
            InlineKeyboardButton("🔙 Back to Methods", callback_data="back_to_methods")
        ])
    
        return InlineKeyboardMarkup(keyboard)

    # --- Handling Auto Setup Buttons ---
    if data == "method_3":
        keyboard = [
            [InlineKeyboardButton("⚙️ Auto 1", callback_data="auto1_menu"),
             InlineKeyboardButton("⚙️ Auto 2", callback_data="auto2_menu")],
            [InlineKeyboardButton("⚙️ Auto 3", callback_data="auto3_menu"),
             InlineKeyboardButton("⚙️ Auto 4", callback_data="auto4_menu")],
            [InlineKeyboardButton("🔙 Back to Methods", callback_data="back_to_methods")]
        ]
        await query.edit_message_text(
            "🛠 <b>Method 3 Activated!</b>\nChoose a setup to configure:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "back_to_methods":
        if user_id == OWNER_ID:
            keyboard = [
                [InlineKeyboardButton("⚡ Method 1", callback_data="method_1")],
                [InlineKeyboardButton("🚀 Method 2", callback_data="method_2")],
                [InlineKeyboardButton("⚙️ Method 3", callback_data="method_3")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("⚡ Method 1", callback_data="method_1")],
                [InlineKeyboardButton("🚀 Method 2", callback_data="method_2")]
            ]
        await query.edit_message_text(
            "🔄 <b>Method Selection Reset!</b>\nPlease select again:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data.startswith("auto") and data.endswith("_menu"):
        setup_num = data[4]
        await query.edit_message_text(
            text=f"⚙️ <b>Auto {setup_num} Config</b>\nSelect an option to configure:",
            parse_mode="HTML",
            reply_markup=get_auto_keyboard(setup_num)
        )
        return

    if data.startswith("setsource"):
        setup_num = data[-1]
        USER_STATE[user_id]["status"] = f"waiting_source{setup_num}"
        await query.edit_message_text(f"📡 Send Source Channel ID for Auto {setup_num}", parse_mode="HTML")
        return

    if data.startswith("setdest") and not data.startswith("setdestcaption"):
        setup_num = data[-1]
        USER_STATE[user_id]["status"] = f"waiting_dest{setup_num}"
        await query.edit_message_text(f"🎯 Send Destination Channel ID for Auto {setup_num}", parse_mode="HTML")
        return

    if data.startswith("setdestcaption"):
        setup_num = data[-1]
        USER_STATE[user_id]["status"] = f"waiting_caption{setup_num}"
        await query.edit_message_text(f"✍️ Send Caption (must include 'Key -') for Auto {setup_num}", parse_mode="HTML")
        return

    if data.startswith("automated"):
        setup_num = data[-1]
        AUTO_SETUP[f"setup{setup_num}"]["key_mode"] = "auto"
        save_config()
        await query.edit_message_text(
            text=f"✅ Auto {setup_num} set to <b>Automated Key Mode</b>.\n\nChoose next action:",
            parse_mode="HTML",
            reply_markup=get_auto_keyboard(setup_num)
        )
        return

    if data.startswith("manual"):
        setup_num = data[-1]
        AUTO_SETUP[f"setup{setup_num}"]["key_mode"] = "manual"
        save_config()
        await query.edit_message_text(
            text=f"✅ Auto {setup_num} set to <b>Manual Key Mode</b>.\n\nChoose next action:",
            parse_mode="HTML",
            reply_markup=get_auto_keyboard(setup_num)
        )
        return

    if data.startswith("quote"):
        setup_num = data[-1]
        AUTO_SETUP[f"setup{setup_num}"]["style"] = "quote"
        save_config()
        await query.edit_message_text(
            text=f"✅ Auto {setup_num} set to <b>Quote Key Style</b>.\n\nChoose next action:",
            parse_mode="HTML",
            reply_markup=get_auto_keyboard(setup_num)
        )
        return

    if data.startswith("mono"):
        setup_num = data[-1]
        AUTO_SETUP[f"setup{setup_num}"]["style"] = "mono"
        save_config()
        await query.edit_message_text(
            text=f"✅ Auto {setup_num} set to <b>Mono Key Style</b>.\n\nChoose next action:",
            parse_mode="HTML",
            reply_markup=get_auto_keyboard(setup_num)
        )
        return

    if data.startswith("on"):
        setup_num = data[-1]
        AUTO_SETUP[f"setup{setup_num}"]["enabled"] = True
        save_config()
        await query.edit_message_text(
            text=f"✅ Auto {setup_num} has been <b>Turned ON</b>.\n\nChoose next action:",
            parse_mode="HTML",
            reply_markup=get_auto_keyboard(setup_num)
        )
        return

    if data.startswith("off"):
        setup_num = data[-1]
        AUTO_SETUP[f"setup{setup_num}"]["enabled"] = False
        save_config()
        await query.edit_message_text(
            text=f"⛔ Auto {setup_num} has been <b>Turned OFF</b>.\n\nChoose next action:",
            parse_mode="HTML",
            reply_markup=get_auto_keyboard(setup_num)
        )
        return
    
    if data == "auto4_menu":
        keyboard = [
            [InlineKeyboardButton("📡 Set Source", callback_data="setsource4"),
             InlineKeyboardButton("🎯 Set Destination", callback_data="setdest4")],
            [InlineKeyboardButton("✍️ Set Caption", callback_data="setdestcaption4")],
            [InlineKeyboardButton("🤖 Automated", callback_data="automated4"),
             InlineKeyboardButton("🧠 Key Manual", callback_data="manual4")],
            [InlineKeyboardButton("📌 Quote Key", callback_data="quote4"),
             InlineKeyboardButton("🔤 Mono Key", callback_data="mono4")],
            [InlineKeyboardButton("✅ On", callback_data="on4"),
             InlineKeyboardButton("⛔ Off", callback_data="off4")],
            [InlineKeyboardButton("👁️ View Setup", callback_data="viewsetup4"),
             InlineKeyboardButton("🧹 Reset Setup", callback_data="resetsetup4")],
            [InlineKeyboardButton("🔙 Back to Auto Menu", callback_data="method_3")]
        ]
        await query.edit_message_text(
            text="⚙️ <b>Auto 4 Config</b>\nSelect an option to configure:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if data.startswith("viewsetup"):
        setup_num = data[-1]
        s = AUTO_SETUP.get(f"setup{setup_num}", {})
    
        total_keys = s.get("completed_count", 0)
        total_apks = s.get("processed_count", total_keys)  # fallback
        source = s.get("source_channel", "Not Set")
        dest = s.get("dest_channel", "Not Set")
        caption_ok = "✅" if s.get("dest_caption") else "❌"
        key_mode = s.get("key_mode", "auto").capitalize()
        style = s.get("style", "mono").capitalize()
        status = "✅ ON" if s.get("enabled") else "⛔ OFF"
    
        msg = (
            f"<pre>"
            f"┌──── AUTO {setup_num} SYSTEM DIAG ─────┐\n"
            f"│ SOURCE        >>  {source}\n"
            f"│ DESTINATION   >>  {dest}\n"
            f"│ CAPTION       >>  {caption_ok}\n"
            f"│ KEY_MODE      >>  {key_mode}\n"
            f"│ STYLE         >>  {style}\n"
            f"│ STATUS        >>  {status}\n"
            f"│ KEYS_SENT     >>  {total_keys}\n"
            f"│ TOTAL_APKS    >>  {total_apks} APK{'s' if total_apks != 1 else ''}\n"
            f"└──────── END OF REPORT ────────┘"
            f"</pre>"
        )
    
        await query.edit_message_text(
            text=msg,
            parse_mode="HTML",
            reply_markup=get_auto_keyboard(setup_num)
        )
        return

    if data.startswith("resetsetup"):
        setup_num = data[-1]
        AUTO_SETUP[f"setup{setup_num}"] = {
            "source_channel": "",
            "dest_channel": "",
            "dest_caption": "",
            "key_mode": "auto",
            "style": "mono",
            "enabled": False,
            "completed_count": 0,
            "processed_count": 0,
            "last_key": ""
        }
        save_config()
    
        msg = (
            f"<pre>"
            f"┌──── AUTO {setup_num} SYSTEM RESET ─────┐\n"
            f"│ STATUS       >>  RESET COMPLETE        │\n"
            f"│ ALL VALUES   >>  CLEARED               │\n"
            f"│ MODE         >>  AUTO                  │\n"
            f"│ STYLE        >>  MONO                  │\n"
            f"└───────RESET DONE──────────┘"
            f"</pre>"
        )
    
        await query.edit_message_text(
            text=msg,
            parse_mode="HTML",
            reply_markup=get_auto_keyboard(setup_num)
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
    
        buttons = []
    
        if BOT_ADMIN_LINK:
            buttons.append([InlineKeyboardButton("🌟 Bot Admin", url=BOT_ADMIN_LINK)])
    
        buttons.append([InlineKeyboardButton("📡 Set Channel", callback_data="set_channel")])
        buttons.append([InlineKeyboardButton("📝 Set Caption", callback_data="set_caption")])
    
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
    
        buttons = []
    
        if BOT_ADMIN_LINK:
            buttons.append([InlineKeyboardButton("🌟 Bot Admin", url=BOT_ADMIN_LINK)])
    
        buttons.append([InlineKeyboardButton("📡 Set Channel", callback_data="set_channel")])
        buttons.append([InlineKeyboardButton("📝 Set Caption", callback_data="set_caption")])
    
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
    
    if data == "auto_last_caption":
        await auto_last_caption(user_id, context)
        return
    
    if data == "last_caption_key":
        await last_caption_key(user_id, context)
        return
    
    if data == "erase_all":
        await erase_all_session(user_id, context)
        await query.edit_message_text(
            text="🧹 <b>Session Erased!</b>\nYou can now send new APKs.",
            parse_mode="HTML"
        )
        return
    
    if data == "erase_all_session":
        user_id = update.callback_query.from_user.id
        state = USER_STATE.get(user_id, {})
        
        state["session_files"] = []
        state["session_filenames"] = []
        state["saved_key"] = None
        state["waiting_key"] = False
        state["last_apk_time"] = None
        state["key_prompt_sent"] = False
        state["progress_message_id"] = None
    
        await update.callback_query.edit_message_text(
            "🧹 <b>Your session has been erased!</b>",
            parse_mode="HTML"
        )
    
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
    
    if data.startswith("auto") and data.endswith("_menu"):
        setup_num = data[4]  # auto1 → "1", auto2 → "2", auto3 → "3"
    
        keyboard = [
            [
                InlineKeyboardButton("📡 Set Source", callback_data=f"setsource{setup_num}"),
                InlineKeyboardButton("🎯 Set Destination", callback_data=f"setdest{setup_num}")
            ],
            [
                InlineKeyboardButton("✍️ Set Caption", callback_data=f"setdestcaption{setup_num}")
            ],
            [
                InlineKeyboardButton("🤖 Automated", callback_data=f"automated{setup_num}"),
                InlineKeyboardButton("🧠 Key Manual", callback_data=f"manual{setup_num}")
            ],
            [
                InlineKeyboardButton("📌 Quote Key", callback_data=f"quote{setup_num}"),
                InlineKeyboardButton("🔤 Mono Key", callback_data=f"mono{setup_num}")
            ],
            [
                InlineKeyboardButton("✅ On", callback_data=f"on{setup_num}"),
                InlineKeyboardButton("⛔ Off", callback_data=f"off{setup_num}")
            ],
            [
                InlineKeyboardButton("👁️ View Setup", callback_data=f"viewsetup{setup_num}"),
                InlineKeyboardButton("🧹 Reset Setup", callback_data=f"resetsetup{setup_num}")
            ],
            [
                InlineKeyboardButton("🔙 Back to Auto Menu", callback_data="method_3")
            ]
        ]
    
        await query.edit_message_text(
            text=f"⚙️ <b>Auto {setup_num} Config</b>\nSelect an option to configure:",
            parse_mode="HTML",  
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = BROADCAST_SESSION.get(user_id)

    if not session or "message" not in session:
        await update.callback_query.edit_message_text(
            "⚠️ No message found to broadcast.",
            parse_mode="Markdown"
        )
        return

    msg = session["message"]
    user_ids = [int(uid) for uid in USER_DATA.keys()]
    total = len(user_ids)
    sent = 0
    failed = 0

    sent_users = []
    failed_users = []

    progress = await update.callback_query.edit_message_text(
        f"🚀 Sending Broadcast: 0/{total}", parse_mode="Markdown"
    )

    for idx, uid in enumerate(user_ids, 1):
        user_info = USER_DATA.get(str(uid), {})
        name = user_info.get("first_name", "—")
        uname = user_info.get("username", "—")

        try:
            if msg.text:
                await context.bot.send_message(chat_id=uid, text=msg.text)
            elif msg.document:
                await context.bot.send_document(chat_id=uid, document=msg.document.file_id, caption=msg.caption)
            elif msg.photo:
                await context.bot.send_photo(chat_id=uid, photo=msg.photo[-1].file_id, caption=msg.caption)
            elif msg.video:
                await context.bot.send_video(chat_id=uid, video=msg.video.file_id, caption=msg.caption)
            else:
                continue

            sent += 1
            sent_users.append(
                f"👤 <b>User:</b> <code>{uid}</code>\n"
                f"├─ 🧬 <b>Username:</b> @{uname if uname != '—' else 'N/A'}\n"
                f"└─ 🩺 <b>Status:</b> ✅ Active"
            )

        except Forbidden:
            failed += 1
            failed_users.append(
                f"👤 <b>User:</b> <code>{uid}</code>\n"
                f"├─ 🧬 <b>Username:</b> @{uname if uname != '—' else 'N/A'}\n"
                f"└─ 🩺 <b>Status:</b> ❌ Blocked"
            )
        except Exception:
            failed += 1
            failed_users.append(
                f"👤 <b>User:</b> <code>{uid}</code>\n"
                f"├─ 🧬 <b>Username:</b> @{uname if uname != '—' else 'N/A'}\n"
                f"└─ 🩺 <b>Status:</b> ⚠️ Error"
            )

        if (sent + failed) % 5 == 0 or (sent + failed) == total:
            try:
                await progress.edit_text(f"🚀 Sending Broadcast: {sent}/{total}", parse_mode="Markdown")
            except:
                pass

    # Summary output
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    date_str = now.strftime("%d-%m-%Y")
    time_str = now.strftime("%I:%M %p")

    summary = (
        "<b>🧠 BROADCAST SUMMARY REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Delivered:</b> <code>{sent}</code> users\n"
        f"❌ <b>Failed:</b> <code>{failed}</code> users\n"
        f"📅 <b>Date:</b> <code>{date_str}</code>\n"
        f"⏰ <b>Time:</b> <code>{time_str}</code>\n"
        f"📦 <b>Total:</b> <code>{sent + failed}</code> users\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    if sent_users:
        summary += "✅ <b>DELIVERED USERS</b>\n"
        summary += "\n\n".join(sent_users[:5])
        if len(sent_users) > 5:
            summary += f"\n<i>...and {len(sent_users) - 5} more.</i>"

    if failed_users:
        summary += "\n\n❌ <b>FAILED USERS</b>\n"
        summary += "\n\n".join(failed_users[:5])
        if len(failed_users) > 5:
            summary += f"\n<i>...and {len(failed_users) - 5} more.</i>"

    summary += (
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>📣 Status:</b> <i>Operation Complete</i>\n"
        "🔐 <i>Private to Admin Only</i>\n"
        "🔗 <b>Powered by</b> <a href='https://t.me/Ceo_DarkFury'>@Ceo_DarkFury</a>"
    )

    try:
        await progress.edit_text(
            text=summary,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=summary,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    BROADCAST_SESSION.pop(user_id, None)

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

    # Match Setup 1, 2, 3
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
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text="⚠️ *Alert!*\n➔ *No matching Auto Setup found for this APK!*\n⛔ *Processing Declined.*",
            parse_mode="Markdown"
        )
        print("❌ No matching setup found. Message sent to owner.")
        return

    if not matched_setup.get("enabled", False):
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"⚠️ *Alert!*\n➔ *Auto {setup_number} is currently OFF!*\n⛔ *Processing Declined.*",
            parse_mode="Markdown"
        )
        print(f"❌ Auto {setup_number} is OFF. Message sent to owner.")
        return

    print(f"✅ Matched to Setup {setup_number}")

    # Size filter
    if setup_number == 1 and not (1 <= file_size_mb <= 50):
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"⚠️ *Alert!*\n➔ *APK Size not matched for Auto {setup_number}*\n⛔ *Processing Declined.*",
            parse_mode="Markdown"
        )
        print("❌ Size not matched. Message sent to owner.")
        return

    if setup_number == 2 and not (80 <= file_size_mb <= 2048):
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"⚠️ *Alert!*\n➔ *APK Size not matched for Auto {setup_number}*\n⛔ *Processing Declined.*",
            parse_mode="Markdown"
        )
        print("❌ Size not matched. Message sent to owner.")
        return

    # Save for later deletion check
    source_chat_id = message.chat_id
    message_id = message.message_id

    # Send initial waiting message
    countdown_msg = await context.bot.send_message(
        chat_id=OWNER_ID,
        text=f"⏳ *Auto {setup_number} - Waiting 20 seconds...*",
        parse_mode="Markdown"
    )

    # Countdown loop
    for sec in range(19, 0, -1):
        await asyncio.sleep(1)
        try:
            await context.bot.edit_message_text(
                chat_id=OWNER_ID,
                message_id=countdown_msg.message_id,
                text=f"⏳ *Auto {setup_number} - {sec} seconds left...*",
                parse_mode="Markdown"
            )
        except:
            pass

    # Final 1 second sleep
    await asyncio.sleep(1)

    # Check if source message still exists
    try:
        await context.bot.forward_message(chat_id=OWNER_ID, from_chat_id=source_chat_id, message_id=message_id)
        print("✅ Message exists after 20s.")
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=OWNER_ID,
            message_id=countdown_msg.message_id,
            text=f"❌ *Auto {setup_number} Declined*\n➔ *Message Deleted during 20s wait.*",
            parse_mode="Markdown"
        )
        print("❌ Message deleted during delay. Skipped.")
        return

    # Now Extract Key
    key_mode = matched_setup.get("key_mode", "auto")
    style = matched_setup.get("style", "mono")
    dest_caption = matched_setup.get("dest_caption", "")
    dest_channel = matched_setup.get("dest_channel", "")

    key = None

    if key_mode == "auto":
        # Step 1: Try "Key -" pattern in caption text
        match = re.search(r'Key\s*-\s*(\S+)', caption)
        if match:
            key = match.group(1)
    
        # Step 2: If not found, check for 'code' style entity (One Tap Copy)
        if not key and message.caption_entities:
            for entity in message.caption_entities:
                if entity.type == "code":
                    offset = entity.offset
                    length = entity.length
                    key = caption[offset:offset + length]
                    break  # Stop after first match
    
    elif key_mode == "manual":
        match = re.search(r'Key\s*-\s*(\S+)', caption)
        if match:
            key = match.group(1)

    if not key:
        await context.bot.edit_message_text(
            chat_id=OWNER_ID,
            message_id=countdown_msg.message_id,
            text=f"❌ *Auto {setup_number} Declined*\n➔ *Key not extracted.*",
            parse_mode="Markdown"
        )
        print("❌ Key missing. Skipped.")
        return

    # Prepare Destination Caption
    if "Key -" not in dest_caption:
        dest_caption += "\nKey -"

    if style == "quote":
        final_caption = dest_caption.replace("Key -", f"<blockquote>Key - <code>{key}</code></blockquote>")
    else:  # mono
        final_caption = dest_caption.replace("Key -", f"Key - <code>{key}</code>")

    # Send document
    try:
        sent_msg = await context.bot.send_document(
            chat_id=dest_channel,
            document=doc.file_id,
            caption=final_caption,
            parse_mode="HTML",
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

        def escape(text):
            return re.sub(r'([_\*~`>\#+\-=|{}.!])', r'\\\1', str(text))

        source_name = source_username if source_username else chat_id
        source = escape(source_name)
        dest = escape(dest_channel)
        key_escape = escape(key)
        post_link_escape = escape(post_link)

        # Final success message
        await context.bot.edit_message_text(
            chat_id=OWNER_ID,
            message_id=countdown_msg.message_id,
            text=(
                f"✅ *Auto {setup_number} Completed*\n"
                f"├─ 👤 Source : {source}\n"
                f"├─ 🎯 Destination : {dest}\n"
                f"├─ 📡 Key : `{key_escape}`\n"
                f"└─ 🔗 Post Link : [Click Here]({post_link_escape})"
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

async def unified_auto_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    # AUTO 4
    setup4 = AUTO_SETUP.get("setup4", {})
    if setup4.get("enabled") and chat_id == str(setup4.get("source_channel", "")):
        await auto4_message_handler(update, context)
        return

    # AUTO 1–3
    for i in range(1, 4):
        setup = AUTO_SETUP.get(f"setup{i}", {})
        if setup.get("enabled") and chat_id == str(setup.get("source_channel", "")):
            await auto_handle_channel_post(update, context)
            return

    print(f"[AUTO] Skipped: {chat_id} not in any setup")

async def notify_owner_on_error(bot, message: str):
    global LAST_ERROR_TIME
    now = time.time()

    if now - LAST_ERROR_TIME >= ERROR_COOLDOWN:
        LAST_ERROR_TIME = now
        try:
            await bot.send_message(
                chat_id=OWNER_ID,
                text=f"⚠️ <b>Bot Error Alert</b>\n\n{message}",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"[Notify Error] Failed to notify owner: {e}")



async def on_startup(app: Application):
    app.create_task(schedule_stat_reports(app))
    app.create_task(autosave_task())

def main():
    print("[BOT] Starting application...")
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

    # Settings panel button callbacks (correct pattern matching)
    app.add_handler(CallbackQueryHandler(
        handle_settings_callback,
        pattern=r"^(view_users|view_autosetup|viewsetup[1-4]|backup_config|force_reset|confirm_reset|settings_back)$"
    ))

    # Manual document upload (PM or group)
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.Document.ALL,
        handle_document
    ))

    # Text inputs (e.g. for caption/channel setting)
    app.add_handler(MessageHandler(
        filters.TEXT & (~filters.COMMAND),
        handle_text
    ))

    # Auto-forward from channel
    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Document.ALL,
        unified_auto_handler
    ))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Run bot
    app.run_polling()

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            error_msg = f"<b>CRITICAL ERROR</b>\n<code>{str(e)}</code>"
            print(f"[CRITICAL ERROR] Restarting Bot...\nError: {e}")

            # Notify owner without spamming
            try:
                from telegram import Bot
                bot = Bot(BOT_TOKEN)
                asyncio.run(notify_owner_on_error(bot, error_msg))
            except Exception as notify_error:
                print(f"[Notify Error] Could not alert owner: {notify_error}")

            time.sleep(5)
            os.execl(sys.executable, sys.executable, *sys.argv)
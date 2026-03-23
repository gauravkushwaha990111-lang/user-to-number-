import logging  # type: ignore
import asyncio
import aiohttp  # type: ignore
import json
import os
import hashlib
import time
import random
import io
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, date
from dotenv import load_dotenv  # type: ignore
import pymongo  # type: ignore
from telegram import (  # type: ignore
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineQueryResultArticle,
    InputTextMessageContent,
    BotCommand,
    BotCommandScopeChat,
)
from telegram.ext import ( # type: ignore
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    InlineQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from telegram.constants import ParseMode, ChatMemberStatus, ChatAction  # type: ignore

load_dotenv()

BOT_TOKEN        = os.getenv("BOT_TOKEN", "")
INFO_BOT_TOKEN   = os.getenv("INFO_BOT_TOKEN", "")
ADMIN_PASS_HASH  = hashlib.sha256(os.getenv("ADMIN_PASSWORD", "admin").encode()).hexdigest()
MAINT_PASS_HASH  = hashlib.sha256(os.getenv("MAINT_PASSWORD", "maint").encode()).hexdigest()
MONGO_URI        = os.getenv("MONGO_URI", "mongodb+srv://rdp96869_db_user:3TgbDUDy9yE66fTP@usertonumber.k7gpo0m.mongodb.net/?appName=usertonumber")

# ── Your TGOSINT API ──────────────────────────────────────────────────────────
TGOSINT_URL = os.getenv("TGOSINT_URL", "https://tgosint.vercel.app/")
TGOSINT_KEY = os.getenv("TGOSINT_KEY", "YOUR_API_KEY")
# ─────────────────────────────────────────────────────────────────────────────

# ── Bot Channels For Force Sub ────────────────────────────────────────────────
_channels_env = os.getenv("CHANNELS", "@flinsbots,@devg4urav")
CHANNELS = [x.strip() for x in _channels_env.split(",") if x.strip()]

EFFECT_IDS = [
    "5046509860389126442", # 🎉 Party Popper
    "5104841245755180586", # 🔥 Fire
    "5159385139981059251", # ❤️ Heart
    "5107584321108051014", # 👍 Thumbs Up
]

# ── Permanent Admins ──────────────────────────────────────────────────────────
_admin_ids_env = os.getenv("ADMIN_IDS", "6155928882")
ADMIN_IDS = [int(x.strip()) for x in _admin_ids_env.split(",") if x.strip().isdigit()]

DB_FILE = "db.json"

COOLDOWNS = {}
COOLDOWN_TIME = 10

AWAIT_ADMIN_PW   = 2
AWAIT_MAINT_PW   = 4
AWAIT_ADD_ADMIN_PW = 5
AWAIT_DEL_ADMIN_PW = 6
AWAIT_PROMO_MSG  = 7

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ── MongoDB Setup ────────────────────────────────────────────────────────────
db_client = None
db_collection = None
if MONGO_URI:
    try:
        db_client = pymongo.MongoClient(MONGO_URI)
        mongo_db = db_client["telegram_bot"]
        db_collection = mongo_db["main_data"]
        log.info("MongoDB Connected Successfully!")
    except Exception as e:
        log.error(f"MongoDB Connection Error: {e}")
# ─────────────────────────────────────────────────────────────────────────────

def loadDb():
    data = None
    if db_collection is not None:
        try:
            data = db_collection.find_one({"_id": "bot_db"})
        except Exception as e:
            log.error(f"MongoDB Load Error: {e}")

    # Fallback / Migration from local db.json
    if data is None and os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                data = json.load(f)
            # Migrate to MongoDB immediately if connected
            if db_collection is not None and data:
                data["_id"] = "bot_db"
                db_collection.replace_one({"_id": "bot_db"}, data, upsert=True)
        except Exception:
            pass

    if not data:
        data = {"users": {}, "recentLookups": [], "globalStats": {}, "adminSessions": [], "maintenance": False, "admins": []}

    # Ensure required keys exist
    if "maintenance" not in data: data["maintenance"] = False
    if "admins" not in data: data["admins"] = []
    if "recentLookups" not in data: data["recentLookups"] = []
    if "globalStats" not in data: data["globalStats"] = {"totalLookups": 0, "successfulLookups": 0, "todayDate": date.today().isoformat(), "todayLookups": 0}
    
    return data

def saveDb(data):
    if db_collection is not None:
        try:
            data["_id"] = "bot_db"
            db_collection.replace_one({"_id": "bot_db"}, data, upsert=True)
        except Exception as e:
            log.error(f"MongoDB Save Error: {e}")
            
    # Local backup just in case
    try:
        with open(DB_FILE, "w") as f:
            d_copy = data.copy()
            if "_id" in d_copy: del d_copy["_id"]
            json.dump(d_copy, f, indent=2)
    except Exception:
        pass

def registerUser(userId, username, firstName, referrerId=None):
    db = loadDb()
    uid = str(userId)
    now = datetime.now()
    if uid not in db["users"]:
        db["users"][uid] = {
            "userId": userId,
            "username": username or "",
            "firstName": firstName or "",
            "joinedAt": now.isoformat(),
            "totalLookups": 0,
            "lastSeen": now.isoformat(),
            "balance": 2,
            "referrals": 0,
            "referredBy": referrerId,
            "lastRefill": now.isoformat()
        }
    else:
        db["users"][uid]["lastSeen"] = now.isoformat()
        db["users"][uid]["username"] = username or ""
        db["users"][uid]["firstName"] = firstName or ""
        if "balance" not in db["users"][uid]:
            db["users"][uid]["balance"] = 2
        if "referrals" not in db["users"][uid]:
            db["users"][uid]["referrals"] = 0
        if "lastRefill" not in db["users"][uid]:
            db["users"][uid]["lastRefill"] = now.isoformat()
            
        # 5 Days Refill Logic
        if db["users"][uid]["balance"] <= 0:
            try:
                last_refill = datetime.fromisoformat(db["users"][uid]["lastRefill"])
            except Exception:
                last_refill = now
            if (now - last_refill).days >= 5:
                db["users"][uid]["balance"] = 2
                db["users"][uid]["lastRefill"] = now.isoformat()
    saveDb(db)

def logLookup(userId, username, firstName, query, result, success):
    db = loadDb()
    uid = str(userId)
    todayStr = date.today().isoformat()

    # Global stats update
    gStats = db.get("globalStats", {"totalLookups": 0, "successfulLookups": 0, "todayDate": todayStr, "todayLookups": 0})
    if gStats.get("todayDate") != todayStr:
        gStats["todayDate"] = todayStr
        gStats["todayLookups"] = 0
        
    gStats["totalLookups"] = gStats.get("totalLookups", 0) + 1
    gStats["todayLookups"] = gStats.get("todayLookups", 0) + 1
    if success:
        gStats["successfulLookups"] = gStats.get("successfulLookups", 0) + 1
    db["globalStats"] = gStats

    # User stats update
    if uid in db["users"]:
        db["users"][uid]["totalLookups"] += 1
        db["users"][uid]["lastSeen"] = datetime.now().isoformat()
        if success:
            db["users"][uid]["successfulLookups"] = db["users"][uid].get("successfulLookups", 0) + 1
        if db["users"][uid].get("lastLookupDate") != todayStr:
            db["users"][uid]["lastLookupDate"] = todayStr
            db["users"][uid]["todayLookups"] = 0
        db["users"][uid]["todayLookups"] = db["users"][uid].get("todayLookups", 0) + 1

    p_info = result.get("phone_info") or result if result else {}
    db.setdefault("recentLookups", []).append({
        "ts": datetime.now().isoformat(),
        "userId": userId,
        "username": username or "",
        "firstName": firstName or "",
        "query": query,
        "success": success,
        "phone": str(p_info.get("number") or p_info.get("phone") or ""),
        "country": str(p_info.get("country") or ""),
    })
    
    # Cap recent lookups to 50 items to save space
    if len(db["recentLookups"]) > 50:
        db["recentLookups"] = db["recentLookups"][-50:]
        
    # Remove old massive lookups array to free disk space immediately
    if "lookups" in db:
        del db["lookups"]

    saveDb(db)

def getUserStats(userId):
    db = loadDb()
    uid = str(userId)
    user = db["users"].get(uid, {})
    todayStr = date.today().isoformat()
    
    todayLookups = user.get("todayLookups", 0) if user.get("lastLookupDate") == todayStr else 0
    
    return {
        "total": user.get("totalLookups", 0),
        "balance": user.get("balance", 0),
        "referrals": user.get("referrals", 0),
        "today": todayLookups,
        "successful": user.get("successfulLookups", 0),
        "joinedAt": user.get("joinedAt", "N/A"),
        "lastSeen": user.get("lastSeen", "N/A"),
    }

def getAdminStats():
    db = loadDb()
    totalUsers = len(db["users"])
    gStats = db.get("globalStats", {"totalLookups": 0, "successfulLookups": 0, "todayDate": "", "todayLookups": 0})
    todayStr = date.today().isoformat()
    totalLookups = gStats.get("totalLookups", 0)
    recentUsers = sorted(db["users"].values(), key=lambda u: u.get("lastSeen",""), reverse=True)[:5]
    return {
        "totalUsers": totalUsers,
        "totalLookups": totalLookups,
        "todayLookups": gStats.get("todayLookups", 0) if gStats.get("todayDate") == todayStr else 0,
        "successRate": round((gStats.get("successfulLookups", 0) / totalLookups) * 100, 1) if totalLookups else 0,
        "recentUsers": recentUsers,
        "allLookups": db.get("recentLookups", []),
        "allUsers": db["users"],
    }


def mainReplyKeyboard(user_id):
    db = loadDb()
    user = db["users"].get(str(user_id), {})
    is_admin = user_id in ADMIN_IDS or user_id in db.get("admins", [])
    balance = "Unlimited" if is_admin else user.get("balance", 0)
    
    return ReplyKeyboardMarkup([
        [KeyboardButton(f"💳 Lookups Left: {balance}")],
        [KeyboardButton("📊 Stats"), KeyboardButton("🎁 Refer & Earn")],
        [KeyboardButton("🤖 More Bots"), KeyboardButton("👨‍💻 Developer")]
    ], resize_keyboard=True)

def adminDashboardKb(page=0):
    db = loadDb()
    maintLabel = "Maintenance  ON" if db.get("maintenance") else "Maintenance  OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("All Users",        callback_data=f"adm_users_{page}"),
         InlineKeyboardButton("All Lookups",      callback_data=f"adm_lookups_{page}")],
        [InlineKeyboardButton("Today's Activity", callback_data="adm_today"),
         InlineKeyboardButton("Success Rate",     callback_data="adm_rate")],
        [InlineKeyboardButton("Recent Queries",   callback_data="adm_recent")],
        [InlineKeyboardButton(maintLabel,         callback_data="adm_maintenance")],
        [InlineKeyboardButton("Close",            callback_data="adm_close")],
    ])

def force_sub_keyboard():
    buttons = []
    for i, ch in enumerate(CHANNELS, 1):
        ch_name = ch.lstrip("@")
        buttons.append([InlineKeyboardButton(f"Join Channel {i}", url=f"https://t.me/{ch_name}")])
    buttons.append([InlineKeyboardButton("✅ I have joined", callback_data="check_joined")])
    return InlineKeyboardMarkup(buttons)

def result_keyboard(data):
    buttons = []
    p_info = data.get("phone_info") or data
    phone = p_info.get("number") or p_info.get("phone")
    if phone:
        buttons.append([InlineKeyboardButton("💾 Download Contact (.vcf)", callback_data="download_vcf")])
    
    if not buttons:
        return None
    return InlineKeyboardMarkup(buttons)

async def check_force_sub(user_id: int, bot) -> bool:
    db = loadDb()
    if user_id in ADMIN_IDS or user_id in db.get("admins", []):
        return True
    for ch in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
                return False
        except Exception as e:
            log.error(f"Force sub check error for {ch}: {e}")
            print(f"\n🚨 ERROR IN FORCE SUB: {e}\n👉 Make sure your Bot is an ADMIN in {ch}!\n")
            return False
    return True

def safeVal(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return "N/A"
    return str(v)

def boolEmoji(v):
    if v is None:
        return "N/A"
    return "Yes" if v else "No"

def getFlag(country_code):
    if not country_code or not isinstance(country_code, str) or len(country_code) != 2:
        return ""
    country_code = country_code.upper()
    return chr(ord(country_code[0]) + 127397) + chr(ord(country_code[1]) + 127397)

def buildResultMsg(data):
    p = data.get("phone_info") or data

    uname          = safeVal(data.get("username"))
    uid            = safeVal(data.get("user_id") or data.get("id"))
    fn             = safeVal(data.get("first_name"))
    ln             = safeVal(data.get("last_name"))
    full           = safeVal(data.get("full_name") or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip())
    bio            = safeVal(data.get("bio") or data.get("about"))
    status         = safeVal(data.get("status"))
    dc             = safeVal(data.get("dc_id"))
    wasOnline      = safeVal(data.get("was_online"))
    commonChats    = safeVal(data.get("common_chats_count"))
    restrictReason = safeVal(data.get("restriction_reason"))
    searchType     = safeVal(data.get("search_type"))
    inputType      = safeVal(data.get("input_type"))
    lang           = safeVal(data.get("language_code"))
    email          = safeVal(data.get("email") or p.get("email"))
    gender         = safeVal(data.get("gender"))

    phone   = safeVal(p.get("number") or p.get("phone"))
    country = safeVal(p.get("country"))
    cc      = safeVal(p.get("country_code"))
    flag    = getFlag(p.get("country_code") or "")
    carrier = safeVal(p.get("carrier") or p.get("network"))
    city    = safeVal(p.get("city"))
    region  = safeVal(p.get("region") or p.get("state"))
    tz      = safeVal(p.get("timezone"))
    prem    = " ⭐" if data.get("is_premium") else ""

    isBot        = "🤖 Yes" if data.get("is_bot") else "❌ No"
    isVerified   = "✅ Yes" if data.get("is_verified") else "❌ No"
    isPremium    = "⭐ Yes" if data.get("is_premium") else "❌ No"
    isScam       = "⚠️ Yes" if data.get("is_scam") else "❌ No"
    isFake       = "🎭 Yes" if data.get("is_fake") else "❌ No"
    isRestricted = "🚫 Yes" if data.get("is_restricted") else "❌ No"
    isSupport    = "👨‍💻 Yes" if data.get("is_support") else "❌ No"
    isContact    = "📞 Yes" if data.get("is_contact") else "❌ No"
    isMutual     = "🤝 Yes" if data.get("is_mutual_contact") else "❌ No"

    msg = (
        f"👤 <b>USER PROFILE</b>  <code>@{uname}</code>{prem}\n"
        f"<code>{'━'*30}</code>\n"
        f"🆔 <b>User ID</b>        <code>{uid}</code>\n"
        f"📛 <b>First Name</b>     <code>{fn}</code>\n"
        f"📛 <b>Last Name</b>      <code>{ln}</code>\n"
        f"📝 <b>Full Name</b>      <code>{full}</code>\n"
        f"🗣️ <b>Language</b>       <code>{lang}</code>\n"
        f"🚻 <b>Gender</b>         <code>{gender}</code>\n"
        f"📧 <b>Email</b>          <code>{email}</code>\n"
        f"📖 <b>Bio</b>            <code>{bio}</code>\n"
        f"🟢 <b>Status</b>         <code>{status}</code>\n"
        f"🕒 <b>Last Online</b>    <code>{wasOnline}</code>\n"
        f"🏢 <b>DC ID</b>          <code>{dc}</code>\n"
        f"💬 <b>Common Chats</b>   <code>{commonChats}</code>\n"
        f"🔍 <b>Search Type</b>    <code>{searchType}</code>\n"
        f"⌨️ <b>Input Type</b>     <code>{inputType}</code>\n"
        f"\n"
        f"📱 <b>PHONE & LOCATION</b>\n"
        f"<code>{'━'*30}</code>\n"
        f"📞 <b>Number</b>         <tg-spoiler><code>{phone}</code></tg-spoiler>\n"
        f"👤 <b>Owner Name</b>     <code>{full}</code>\n"
        f"📡 <b>Carrier</b>        <code>{carrier}</code>\n"
        f"🏙️ <b>City</b>          <code>{city}</code>\n"
        f"📍 <b>Region</b>        <code>{region}</code>\n"
        f"🕒 <b>Timezone</b>      <code>{tz}</code>\n"
        f"🗺️ <b>Country</b>        <code>{country}</code> {flag}\n"
        f"🔠 <b>Country Code</b>   <code>{cc}</code>\n"
        f"\n"
        f"🚩 <b>ACCOUNT FLAGS</b>\n"
        f"<code>{'━'*30}</code>\n"
        f"<b>Bot</b>          <code>{isBot}</code>   <b>Verified</b>   <code>{isVerified}</code>\n"
        f"<b>Premium</b>      <code>{isPremium}</code>   <b>Scam</b>       <code>{isScam}</code>\n"
        f"<b>Fake</b>         <code>{isFake}</code>   <b>Restricted</b> <code>{isRestricted}</code>\n"
        f"<b>Support</b>      <code>{isSupport}</code>   <b>Contact</b>    <code>{isContact}</code>\n"
        f"<b>Mutual</b>       <code>{isMutual}</code>\n"
        f"🚫 <b>Restriction</b>  <code>{restrictReason}</code>\n"
        f"\n"
        f"⏱️ <i>Response time: {safeVal(data.get('response_time'))}</i>"
    )
    return msg


async def fetchUserInfo(query):
    isId = str(query).lstrip("-").isdigit()
    param = query if isId else f"@{query}"
    url = f"{TGOSINT_URL}?key={TGOSINT_KEY}&q={param}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=60)) as r:
                if r.status != 200:
                    return None, f"API returned HTTP {r.status}"
                data = await r.json()
                print(f"\n[API RESPONSE for {query}] -> {data}\n")
                return data, None
    except asyncio.TimeoutError:
        return None, "timeout"
    except Exception as e:
        log.error("fetchUserInfo error: %s", e)
        return None, "unreachable"


async def cmdStart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    args = ctx.args
    referrer_id = str(args[0]) if args and args[0].isdigit() else None

    db = loadDb()
    is_new = str(u.id) not in db["users"]
    registerUser(u.id, u.username, u.first_name, referrer_id if is_new else None)

    if is_new and referrer_id and referrer_id != str(u.id) and referrer_id in db["users"]:
        db = loadDb()
        db["users"][referrer_id]["balance"] = db["users"][referrer_id].get("balance", 0) + 1
        db["users"][referrer_id]["referrals"] = db["users"][referrer_id].get("referrals", 0) + 1
        saveDb(db)
        try:
            await ctx.bot.send_message(
                chat_id=int(referrer_id),
                text=f"🎉 <b>New Referral!</b>\n\n<a href='tg://user?id={u.id}'>{u.first_name}</a> joined using your link.\nYou earned +1 free lookup! 🎁",
                parse_mode=ParseMode.HTML,
                message_effect_id=random.choice(EFFECT_IDS)
            )
        except:
            pass

    db = loadDb()
    if db.get("maintenance"):
        await update.message.reply_text(
            "<b>Bot Under Maintenance</b>\n\n"
            "We are currently performing maintenance.\n"
            "<i>Please check back shortly.</i>",
            parse_mode=ParseMode.HTML,
            message_effect_id=random.choice(EFFECT_IDS)
        )
        return

    if not await check_force_sub(u.id, ctx.bot):
        await update.message.reply_text(
            "🚨 <b>Mandatory Action Required</b>\n\nTo use this bot, you must join our channels first!",
            parse_mode=ParseMode.HTML,
            reply_markup=force_sub_keyboard(),
            message_effect_id=random.choice(EFFECT_IDS)
        )
        return

    if db["users"].get(str(u.id), {}).get("banned"):
        await update.message.reply_text("❌ <b>Access Denied</b>\nYou have been banned from using this bot.", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
        return

    user_data = db["users"].get(str(u.id), {})
    is_admin = u.id in ADMIN_IDS or u.id in db.get("admins", [])
    
    # Set bot menu commands dynamically based on user role
    try:
        if is_admin:
            await ctx.bot.set_my_commands([
                BotCommand("start", "Restart the bot"),
                BotCommand("admin", "Open Admin Dashboard"),
                BotCommand("stats", "Check your account statistics"),
                BotCommand("apistatus", "Check OSINT API status"),
                BotCommand("addbalance", "/addbalance <id> <amount>"),
                BotCommand("setbalance", "/setbalance <id> <amount>"),
                BotCommand("ban", "/ban <user_id>"),
                BotCommand("unban", "/unban <user_id>"),
                BotCommand("addadmin", "/addadmin <user_id>"),
                BotCommand("deladmin", "/deladmin <user_id>"),
                BotCommand("promotion", "Broadcast message to all users"),
            ], scope=BotCommandScopeChat(u.id))
        else:
            await ctx.bot.set_my_commands([
                BotCommand("start", "Restart the bot"),
                BotCommand("stats", "Check your account statistics"),
            ], scope=BotCommandScopeChat(u.id))
    except Exception as e:
        log.warning(f"Could not set commands for {u.id}: {e}")

    bal_text = "Unlimited" if is_admin else user_data.get("balance", 0)
    name = u.first_name or "there"
    msg = (
        f"👋 <b>Welcome, {name}!</b>\n\n"
        f"🎁 <b>Free Lookups Remaining:</b> <code>{bal_text}</code>\n\n"
        f"🔍 <code>Telegram OSINT & Phone Lookup</code>\n\n"
        f"Find detailed profile information and phone numbers\n"
        f"linked to any Telegram username.\n\n"
        f"🎯 <b>Just send me a username directly to look them up!</b>\n"
        f"💡 <i>Example: @username</i>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=mainReplyKeyboard(u.id), message_effect_id=random.choice(EFFECT_IDS))


async def cmdStats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    registerUser(u.id, u.username, u.first_name)
    s = getUserStats(u.id)
    joined   = s["joinedAt"][:10] if s["joinedAt"] != "N/A" else "N/A"
    lastSeen = s["lastSeen"][:10] if s["lastSeen"] != "N/A" else "N/A"
    msg = (
        f"📊 <b>YOUR STATS</b>\n"
        f"<code>{'━'*26}</code>\n"
        f"💳 <b>Available Lookups</b>   <code>{s.get('balance', 0)}</code>\n"
        f"👥 <b>Total Referrals</b>     <code>{s.get('referrals', 0)}</code>\n"
        f"🔍 <b>Total Lookups</b>       <code>{s['total']}</code>\n"
        f"📅 <b>Lookups Today</b>       <code>{s['today']}</code>\n"
        f"✅ <b>Successful</b>          <code>{s['successful']}</code>\n"
        f"⏱️ <b>Member Since</b>        <code>{joined}</code>\n"
        f"👀 <b>Last Active</b>         <code>{lastSeen}</code>\n"
        f"<code>{'━'*26}</code>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=mainReplyKeyboard(u.id), message_effect_id=random.choice(EFFECT_IDS))


async def cmdApiStatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db = loadDb()
    is_admin = u.id in ADMIN_IDS or u.id in db.get("admins", [])
    
    if not is_admin:
        await update.message.reply_text("❌ <b>Admin only command.</b>", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
        return
        
    loading = await update.message.reply_text("🔄 <b>Checking API Status...</b>", parse_mode=ParseMode.HTML)
    
    start_time = time.time()
    # Checking with a known Telegram account (@durov) to see if API responds properly
    url = f"{TGOSINT_URL}?key={TGOSINT_KEY}&q=@durov"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                elapsed = round((time.time() - start_time) * 1000)
                if r.status == 200:
                    status_text = f"✅ <b>ONLINE</b>\n⏱️ Response Time: <code>{elapsed}ms</code>"
                else:
                    status_text = f"⚠️ <b>DEGRADED</b> (HTTP {r.status})\n⏱️ Response Time: <code>{elapsed}ms</code>"
    except asyncio.TimeoutError:
        status_text = "❌ <b>OFFLINE</b> (Timeout)\n<i>The API took too long to respond.</i>"
    except Exception as e:
        status_text = f"❌ <b>ERROR</b>\n<code>{str(e)}</code>"
        
    msg = (
        f"📡 <b>API STATUS REPORT</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"🔗 <b>Endpoint:</b> <code>{TGOSINT_URL}</code>\n"
        f"📊 <b>Status:</b> {status_text}\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━</code>"
    )
    await loading.edit_text(msg, parse_mode=ParseMode.HTML)


async def cmdAdmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>ADMIN ACCESS</b>\n\nEnter the admin password to continue.",
        parse_mode=ParseMode.HTML,
        message_effect_id=random.choice(EFFECT_IDS)
    )
    return AWAIT_ADMIN_PW


async def receiveAdminPw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    entered = update.message.text.strip()
    enteredHash = hashlib.sha256(entered.encode()).hexdigest()
    u = update.effective_user

    try:
        await update.message.delete()
    except:
        pass

    if enteredHash != ADMIN_PASS_HASH:
        await update.message.reply_text(
            "<b>Incorrect password.</b>\n<i>Access denied.</i>",
            parse_mode=ParseMode.HTML,
            message_effect_id=random.choice(EFFECT_IDS)
        )
        return ConversationHandler.END

    db = loadDb()
    if "admins" not in db: db["admins"] = []
    if u.id not in db["admins"]:
        db["admins"].append(u.id)
    db["adminSessions"].append({"userId": update.effective_user.id, "ts": datetime.now().isoformat()})
    saveDb(db)

    stats = getAdminStats()
    msg = (
        f"<b>ADMIN DASHBOARD</b>\n"
        f"<code>{'─'*28}</code>\n\n"
        f"<b>Total Users</b>      <code>{stats['totalUsers']}</code>\n"
        f"<b>Total Lookups</b>    <code>{stats['totalLookups']}</code>\n"
        f"<b>Today's Lookups</b>  <code>{stats['todayLookups']}</code>\n"
        f"<b>Success Rate</b>     <code>{stats['successRate']}%</code>\n\n"
        f"<code>{'─'*28}</code>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=adminDashboardKb(), message_effect_id=random.choice(EFFECT_IDS))
    return ConversationHandler.END


async def cmdAddAdmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = loadDb()
    if update.effective_user.id not in ADMIN_IDS and update.effective_user.id not in db.get("admins", []):
        return ConversationHandler.END
    if not ctx.args:
        await update.message.reply_text("Usage: /addadmin <user_id>", message_effect_id=random.choice(EFFECT_IDS))
        return ConversationHandler.END
    try:
        new_admin = int(ctx.args[0])
    except ValueError:
        return ConversationHandler.END
        
    ctx.user_data["target_add_admin"] = new_admin
    await update.message.reply_text(
        f"<b>Security Check</b>\n\nEnter the admin password to confirm adding <code>{new_admin}</code> as Admin.",
        parse_mode=ParseMode.HTML,
        message_effect_id=random.choice(EFFECT_IDS)
    )
    return AWAIT_ADD_ADMIN_PW

async def receiveAddAdminPw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    entered = update.message.text.strip()
    enteredHash = hashlib.sha256(entered.encode()).hexdigest()
    
    try:
        await update.message.delete()
    except:
        pass

    if enteredHash != ADMIN_PASS_HASH:
        await update.message.reply_text("❌ <b>Incorrect password.</b> Action cancelled.", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
        return ConversationHandler.END

    new_admin = ctx.user_data.get("target_add_admin")
    db = loadDb()
    if new_admin not in db["admins"]:
        db["admins"].append(new_admin)
        saveDb(db)
        await update.message.reply_text(f"✅ User <code>{new_admin}</code> added as admin.", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
    else:
        await update.message.reply_text("User is already an admin.", message_effect_id=random.choice(EFFECT_IDS))
    return ConversationHandler.END

async def cmdDelAdmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = loadDb()
    if update.effective_user.id not in ADMIN_IDS and update.effective_user.id not in db.get("admins", []):
        return ConversationHandler.END
    if not ctx.args:
        await update.message.reply_text("Usage: /deladmin <user_id>", message_effect_id=random.choice(EFFECT_IDS))
        return ConversationHandler.END
    try:
        target = int(ctx.args[0])
    except ValueError:
        return ConversationHandler.END
        
    ctx.user_data["target_del_admin"] = target
    await update.message.reply_text(
        f"<b>Security Check</b>\n\nEnter the admin password to confirm removing <code>{target}</code> from Admins.",
        parse_mode=ParseMode.HTML,
        message_effect_id=random.choice(EFFECT_IDS)
    )
    return AWAIT_DEL_ADMIN_PW

async def receiveDelAdminPw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    entered = update.message.text.strip()
    enteredHash = hashlib.sha256(entered.encode()).hexdigest()
    
    try:
        await update.message.delete()
    except:
        pass

    if enteredHash != ADMIN_PASS_HASH:
        await update.message.reply_text("❌ <b>Incorrect password.</b> Action cancelled.", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
        return ConversationHandler.END

    target = ctx.user_data.get("target_del_admin")
    db = loadDb()
    if target in db["admins"]:
        db["admins"].remove(target)
        saveDb(db)
        await update.message.reply_text(f"✅ User <code>{target}</code> removed from admins.", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
    else:
        await update.message.reply_text("User is not an admin.", message_effect_id=random.choice(EFFECT_IDS))
    return ConversationHandler.END

async def cmdBan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = loadDb()
    if update.effective_user.id not in ADMIN_IDS and update.effective_user.id not in db.get("admins", []):
        return
    if not ctx.args:
        await update.message.reply_text("Usage: /ban <user_id>", message_effect_id=random.choice(EFFECT_IDS))
        return
    target = ctx.args[0]
    if target in db["users"]:
        db["users"][target]["banned"] = True
        saveDb(db)
        await update.message.reply_text(f"✅ User <code>{target}</code> has been banned.", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
    else:
        await update.message.reply_text("User not found in Database.", message_effect_id=random.choice(EFFECT_IDS))

async def cmdUnban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = loadDb()
    if update.effective_user.id not in ADMIN_IDS and update.effective_user.id not in db.get("admins", []):
        return
    if not ctx.args:
        await update.message.reply_text("Usage: /unban <user_id>", message_effect_id=random.choice(EFFECT_IDS))
        return
    target = ctx.args[0]
    if target in db["users"]:
        db["users"][target]["banned"] = False
        saveDb(db)
        await update.message.reply_text(f"✅ User <code>{target}</code> unbanned successfully.", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
    else:
        await update.message.reply_text("User not found in Database.", message_effect_id=random.choice(EFFECT_IDS))

async def cmdSetBalance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = loadDb()
    if update.effective_user.id not in ADMIN_IDS and update.effective_user.id not in db.get("admins", []):
        return
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage: /setbalance <user_id> <amount>", message_effect_id=random.choice(EFFECT_IDS))
        return
    target = ctx.args[0]
    try:
        amount = int(ctx.args[1])
    except ValueError:
        await update.message.reply_text("Amount must be a valid number.", message_effect_id=random.choice(EFFECT_IDS))
        return
        
    if target in db["users"]:
        db["users"][target]["balance"] = amount
        saveDb(db)
        await update.message.reply_text(f"✅ User <code>{target}</code> balance successfully set to <b>{amount}</b> lookups.", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
    else:
        await update.message.reply_text("User not found in Database.", message_effect_id=random.choice(EFFECT_IDS))

async def cmdAddBalance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = loadDb()
    if update.effective_user.id not in ADMIN_IDS and update.effective_user.id not in db.get("admins", []):
        return
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage: /addbalance <user_id> <amount>", message_effect_id=random.choice(EFFECT_IDS))
        return
    target = ctx.args[0]
    try:
        amount = int(ctx.args[1])
    except ValueError:
        await update.message.reply_text("Amount must be a valid number.", message_effect_id=random.choice(EFFECT_IDS))
        return
        
    if target in db["users"]:
        db["users"][target]["balance"] = db["users"][target].get("balance", 0) + amount
        saveDb(db)
        await update.message.reply_text(f"✅ Added <b>{amount}</b> lookups to user <code>{target}</code>.\nNew Balance: <b>{db['users'][target]['balance']}</b>", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
    else:
        await update.message.reply_text("User not found in Database.", message_effect_id=random.choice(EFFECT_IDS))

async def cbAdminUsers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    page = int(data.split("_")[-1]) if data.split("_")[-1].isdigit() else 0

    db = loadDb()
    users = list(db["users"].values())
    perPage = 5
    total = len(users)
    start = page * perPage
    end = start + perPage
    chunk = users[start:end]

    lines = [f"<b>ALL USERS</b>  <i>(page {page+1})</i>\n<code>{'─'*28}</code>\n"]
    for u in chunk:
        joined = u.get("joinedAt","")[:10]
        lines.append(
            f"\n<b>{u.get('firstName','?')}</b>  <code>@{u.get('username','?')}</code>\n"
            f"ID: <code>{u.get('userId','?')}</code>\n"
            f"Lookups: <code>{u.get('totalLookups',0)}</code>   Joined: <code>{joined}</code>"
        )

    navBtns = []
    if page > 0:
        navBtns.append(InlineKeyboardButton("Prev", callback_data=f"adm_users_{page-1}"))
    if end < total:
        navBtns.append(InlineKeyboardButton("Next", callback_data=f"adm_users_{page+1}"))

    kb = []
    if navBtns:
        kb.append(navBtns)
    kb.append([InlineKeyboardButton("Back to Dashboard", callback_data="adm_dashboard")])

    await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))


async def cbAdminLookups(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    page = int(data.split("_")[-1]) if data.split("_")[-1].isdigit() else 0

    db = loadDb()
    lookups = list(reversed(db.get("recentLookups", [])))
    perPage = 5
    total = len(lookups)
    start = page * perPage
    end = start + perPage
    chunk = lookups[start:end]

    lines = [f"<b>RECENT LOOKUPS</b>  <i>(page {page+1})</i>\n<code>{'─'*28}</code>\n"]
    for l in chunk:
        ts = l.get("ts","")[:16].replace("T"," ")
        lines.append(
            f"\n<b>@{l.get('query','?')}</b>\n"
            f"By: <code>{l.get('firstName','?')}</code> (<code>@{l.get('username','?')}</code>)\n"
            f"Phone: <tg-spoiler><code>{l.get('phone','N/A') or 'N/A'}</code></tg-spoiler>   "
            f"Country: <code>{l.get('country','N/A') or 'N/A'}</code>\n"
            f"Status: <code>{'Success' if l.get('success') else 'Failed'}</code>   Time: <code>{ts}</code>"
        )

    navBtns = []
    if page > 0:
        navBtns.append(InlineKeyboardButton("Prev", callback_data=f"adm_lookups_{page-1}"))
    if end < total:
        navBtns.append(InlineKeyboardButton("Next", callback_data=f"adm_lookups_{page+1}"))

    kb = []
    if navBtns:
        kb.append(navBtns)
    kb.append([InlineKeyboardButton("Back to Dashboard", callback_data="adm_dashboard")])

    await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))


async def cbAdminToday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db = loadDb()
    todayStr = date.today().isoformat()
    gStats = db.get("globalStats", {})
    todayTotal = gStats.get("todayLookups", 0) if gStats.get("todayDate") == todayStr else 0
    
    todayLookups = [l for l in db.get("recentLookups", []) if l.get("ts", "").startswith(todayStr)]

    lines = [f"<b>TODAY'S ACTIVITY</b>\n<code>{'─'*28}</code>\n"]
    lines.append(f"\n<b>Total Lookups Today</b>   <code>{todayTotal}</code>")
    lines.append(f"<i>(Recent lookups details shown below)</i>\n")
    lines.append(f"<code>{'─'*28}</code>")

    for l in reversed(todayLookups[-10:]):
        ts = l.get("ts","")[11:16]
        lines.append(
            f"\n<code>{ts}</code>  <b>@{l.get('query','?')}</b>\n"
            f"<code>{'Success' if l.get('success') else 'Failed'}</code>  by {l.get('firstName','?')}"
        )

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="adm_dashboard")]])
    )


async def cbAdminRate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db = loadDb()
    gStats = db.get("globalStats", {})
    total = gStats.get("totalLookups", 0)
    successful = gStats.get("successfulLookups", 0)
    failed = total - successful
    rate = round(successful / total * 100, 1) if total else 0

    users = list(db["users"].values())
    topSorted = sorted(users, key=lambda x: x.get("totalLookups", 0), reverse=True)[:5]

    lines = [f"<b>SUCCESS RATE</b>\n<code>{'─'*28}</code>\n"]
    lines.append(f"\n<b>Total Lookups</b>   <code>{total}</code>")
    lines.append(f"<b>Successful</b>      <code>{successful}</code>")
    lines.append(f"<b>Failed</b>          <code>{failed}</code>")
    lines.append(f"<b>Success Rate</b>    <code>{rate}%</code>\n")
    lines.append(f"<code>{'─'*28}</code>")
    lines.append(f"\n<b>TOP USERS BY LOOKUPS</b>")
    for u in topSorted:
        name = u.get("firstName", "?")
        count = u.get("totalLookups", 0)
        if count > 0:
            lines.append(f"<code>{name}</code>  <code>{count} lookups</code>")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="adm_dashboard")]])
    )


async def cbAdminRecent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db = loadDb()
    recent = list(reversed(db.get("recentLookups", [])[-20:]))

    lines = [f"<b>RECENT QUERIES</b>\n<code>{'─'*28}</code>\n"]
    for l in recent:
        ts = l.get("ts","")[:16].replace("T"," ")
        lines.append(
            f"\n<code>{ts}</code>\n"
            f"Query: <b>@{l.get('query','?')}</b>\n"
            f"By: <code>{l.get('firstName','?')}</code>  |  "
            f"<code>{'Success' if l.get('success') else 'Failed'}</code>"
        )

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="adm_dashboard")]])
    )


async def cbAdminDashboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stats = getAdminStats()
    msg = (
        f"<b>ADMIN DASHBOARD</b>\n"
        f"<code>{'─'*28}</code>\n\n"
        f"<b>Total Users</b>      <code>{stats['totalUsers']}</code>\n"
        f"<b>Total Lookups</b>    <code>{stats['totalLookups']}</code>\n"
        f"<b>Today's Lookups</b>  <code>{stats['todayLookups']}</code>\n"
        f"<b>Success Rate</b>     <code>{stats['successRate']}%</code>\n\n"
        f"<code>{'─'*28}</code>"
    )
    await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=adminDashboardKb())


async def cbAdminClose(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.delete_message()


async def cbMaintenanceToggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db = loadDb()
    currentState = db.get("maintenance", False)
    action = "disable" if currentState else "enable"
    ctx.user_data["pendingMaintenance"] = not currentState
    await query.edit_message_text(
        f"<b>Maintenance Mode</b>\n\n"
        f"You are about to <b>{action}</b> maintenance mode.\n\n"
        f"Enter the maintenance password to confirm.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="adm_dashboard")]])
    )
    return AWAIT_MAINT_PW


async def receiveMaintPw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    entered = update.message.text.strip()
    enteredHash = hashlib.sha256(entered.encode()).hexdigest()

    try:
        await update.message.delete()
    except:
        pass

    if enteredHash != MAINT_PASS_HASH:
        await update.message.reply_text(
            "<b>Incorrect password.</b>\n<i>Maintenance state unchanged.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=adminDashboardKb(),
            message_effect_id=random.choice(EFFECT_IDS)
        )
        return ConversationHandler.END

    newState = ctx.user_data.pop("pendingMaintenance", False)
    db = loadDb()
    db["maintenance"] = newState
    saveDb(db)

    label = "ENABLED" if newState else "DISABLED"
    await update.message.reply_text(
        f"<b>Maintenance Mode {label}</b>\n\n"
        f"<i>{'Users will now see a maintenance message.' if newState else 'Bot is back online for all users.'}</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=adminDashboardKb(),
        message_effect_id=random.choice(EFFECT_IDS)
    )
    return ConversationHandler.END


async def cbBackMain(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    u = update.effective_user

    if not await check_force_sub(u.id, ctx.bot):
        await query.edit_message_text(
            "🚨 <b>Mandatory Action Required</b>\n\nTo use this bot, you must join our channels first!",
            parse_mode=ParseMode.HTML,
            reply_markup=force_sub_keyboard()
        )
        return

    try:
        await query.message.delete()
    except:
        pass

    db = loadDb()
    if db["users"].get(str(u.id), {}).get("banned"):
        await ctx.bot.send_message(chat_id=u.id, text="❌ <b>Access Denied</b>\nYou have been banned from using this bot.", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
        return ConversationHandler.END

    user_data = db["users"].get(str(u.id), {})
    is_admin = u.id in ADMIN_IDS or u.id in db.get("admins", [])
    bal_text = "Unlimited" if is_admin else user_data.get("balance", 0)
    name = u.first_name or "there"
    msg = (
        f"👋 <b>Welcome, {name}!</b>\n\n"
        f"🎁 <b>Free Lookups Remaining:</b> <code>{bal_text}</code>\n\n"
        f"🔍 <code>Telegram OSINT & Phone Lookup</code>\n\n"
        f"Find detailed profile information and phone numbers\n"
        f"linked to any Telegram username.\n\n"
        f"🎯 <b>Just send me a username directly to look them up!</b>\n"
        f"💡 <i>Example: @username</i>"
    )
    await ctx.bot.send_message(chat_id=u.id, text=msg, parse_mode=ParseMode.HTML, reply_markup=mainReplyKeyboard(u.id), message_effect_id=random.choice(EFFECT_IDS))
    return ConversationHandler.END


async def cbMyStats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    u = update.effective_user
    try:
        await query.message.delete()
    except:
        pass
    s = getUserStats(u.id)
    joined   = s["joinedAt"][:10] if s["joinedAt"] != "N/A" else "N/A"
    lastSeen = s["lastSeen"][:10] if s["lastSeen"] != "N/A" else "N/A"
    msg = (
        f"📊 <b>YOUR STATS</b>\n"
        f"<code>{'━'*26}</code>\n"
        f"💳 <b>Available Lookups</b>   <code>{s.get('balance', 0)}</code>\n"
        f"👥 <b>Total Referrals</b>     <code>{s.get('referrals', 0)}</code>\n"
        f"🔍 <b>Total Lookups</b>       <code>{s['total']}</code>\n"
        f"📅 <b>Lookups Today</b>       <code>{s['today']}</code>\n"
        f"✅ <b>Successful</b>          <code>{s['successful']}</code>\n"
        f"⏱️ <b>Member Since</b>        <code>{joined}</code>\n"
        f"👀 <b>Last Active</b>         <code>{lastSeen}</code>\n"
        f"<code>{'━'*26}</code>"
    )
    await ctx.bot.send_message(
        chat_id=u.id, 
        text=msg, 
        parse_mode=ParseMode.HTML, 
        reply_markup=mainReplyKeyboard(u.id),
        message_effect_id=random.choice(EFFECT_IDS)
    )


async def cbMyReferral(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    u = update.effective_user
    try:
        await query.message.delete()
    except:
        pass
    bot_username = (await ctx.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={u.id}"
    db = loadDb()
    user_data = db["users"].get(str(u.id), {})
    balance = user_data.get("balance", 0)
    referrals = user_data.get("referrals", 0)
    
    msg = (
        f"🎁 <b>REFER & EARN</b>\n\n"
        f"Share your link and earn <b>1 Free Lookup</b> for every new user!\n\n"
        f"🔗 <b>Your Link:</b>\n<code>{ref_link}</code>\n\n"
        f"👥 <b>Total Referrals:</b> <code>{referrals}</code>\n"
        f"💳 <b>Current Balance:</b> <code>{balance} lookups</code>"
    )
    await ctx.bot.send_message(chat_id=u.id, text=msg, parse_mode=ParseMode.HTML, reply_markup=mainReplyKeyboard(u.id), message_effect_id=random.choice(EFFECT_IDS))

async def cbCheckJoined(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    u = update.effective_user
    if await check_force_sub(u.id, ctx.bot):
        await query.answer("✅ Verified! Welcome.", show_alert=True)
        try:
            await query.message.delete()
        except:
            pass
        db = loadDb()
        user_data = db["users"].get(str(u.id), {})
        is_admin = u.id in ADMIN_IDS or u.id in db.get("admins", [])
        bal_text = "Unlimited" if is_admin else user_data.get("balance", 0)
        name = u.first_name or "there"
        msg = (
            f"👋 <b>Welcome, {name}!</b>\n\n"
            f"🎁 <b>Free Lookups Remaining:</b> <code>{bal_text}</code>\n\n"
            f"🔍 <code>Telegram OSINT & Phone Lookup</code>\n\n"
            f"Find detailed profile information and phone numbers\n"
            f"linked to any Telegram username.\n\n"
            f"🎯 <b>Just send me a username directly to look them up!</b>\n"
            f"💡 <i>Example: @username</i>"
        )
        await ctx.bot.send_message(chat_id=u.id, text=msg, parse_mode=ParseMode.HTML, reply_markup=mainReplyKeyboard(u.id), message_effect_id=random.choice(EFFECT_IDS))
    else:
        await query.answer("❌ You haven't joined both channels yet!", show_alert=True)

async def cb_download_vcf(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    u = update.effective_user
    
    last_result = ctx.user_data.get('last_result')
    
    if not last_result:
        await query.answer("This is an old result. Please perform a new lookup.", show_alert=True)
        return

    p_info = last_result.get("phone_info") or last_result
    phone = p_info.get("number") or p_info.get("phone")
    full_name = last_result.get("full_name") or f"{last_result.get('first_name', '')} {last_result.get('last_name', '')}".strip()
    
    if not phone:
        await query.answer("No phone number found in this result to save.", show_alert=True)
        return

    await query.answer("Generating contact file...")

    vcf_content = (
        f"BEGIN:VCARD\n"
        f"VERSION:3.0\n"
        f"FN:{full_name or phone}\n"
        f"TEL;TYPE=CELL:{phone}\n"
        f"END:VCARD"
    )
    
    vcf_bytes = io.BytesIO(vcf_content.encode('utf-8'))
    filename = f"{(full_name or phone).replace(' ', '_')}.vcf"
    
    await ctx.bot.send_document(
        chat_id=u.id,
        document=vcf_bytes,
        filename=filename,
        caption=f"Here is the contact file for <b>{full_name or phone}</b>.",
        parse_mode=ParseMode.HTML,
        message_effect_id=random.choice(EFFECT_IDS)
    )

async def notify_admins_via_infobot(user_id, username, first_name, query, data, success):
    db = loadDb()
    all_admins = set(ADMIN_IDS + db.get("admins", []))
    if not all_admins:
        return
        
    user_info = db.get("users", {}).get(str(user_id), {})
    balance = user_info.get("balance", 0)
    tot_lookups = user_info.get("totalLookups", 0)
    joined_at = user_info.get("joinedAt", "N/A")[:10]

    status = "✅ Success" if success else "❌ Failed"
    p_info = data.get("phone_info") or data if data else {}
    phone = p_info.get("number") or p_info.get("phone") or "N/A"
    country = p_info.get("country") or "N/A"
    uname_text = f"@{username}" if username else "N/A"
    
    target_id = data.get("user_id") or data.get("id") or "N/A" if data else "N/A"
    target_uname = f"@{data.get('username')}" if data and data.get("username") else "N/A"
    target_name = data.get("first_name") or "N/A" if data else "N/A"

    msg = (
        f"🚨 <b>NEW LOOKUP ALERT</b>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"🕵️‍♂️ <b>SEARCHER DETAILS:</b>\n"
        f"<b>• Name:</b> <a href='tg://user?id={user_id}'>{first_name}</a>\n"
        f"<b>• Username:</b> {uname_text}\n"
        f"<b>• User ID:</b> <code>{user_id}</code>\n"
        f"<b>• Balance:</b> <code>{balance} lookups</code>\n"
        f"<b>• Total Lookups:</b> <code>{tot_lookups}</code>\n"
        f"<b>• Joined:</b> <code>{joined_at}</code>\n"
        f"<code>━━━━━━━━━━━━━━━━━━━━</code>\n"
        f"<b>🔍 Query:</b> <code>{query}</code>\n"
        f"<b>📊 Status:</b> {status}\n"
    )
    if data and (target_id != "N/A" or success):
        msg += (
            f"<code>━━━━━━━━━━━━━━━━━━━━</code>\n"
            f"🎯 <b>TARGET DETAILS:</b>\n"
            f"<b>• ID:</b> <code>{target_id}</code>\n"
            f"<b>• Name:</b> <code>{target_name}</code>\n"
            f"<b>• User:</b> {target_uname}\n"
        )
    if success:
        msg += (
            f"<b>• Phone:</b> <code>{phone}</code>\n"
            f"<b>• Country:</b> <code>{country}</code>\n"
        )

    url = f"https://api.telegram.org/bot{INFO_BOT_TOKEN}/sendMessage"
    
    async with aiohttp.ClientSession() as session:
        for admin_id in all_admins:
            try:
                await session.post(url, json={"chat_id": admin_id, "text": msg, "parse_mode": "HTML", "message_effect_id": random.choice(EFFECT_IDS)})
            except Exception as e:
                log.error(f"Infobot notify error for {admin_id}: {e}")

async def receiveInput(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    msg = update.message
    
    # Puraane users ka balance 2 set karne ke liye unhe update karna zaroori hai
    registerUser(u.id, u.username, u.first_name)
    query = None

    db = loadDb()

    if db["users"].get(str(u.id), {}).get("banned"):
        await msg.reply_text("❌ <b>Access Denied</b>\nYou have been banned from using this bot.", parse_mode=ParseMode.HTML, message_effect_id=random.choice(EFFECT_IDS))
        return

    if db.get("maintenance"):
        await msg.reply_text(
            "🛠️ <b>Bot Under Maintenance</b>\n\n<i>Please check back shortly.</i>",
            parse_mode=ParseMode.HTML,
            message_effect_id=random.choice(EFFECT_IDS)
        )
        return

    if not await check_force_sub(u.id, ctx.bot):
        await msg.reply_text(
            "🚨 <b>Mandatory Action Required</b>\n\nTo use this bot, you must join our channels first!",
            parse_mode=ParseMode.HTML,
            reply_markup=force_sub_keyboard()
        )
        return

    text_val = msg.text.strip() if msg.text else ""
    if text_val.startswith("💳 Lookups Left") or text_val == "📊 Stats":
        await cmdStats(update, ctx)
        return
    elif text_val == "🎁 Refer & Earn":
        bot_username = (await ctx.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={u.id}"
        user_data = db["users"].get(str(u.id), {})
        balance = user_data.get("balance", 0)
        referrals = user_data.get("referrals", 0)
        
        reply_msg = (
            f"🎁 <b>REFER & EARN</b>\n\n"
            f"Share your link and earn <b>1 Free Lookup</b> for every new user!\n\n"
            f"🔗 <b>Your Link:</b>\n<code>{ref_link}</code>\n\n"
            f"👥 <b>Total Referrals:</b> <code>{referrals}</code>\n"
            f"💳 <b>Current Balance:</b> <code>{balance} lookups</code>"
        )
        await msg.reply_text(reply_msg, parse_mode=ParseMode.HTML, reply_markup=mainReplyKeyboard(u.id), message_effect_id=random.choice(EFFECT_IDS))
        return
    elif text_val == "🤖 More Bots":
        await msg.reply_text(
            "🤖 <b>More Bots:</b>\nJoin our channel <a href='https://t.me/flinsbots'>@flinsbots</a> for more amazing bots!",
            parse_mode=ParseMode.HTML,
            reply_markup=mainReplyKeyboard(u.id),
            message_effect_id=random.choice(EFFECT_IDS)
        )
        return
    elif text_val == "👨‍💻 Developer":
        await msg.reply_text(
            "👨‍💻 <b>Developer:</b>\nCheck out the developer <a href='https://t.me/devg4urav'>@devg4urav</a>",
            parse_mode=ParseMode.HTML,
            reply_markup=mainReplyKeyboard(u.id),
            message_effect_id=random.choice(EFFECT_IDS)
        )
        return

    is_admin = u.id in ADMIN_IDS or u.id in db.get("admins", [])
    user_data = db["users"].get(str(u.id), {})
    balance = user_data.get("balance", 0)

    if not is_admin and balance <= 0:
        bot_username = (await ctx.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={u.id}"
        
        last_refill_str = user_data.get("lastRefill", datetime.now().isoformat())
        try:
            last_refill = datetime.fromisoformat(last_refill_str)
        except Exception:
            last_refill = datetime.now()
        days_left = max(1, 5 - (datetime.now() - last_refill).days)

        await msg.reply_text(
            f"⚠️ <b>Out of Lookups</b>\n\n"
            f"You have used all your free lookups.\n"
            f"⏳ <b>Next free refill in:</b> <code>{days_left} days</code>\n\n"
            f"Share your referral link to earn more lookups! (1 lookup per referral)\n\n"
            f"🔗 <b>Your Link:</b>\n<code>{ref_link}</code>",
            parse_mode=ParseMode.HTML,
            message_effect_id=random.choice(EFFECT_IDS)
        )
        return

    # ── Cooldown Check ────────────────────────────────────────────────────────
    if not is_admin:
        now_time = time.time()
        last_req = COOLDOWNS.get(u.id, 0)
        if now_time - last_req < COOLDOWN_TIME:
            wait_time = int(COOLDOWN_TIME - (now_time - last_req))
            await msg.reply_text(
                f"⏳ <b>Spam Protection</b>\n\n"
                f"Please wait <code>{wait_time}s</code> before searching again.",
                parse_mode=ParseMode.HTML,
                reply_markup=mainReplyKeyboard(u.id),
                message_effect_id=random.choice(EFFECT_IDS)
            )
            return
        COOLDOWNS[u.id] = now_time

    if getattr(msg, "forward_origin", None):
        fwd = msg.forward_origin
        if hasattr(fwd, "sender_user") and fwd.sender_user:
            query = fwd.sender_user.username or str(fwd.sender_user.id)
        elif hasattr(fwd, "chat") and fwd.chat:
            query = fwd.chat.username or str(fwd.chat.id)

        if not query:
            await msg.reply_text(
                "🕵️‍♂️ <b>Could Not Extract Identity</b>\n\n"
                "This user has hidden their identity in forwards.\n"
                "Try entering their username or user ID manually.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back_main")]]),
                message_effect_id=random.choice(EFFECT_IDS)
            )
            return
    else:
        raw = msg.text.strip().lstrip("@") if msg.text else ""
        isNumericId = raw.lstrip("-").isdigit()
        if isNumericId:
            query = raw
        else:
            if not raw or len(raw) < 3 or len(raw) > 32 or not all(c.isalnum() or c == "_" for c in raw):
                await msg.reply_text(
                    "⚠️ <b>Invalid input.</b>\n\n"
                    "Send a username (3-32 chars, letters/numbers/underscores)\n"
                    "or a numeric Telegram user ID.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back_main")]]),
                    message_effect_id=random.choice(EFFECT_IDS)
                )
                return
            query = raw

    displayQuery = f"@{query}" if not str(query).lstrip("-").isdigit() else query
    loadingMsg = await msg.reply_text(
        f"⏳ <b>Looking up</b>  <code>{displayQuery}</code>\n<i>Bot is working... 📡</i>",
        parse_mode=ParseMode.HTML,
        message_effect_id=random.choice(EFFECT_IDS)
    )
    
    await ctx.bot.send_chat_action(chat_id=u.id, action=ChatAction.TYPING)

    data, err = await fetchUserInfo(query)
    await loadingMsg.delete()

    if err == "timeout":
        await msg.reply_text(
            "⌛ <b>Request Timed Out</b>\n\n"
            "The API is taking too long right now.\n"
            "<i>Try again in a moment.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=mainReplyKeyboard(u.id),
            message_effect_id=random.choice(EFFECT_IDS)
        )
        logLookup(u.id, u.username, u.first_name, query, None, False)
        asyncio.create_task(notify_admins_via_infobot(u.id, u.username, u.first_name, query, None, False))
        return

    if err or data is None:
        await msg.reply_text(
            "🔌 <b>Service Unavailable</b>\n\n"
            "The lookup API is currently unreachable.\n"
            "<i>Try again shortly.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=mainReplyKeyboard(u.id),
            message_effect_id=random.choice(EFFECT_IDS)
        )
        logLookup(u.id, u.username, u.first_name, query, None, False)
        asyncio.create_task(notify_admins_via_infobot(u.id, u.username, u.first_name, query, None, False))
        return

    has_profile = bool(data.get("user_id") or data.get("id") or data.get("username") or data.get("first_name"))
    phoneInfo = data.get("phone_info") or data
    has_phone = bool(phoneInfo.get("number") or phoneInfo.get("phone"))

    if not has_profile and not has_phone:
        reason = data.get("message") or data.get("error") or "User profile not found."
        await msg.reply_text(
            f"❌ <b>Lookup Failed</b>\n\n"
            f"<code>{reason}</code>\n\n"
            f"<code>{displayQuery}</code> may not exist or the API couldn't find them.",
            parse_mode=ParseMode.HTML,
            reply_markup=mainReplyKeyboard(u.id),
            message_effect_id=random.choice(EFFECT_IDS)
        )
        logLookup(u.id, u.username, u.first_name, query, data, False)
        asyncio.create_task(notify_admins_via_infobot(u.id, u.username, u.first_name, query, data, False))
        return

    resultText = buildResultMsg(data)
    pfp = data.get("profile_pic")

    ctx.user_data['last_result'] = data
    keyboard = result_keyboard(data)

    if pfp:
        try:
            photoMsg = await msg.reply_photo(photo=pfp)
            await photoMsg.reply_text(resultText, parse_mode=ParseMode.HTML, reply_markup=keyboard, message_effect_id=random.choice(EFFECT_IDS))
        except Exception:
            await msg.reply_text(resultText, parse_mode=ParseMode.HTML, reply_markup=keyboard, message_effect_id=random.choice(EFFECT_IDS))
    else:
        await msg.reply_text(resultText, parse_mode=ParseMode.HTML, reply_markup=keyboard, message_effect_id=random.choice(EFFECT_IDS))

    logLookup(u.id, u.username, u.first_name, query, data, True)
    asyncio.create_task(notify_admins_via_infobot(u.id, u.username, u.first_name, query, data, True))
    if not is_admin:
        db = loadDb()
        db["users"][str(u.id)]["balance"] = db["users"][str(u.id)].get("balance", 1) - 1
        saveDb(db)
    return

async def cmdPromotion(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = loadDb()
    if update.effective_user.id not in ADMIN_IDS and update.effective_user.id not in db.get("admins", []):
        return ConversationHandler.END

    await update.message.reply_text(
        "📢 <b>Promotion / Broadcast</b>\n\n"
        "Please send the message (text, photo, video, etc.) you want to broadcast to all users.\n\n"
        "Type /cancel to abort.",
        parse_mode=ParseMode.HTML,
        message_effect_id=random.choice(EFFECT_IDS)
    )
    return AWAIT_PROMO_MSG

async def cancelPromo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Broadcast cancelled.")
    return ConversationHandler.END

async def bg_broadcast(msg, users, status_msg):
    success = 0
    failed = 0
    for u in users:
        try:
            await msg.copy(chat_id=u["userId"])
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # Prevents Telegram flood limit errors
        
    try:
        await status_msg.edit_text(
            f"✅ <b>Broadcast Complete!</b>\n\n"
            f"📨 Total Attempted: {len(users)}\n"
            f"🟢 Success: {success}\n"
            f"🔴 Failed: {failed}",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

async def receivePromoMsg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    db = loadDb()
    users = list(db["users"].values())
    
    status_msg = await msg.reply_text(f"🚀 Starting background broadcast to {len(users)} users...\n\n<i>You can continue using the bot. You will be notified when it's done.</i>", parse_mode=ParseMode.HTML)
    
    # Run the broadcast in the background so it doesn't block the bot
    asyncio.create_task(bg_broadcast(msg, users, status_msg))
    
    return ConversationHandler.END


async def inlineQuery(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.inline_query.query.strip().lstrip("@")
    if not q or len(q) < 3:
        await update.inline_query.answer([], cache_time=0)
        return
    results = [
        InlineQueryResultArticle(
            id=q,
            title=f"Look up @{q}",
            description="Tap to fetch profile and phone info",
            input_message_content=InputTextMessageContent(
                f"<b>Lookup initiated for</b> <code>@{q}</code>\n\n"
                f"<i>Open the bot to see the result.</i>",
                parse_mode=ParseMode.HTML
            ),
        )
    ]
    await update.inline_query.answer(results, cache_time=0)


async def errorHandler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    log.error("Update %s caused error: %s", update, ctx.error)

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running successfully on Render Free Tier!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), DummyHandler).serve_forever()

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()

    adminConv = ConversationHandler(
        entry_points=[CommandHandler("admin", cmdAdmin)],
        states={
            AWAIT_ADMIN_PW:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receiveAdminPw)],
        },
        fallbacks=[CommandHandler("start", cmdStart)],
        allow_reentry=True,
        per_message=False,
    )

    maintConv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cbMaintenanceToggle, pattern="^adm_maintenance$")],
        states={
            AWAIT_MAINT_PW: [MessageHandler(filters.TEXT & ~filters.COMMAND, receiveMaintPw)],
        },
        fallbacks=[CallbackQueryHandler(cbAdminDashboard, pattern="^adm_dashboard$")],
        allow_reentry=True,
        per_message=False,
        per_chat=True,
        per_user=True,
    )
    
    addAdminConv = ConversationHandler(
        entry_points=[CommandHandler("addadmin", cmdAddAdmin)],
        states={
            AWAIT_ADD_ADMIN_PW: [MessageHandler(filters.TEXT & ~filters.COMMAND, receiveAddAdminPw)],
        },
        fallbacks=[CommandHandler("start", cmdStart)],
        allow_reentry=True,
        per_message=False,
    )

    delAdminConv = ConversationHandler(
        entry_points=[CommandHandler("deladmin", cmdDelAdmin)],
        states={
            AWAIT_DEL_ADMIN_PW: [MessageHandler(filters.TEXT & ~filters.COMMAND, receiveDelAdminPw)],
        },
        fallbacks=[CommandHandler("start", cmdStart)],
        allow_reentry=True,
        per_message=False,
    )

    promoConv = ConversationHandler(
        entry_points=[CommandHandler("promotion", cmdPromotion)],
        states={
            AWAIT_PROMO_MSG: [
                CommandHandler("cancel", cancelPromo),
                MessageHandler(filters.ALL & ~filters.COMMAND, receivePromoMsg)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancelPromo)],
        allow_reentry=True,
    )

    app.add_error_handler(errorHandler)
    app.add_handler(adminConv)
    app.add_handler(maintConv)
    app.add_handler(addAdminConv)
    app.add_handler(delAdminConv)
    app.add_handler(promoConv)
    app.add_handler(CommandHandler("start", cmdStart))
    app.add_handler(CommandHandler("stats", cmdStats))
    app.add_handler(CommandHandler("apistatus", cmdApiStatus))
    app.add_handler(CommandHandler("ban", cmdBan))
    app.add_handler(CommandHandler("unban", cmdUnban))
    app.add_handler(CommandHandler("setbalance", cmdSetBalance))
    app.add_handler(CommandHandler("addbalance", cmdAddBalance))
    app.add_handler(InlineQueryHandler(inlineQuery))
    app.add_handler(CallbackQueryHandler(cbBackMain,       pattern="^back_main$"))
    app.add_handler(CallbackQueryHandler(cbMyStats,        pattern="^myStats$"))
    app.add_handler(CallbackQueryHandler(cbMyReferral,     pattern="^myReferral$"))
    app.add_handler(CallbackQueryHandler(cbCheckJoined,    pattern="^check_joined$"))
    app.add_handler(CallbackQueryHandler(cb_download_vcf,  pattern="^download_vcf$"))
    app.add_handler(CallbackQueryHandler(cbAdminDashboard, pattern="^adm_dashboard$"))
    app.add_handler(CallbackQueryHandler(cbAdminUsers,     pattern="^adm_users_"))
    app.add_handler(CallbackQueryHandler(cbAdminLookups,   pattern="^adm_lookups_"))
    app.add_handler(CallbackQueryHandler(cbAdminToday,     pattern="^adm_today$"))
    app.add_handler(CallbackQueryHandler(cbAdminRate,      pattern="^adm_rate$"))
    app.add_handler(CallbackQueryHandler(cbAdminRecent,    pattern="^adm_recent$"))
    app.add_handler(CallbackQueryHandler(cbAdminClose,     pattern="^adm_close$"))
    app.add_handler(MessageHandler((filters.TEXT | filters.FORWARDED) & ~filters.COMMAND, receiveInput))

    log.info("Bot running")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    os._exit(0)


if __name__ == "__main__":
    main()
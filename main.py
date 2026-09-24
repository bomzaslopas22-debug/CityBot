import asyncio
import logging
import json
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiohttp

# ====================== NUSTATYMAI ======================
TOKEN = "8675019835:AAF2LbTUib6fwdUQonPcuSu23_faKPqcm38"  # ← ĮDĖK NAUJĄ TOKENĄ IŠ @BotFather
OWNER_ID = 8618585844
OWNER_SOL_WALLET = "8dnA6XsKYwAnXyaF1JLYE8b2qwPVgLzaW7SySejQLrTv"

DATA_FILE = "data.json"
USERS_FILE = "users.json"

# ====================== DUOMENYS ======================
def load_json(file):
    if not os.path.exists(file):
        return {}
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_json(DATA_FILE)
users = load_json(USERS_FILE)

def get_user(user_id: int):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "balance": 0.0,
            "total_spent": 0.0,
            "cart": [],
            "username": ""
        }
        save_json(USERS_FILE, users)
    return users[uid]

def save_users():
    save_json(USERS_FILE, users)

def get_status(total_spent: float) -> str:
    if total_spent >= 500:
        return "💎 Diamond"
    elif total_spent >= 200:
        return "🥇 Gold"
    elif total_spent >= 50:
        return "🥈 Silver"
    elif total_spent >= 10:
        return "🥉 Bronze"
    else:
        return "🆕 New"

# ====================== BOTAS ======================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class PhotoState(StatesGroup):
    waiting_photo = State()

async def get_sol_price_eur():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=eur") as resp:
                result = await resp.json()
                return result["solana"]["eur"]
    except:
        return None

# ---------- Klaviatūros ----------
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Shop", callback_data="shop")],
        [InlineKeyboardButton(text="👤 Profile", callback_data="profile")]
    ])

def cities_kb():
    buttons = []
    for city in data.keys():
        # Rodome miestą tik jei jame dar yra prekių
        has_items = any(len(stores) > 0 for stores in data[city].values())
        if has_items:
            buttons.append([InlineKeyboardButton(text=city, callback_data=f"city:{city}")])
    buttons.append([InlineKeyboardButton(text="« Atgal", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def districts_kb(city):
    buttons = []
    for district, stores in data.get(city, {}).items():
        if len(stores) > 0:  # Rodome tik tuos rajonus, kur dar yra prekių
            buttons.append([InlineKeyboardButton(
                text=f"{district} ({len(stores)})",
                callback_data=f"district:{city}:{district}"
            )])
    buttons.append([InlineKeyboardButton(text="« Atgal į miestus", callback_data="shop")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def stores_kb(city, district):
    stores = data[city][district]
    buttons = []
    for i, store in enumerate(stores):
        buttons.append([InlineKeyboardButton(
            text=f"{store['name']} — {store['price_eur']} €",
            callback_data=f"store:{city}:{district}:{i}"
        )])
    buttons.append([InlineKeyboardButton(text="« Atgal", callback_data=f"city:{city}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Krepšelis", callback_data="cart")],
        [InlineKeyboardButton(text="➕ Top up", callback_data="topup")],
        [InlineKeyboardButton(text="« Atgal", callback_data="back_main")]
    ])

def store_actions_kb(city, district, idx):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Į krepšelį", callback_data=f"addtocart:{city}:{district}:{idx}")],
        [InlineKeyboardButton(text="« Atgal", callback_data=f"district:{city}:{district}")]
    ])

# ---------- /start ----------
@dp.message(CommandStart())
async def start(message: Message):
    user = get_user(message.from_user.id)
    user["username"] = message.from_user.username or message.from_user

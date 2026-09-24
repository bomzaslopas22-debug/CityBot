import asyncio
import logging
import json
import os
import time
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiohttp
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.signature import Signature

# ====================== NUSTATYMAI ======================
TOKEN = "8675019835:AAHxpmuEJFE6truTUFtQfe3Bihjf-tFx9Zs"                  # ← ĮDĖK NAUJĄ TOKENĄ
OWNER_ID = 8618585844
OWNER_SOL_WALLET = "8dnA6XsKYwAnXyaF1JLYE8b2qwPVgLzaW7SySejQLrTv"

DATA_FILE = "data.json"
USERS_FILE = "users.json"
PROCESSED_FILE = "processed.json"

RPC_URL = "https://api.mainnet-beta.solana.com"   # Viešas RPC (gali būti lėtas)

# ====================== DUOMENYS ======================
def load_json(file, default=None):
    if default is None:
        default = {}
    if not os.path.exists(file):
        return default
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_json(DATA_FILE)
users = load_json(USERS_FILE)
processed_txs = set(load_json(PROCESSED_FILE, []))

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
    if total_spent >= 200:
        return "🥇 Gold"
    if total_spent >= 50:
        return "🥈 Silver"
    if total_spent >= 10:
        return "🥉 Bronze"
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
                return float(result["solana"]["eur"])
    except Exception as e:
        logging.error(f"SOL price error: {e}")
        return None

# ---------- Klaviatūros ----------
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Shop", callback_data="shop")],
        [InlineKeyboardButton(text="👤 Profile", callback_data="profile")]
    ])

def cities_kb():
    buttons = []
    for city in data:
        has_items = any(len(stores) > 0 for stores in data[city].values())
        if has_items:
            buttons.append([InlineKeyboardButton(text=city, callback_data=f"city:{city}")])
    buttons.append([InlineKeyboardButton(text="« Atgal", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def districts_kb(city):
    buttons = []
    for district, stores in data.get(city, {}).items():
        if len(stores) > 0:
            buttons.append([InlineKeyboardButton(
                text=f"{district} ({len(stores)})",
                callback_data=f"district:{city}:{district}"
            )])
    buttons.append([InlineKeyboardButton(text="« Atgal", callback_data="shop")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def stores_kb(city, district):
    buttons = []
    for i, store in enumerate(data[city][district]):
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
    user["username"] = message.from_user.username or message.from_user.first_name
    save_users()
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    await message.answer(f"Sveikas, {username}!", reply_markup=main_kb())

@dp.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery):
    username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.first_name
    await callback.message.edit_text(f"Sveikas, {username}!", reply_markup=main_kb())
    await callback.answer()

# ---------- SHOP ----------
@dp.callback_query(F.data == "shop")
async def shop(callback: CallbackQuery):
    if not any(any(len(s) > 0 for s in city.values()) for city in data.values()):
        await callback.answer("Šiuo metu nėra prekių.", show_alert=True)
        return
    await callback.message.edit_text("Pasirinkite miestą:", reply_markup=cities_kb())
    await callback.answer()

@dp.callback_query(F.data.startswith("city:"))
async def choose_city(callback: CallbackQuery):
    city = callback.data.split(":")[1]
    await callback.message.edit_text(
        f"Miestas: <b>{city}</b>\n\nPasirinkite rajoną:",
        reply_markup=districts_kb(city),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("district:"))
async def choose_district(callback: CallbackQuery):
    _, city, district = callback.data.split(":", 2)
    count = len(data.get(city, {}).get(district, []))
    text = (
        f"Miestas: <b>{city}</b>\n"
        f"Rajonas: <b>{district}</b>\n\n"
        f"Likę nenupirktų: <b>{count}</b>\n\n"
        f"Pasirinkite prekę:"
    )
    await callback.message.edit_text(text, reply_markup=stores_kb(city, district), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("store:"))
async def choose_store(callback: CallbackQuery):
    _, city, district, idx = callback.data.split(":")
    idx = int(idx)
    try:
        store = data[city][district][idx]
    except:
        await callback.answer("Ši prekė jau nupirkta.", show_alert=True)
        return

    text = (
        f"<b>{store['name']}</b>\n"
        f"📍 {store['address']}\n"
        f"💰 Kaina: <b>{store['price_eur']} €</b>"
    )
    await callback.message.edit_text(text, reply_markup=store_actions_kb(city, district, idx), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("addtocart:"))
async def add_to_cart(callback: CallbackQuery):
    _, city, district, idx = callback.data.split(":")
    idx = int(idx)
    user = get_user(callback.from_user.id)
    try:
        store = data[city][district][idx]
    except:
        await callback.answer("Prekė nebeegzistuoja.", show_alert=True)
        return

    user["cart"].append({
        "city": city,
        "district": district,
        "name": store["name"],
        "address": store["address"],
        "price_eur": store["price_eur"],
        "photo_id": store.get("photo_id")
    })
    save_users()
    await callback.answer("✅ Pridėta į krepšelį!", show_alert=True)

# ---------- PROFILE ----------
@dp.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    status = get_status(user["total_spent"])
    text = (
        f"👤 <b>Profilis</b>\n\n"
        f"Balansas: <b>{user['balance']:.2f} €</b>\n"
        f"Statusas: <b>{status}</b>\n"
        f"Išleista viso: <b>{user['total_spent']:.2f} €</b>\n"
        f"Krepšelyje: <b>{len(user['cart'])}</b> prekės"
    )
    await callback.message.edit_text(text, reply_markup=profile_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "cart")
async def show_cart(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user["cart"]:
        await callback.answer("Krepšelis tuščias.", show_alert=True)
        return

    total = sum(item["price_eur"] for item in user["cart"])
    text = "<b>🛒 Krepšelis</b>\n\n"
    for i, item in enumerate(user["cart"], 1):
        text += f"{i}. {item['name']} — {item['price_eur']} €\n"
    text += f"\n<b>Viso: {total:.2f} €</b>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Apmokėti kreditais", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Išvalyti", callback_data="clearcart")],
        [InlineKeyboardButton(text="« Atgal", callback_data="profile")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "clearcart")
async def clear_cart(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    user["cart"] = []
    save_users()
    await callback.answer("Krepšelis išvalytas", show_alert=True)
    await profile(callback)

@dp.callback_query(F.data == "checkout")
async def checkout(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user["cart"]:
        await callback.answer("Krepšelis tuščias", show_alert=True)
        return

    total = sum(item["price_eur"] for item in user["cart"])
    if user["balance"] < total:
        await callback.answer(f"Nepakanka kreditų. Reikia {total:.2f} €", show_alert=True)
        return

    user["balance"] -= total
    user["total_spent"] += total

    for item in user["cart"]:
        caption = f"<b>{item['name']}</b>\n📍 {item['address']}"
        try:
            if item.get("photo_id"):
                await bot.send_photo(callback.from_user.id, item["photo_id"], caption=caption, parse_mode="HTML")
            else:
                await bot.send_message(callback.from_user.id, caption, parse_mode="HTML")
        except:
            pass

        # Ištriname prekę
        try:
            city, district = item["city"], item["district"]
            for i, s in enumerate(data.get(city, {}).get(district, [])):
                if s["name"] == item["name"] and s["address"] == item["address"]:
                    data[city][district].pop(i)
                    break
            if city in data and district in data[city] and not data[city][district]:
                del data[city][district]
            if city in data and not data[city]:
                del data[city]
        except:
            pass

    user["cart"] = []
    save_users()
    save_json(DATA_FILE, data)

    await callback.message.edit_text("✅ Apmokėta! Prekės išsiųstos.", reply_markup=main_kb())
    await callback.answer()

# ---------- TOP UP (automatinis) ----------
@dp.callback_query(F.data == "topup")
async def topup(callback: CallbackQuery):
    sol_price = await get_sol_price_eur()
    if not sol_price:
        await callback.answer("Nepavyko gauti kurso. Bandyk vėliau.", show_alert=True)
        return

    memo = f"TOPUP_{callback.from_user.id}"
    text = (
        f"<b>➕ Top up (automatinis)</b>\n\n"
        f"Siųsk SOL į:\n<code>{OWNER_SOL_WALLET}</code>\n\n"
        f"<b>PRIVALOMA</b> įrašyti memo:\n<code>{memo}</code>\n\n"
        f"1 € ≈ <b>{round(1/sol_price, 4)} SOL</b>\n\n"
        f"Kai išsiųsi – botas pats per 1–2 minutes pridės kreditus."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Atgal", callback_data="profile")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ---------- AUTOMATINIS MOKĖJIMŲ STEBĖJIMAS ----------
async def check_payments():
    global processed_txs
    client = AsyncClient(RPC_URL)

    while True:
        try:
            pubkey = Pubkey.from_string(OWNER_SOL_WALLET)
            resp = await client.get_signatures_for_address(pubkey, limit=15)
            if not resp.value:
                await asyncio.sleep(40)
                continue

            sol_price = await get_sol_price_eur()
            if not sol_price:
                await asyncio.sleep(40)
                continue

            for sig_info in resp.value:
                sig_str = str(sig_info.signature)
                if sig_str in processed_txs:
                    continue

                try:
                    tx = await client.get_transaction(
                        Signature.from_string(sig_str),
                        encoding="jsonParsed",
                        max_supported_transaction_version=0
                    )
                    if not tx.value:
                        continue

                    meta = tx.value.transaction.meta
                    if meta is None or meta.err is not None:
                        continue

                    # Ieškome memo
                    memo = None
                    logs = meta.log_messages or []
                    for log in logs:
                        if "Memo" in log and "TOPUP_" in log:
                            # Bandome ištraukti memo
                            start = log.find("TOPUP_")
                            if start != -1:
                                memo = log[start:].split()[0].strip('"').strip("'")
                                break

                    if not memo or not memo.startswith("TOPUP_"):
                        processed_txs.add(sig_str)
                        continue

                    try:
                        user_id = int(memo.split("_")[1])
                    except:
                        processed_txs.add(sig_str)
                        continue

                    # Skaičiuojame gautą SOL (paprastas būdas)
                    pre = meta.pre_balances
                    post = meta.post_balances
                    if not pre or not post:
                        processed_txs.add(sig_str)
                        continue

                    # Randame savininko indeką
                    account_keys = tx.value.transaction.transaction.message.account_keys
                    owner_idx = None
                    for i, acc in enumerate(account_keys):
                        if str(acc) == OWNER_SOL_WALLET or (hasattr(acc, "pubkey") and str(acc.pubkey) == OWNER_SOL_WALLET):
                            owner_idx = i
                            break

                    if owner_idx is None:
                        processed_txs.add(sig_str)
                        continue

                    sol_received = (post[owner_idx] - pre[owner_idx]) / 1_000_000_000
                    if sol_received <= 0.001:  # per mažai
                        processed_txs.add(sig_str)
                        continue

                    eur_amount = round(sol_received * sol_price, 2)
                    if eur_amount < 0.5:
                        processed_txs.add(sig_str)
                        continue

                    # Pridedame kreditus
                    user = get_user(user_id)
                    user["balance"] += eur_amount
                    save_users()

                    processed_txs.add(sig_str)
                    save_json(PROCESSED_FILE, list(processed_txs))

                    try:
                        await bot.send_message(
                            user_id,
                            f"✅ Gauta <b>{eur_amount} €</b> kreditų!\n"
                            f"Tavo balansas: <b>{user['balance']:.2f} €</b>",
                            parse_mode="HTML"
                        )
                        await bot.send_message(
                            OWNER_ID,
                            f"💰 Automatinis top-up\n"
                            f"Vartotojas: {user_id}\n"
                            f"Suma: {eur_amount} € ({sol_received:.4f} SOL)"
                        )
                    except Exception as e:
                        logging.error(f"Notify error: {e}")

                except Exception as e:
                    logging.error(f"Tx process error: {e}")
                    continue

        except Exception as e:
            logging.error(f"Check payments error: {e}")

        await asyncio.sleep(40)

# ---------- ADMIN ----------
@dp.message(Command("addstore"))
async def add_store(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    try:
        parts = message.text.split(" ", 1)[1].split("|")
        city, district, name, address, price = [p.strip() for p in parts]
        price = float(price)
        if city not in data:
            data[city] = {}
        if district not in data[city]:
            data[city][district] = []
        data[city][district].append({
            "name": name,
            "address": address,
            "price_eur": price,
            "photo_id": None
        })
        save_json(DATA_FILE, data)
        await message.answer(f"✅ Pridėta: {name} ({price} €)")
    except:
        await message.answer("Formatas:\n/addstore Miestas|Rajonas|Pavadinimas|Adresas|Kaina")

@dp.message(Command("foto"))
async def foto_cmd(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    try:
        parts = message.text.split(" ", 1)[1].split("|")
        city, district, name = [p.strip() for p in parts]
        found = None
        for i, store in enumerate(data.get(city, {}).get(district, [])):
            if store["name"].lower() == name.lower():
                found = (city, district, i)
                break
        if not found:
            await message.answer("Prekė nerasta")
            return
        await state.update_data(store_key=found)
        await state.set_state(PhotoState.waiting_photo)
        await message.answer("Atsiųsk nuotrauką:")
    except:
        await message.answer("Formatas:\n/foto Miestas|Rajonas|Pavadinimas")

@dp.message(PhotoState.waiting_photo, F.photo)
async def save_photo(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    st = await state.get_data()
    city, district, idx = st["store_key"]
    data[city][district][idx]["photo_id"] = message.photo[-1].file_id
    save_json(DATA_FILE, data)
    await state.clear()
    await message.answer("✅ Nuotrauka išsaugota!")

@dp.message(Command("list"))
async def list_stores(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if not data:
        await message.answer("Tuščia")
        return
    text = ""
    for city, districts in data.items():
        text += f"\n<b>{city}</b>\n"
        for dist, stores in districts.items():
            text += f"  {dist} ({len(stores)}):\n"
            for s in stores:
                photo = "📷" if s.get("photo_id") else "❌"
                text += f"    {photo} {s['name']} — {s['price_eur']}€\n"
    await message.answer(text or "Tuščia", parse_mode="HTML")

# ---------- Paleidimas ----------
async def main():
    asyncio.create_task(check_payments())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
import json
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiohttp

# ====================== NUSTATYMAI ======================
TOKEN = "8675019835:AAF2LbTUib6fwdUQonPcuSu23_faKPqcm38"         # ← čia turi būti tavo tokenas
OWNER_ID = 8618585844
OWNER_SOL_WALLET = "8dnA6XsKYwAnXyaF1JLYE8b2qwPVgLzaW7SySejQLrTv"
DATA_FILE = "data.json"

# ====================== DUOMENYS ======================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()
pending = {}  # laikinai laukiantys mokėjimai

# ====================== BOTAS ======================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

class PhotoState(StatesGroup):
    waiting_photo = State()

# ---------- SOL kaina ----------
async def get_sol_price_eur():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=eur") as resp:
                result = await resp.json()
                return result["solana"]["eur"]
    except:
        return None

# ---------- Klaviatūros ----------
def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Pirkti", callback_data="buy")]
    ])

def cities_kb():
    buttons = [[InlineKeyboardButton(text=city, callback_data=f"city:{city}")] for city in data.keys()]
    buttons.append([InlineKeyboardButton(text="« Atgal", callback_data="back_start")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def districts_kb(city):
    buttons = [[InlineKeyboardButton(text=d, callback_data=f"district:{city}:{d}")] for d in data.get(city, {}).keys()]
    buttons.append([InlineKeyboardButton(text="« Atgal į miestus", callback_data="buy")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def stores_kb(city, district):
    stores = data[city][district]
    buttons = []
    for i, store in enumerate(stores):
        buttons.append([InlineKeyboardButton(
            text=f"{store['name']} — {store['price_eur']} €",
            callback_data=f"store:{city}:{district}:{i}"
        )])
    buttons.append([InlineKeyboardButton(text="« Atgal į rajonus", callback_data=f"city:{city}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- /start ----------
@dp.message(CommandStart())
async def start(message: Message):
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
    text = f"Sveikas, {username}!\n\nPasirink veiksmą:"
    await message.answer(text, reply_markup=start_kb())

@dp.callback_query(F.data == "back_start")
async def back_start(callback: CallbackQuery):
    username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.first_name
    await callback.message.edit_text(f"Sveikas, {username}!\n\nPasirink veiksmą:", reply_markup=start_kb())
    await callback.answer()

@dp.callback_query(F.data == "buy")
async def buy_start(callback: CallbackQuery):
    if not data:
        await callback.answer("Šiuo metu nėra jokių pasiūlymų.", show_alert=True)
        return
    await callback.message.edit_text("Pasirinkite miestą:", reply_markup=cities_kb())
    await callback.answer()

@dp.callback_query(F.data.startswith("city:"))
async def choose_city(callback: CallbackQuery):
    city = callback.data.split(":")[1]
    if city not in data or not data[city]:
        await callback.answer("Šiame mieste nieko nėra.", show_alert=True)
        return
    await callback.message.edit_text(f"Miestas: <b>{city}</b>\n\nPasirinkite rajoną:", 
                                     reply_markup=districts_kb(city), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("district:"))
async def choose_district(callback: CallbackQuery):
    _, city, district = callback.data.split(":", 2)
    stores = data.get(city, {}).get(district, [])
    count = len(stores)
    
    text = f"Miestas: <b>{city}</b>\nRajonas: <b>{district}</b>\n\n"
    text += f"Likę nenupirktų: <b>{count}</b>\n\nPasirinkite:"
    
    await callback.message.edit_text(text, reply_markup=stores_kb(city, district), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("store:"))
async def choose_store(callback: CallbackQuery):
    _, city, district, idx = callback.data.split(":")
    idx = int(idx)
    
    try:
        store = data[city][district][idx]
    except:
        await callback.answer("Šis pasiūlymas jau nupirktas.", show_alert=True)
        return

    sol_price = await get_sol_price_eur()
    if not sol_price:
        await callback.answer("Nepavyko gauti SOL kurso. Bandykite vėliau.", show_alert=True)
        return

    sol_amount = round(store["price_eur"] / sol_price, 4)
    memo = f"TG{callback.from_user.id}_{city}_{district}_{idx}"

    # Išsaugome laukiantį mokėjimą
    pending[callback.from_user.id] = {
        "city": city,
        "district": district,
        "idx": idx,
        "store": store
    }

    text = (
        f"<b>{store['name']}</b>\n"
        f"Kaina: <b>{store['price_eur']} €</b>\n"
        f"Reikia sumokėti: <b>{sol_amount} SOL</b>\n\n"
        f"Siųskite į piniginę:\n<code>{OWNER_SOL_WALLET}</code>\n\n"
        f"<b>PRIVALOMA</b> įrašyti memo:\n<code>{memo}</code>\n\n"
        f"Kai sumokėsite – parašykite /sumokejau"
    )
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()

@dp.message(Command("sumokejau"))
async def payment_claimed(message: Message):
    user_id = message.from_user.id
    if user_id not in pending:
        await message.answer("Nerasta laukiančio mokėjimo. Pirmiausia pasirinkite prekę.")
        return

    await bot.send_message(
        OWNER_ID,
        f"🔔 Galimas mokėjimas!\n\n"
        f"Vartotojas: @{message.from_user.username or 'be_username'} (ID: {user_id})\n"
        f"Prekė: {pending[user_id]['store']['name']}\n\n"
        f"Patvirtinti: /patvirtinti {user_id}"
    )
    await message.answer("Ačiū! Laukite patvirtinimo iš administratoriaus.")

@dp.message(Command("patvirtinti"))
async def confirm_payment(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    try:
        user_id = int(message.text.split()[1])
        if user_id not in pending:
            await message.answer("Nerasta laukiančio mokėjimo šiam vartotojui.")
            return

        info = pending.pop(user_id)
        store = info["store"]
        city = info["city"]
        district = info["district"]
        idx = info["idx"]

        # Siunčiame adresą + nuotrauką
        caption = f"<b>{store['name']}</b>\n📍 Adresas: {store['address']}"
        
        if store.get("photo_id"):
            await bot.send_photo(user_id, store["photo_id"], caption=caption, parse_mode="HTML")
        else:
            await bot.send_message(user_id, caption, parse_mode="HTML")

        # Ištriname parduotuvę
        data[city][district].pop(idx)
        if not data[city][district]:
            del data[city][district]
        if not data[city]:
            del data[city]
        save_data(data)

        await bot.send_message(user_id, "✅ Mokėjimas patvirtintas! Štai jūsų informacija.")
        await message.answer("Patvirtinta. Prekė ištrinta ir išsiųsta pirkėjui.")
    except Exception as e:
        await message.answer(f"Klaida: {e}")

# ---------- Admin komandos ----------
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
        save_data(data)
        await message.answer(f"✅ Pridėta: {name} ({price} €)\nDabar gali pridėti nuotrauką su /foto")
    except:
        await message.answer("Formatas:\n/addstore Miestas|Rajonas|Pavadinimas|Adresas|Kaina")

@dp.message(Command("foto"))
async def foto_cmd(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    try:
        parts = message.text.split(" ", 1)[1].split("|")
        city, district, name = [p.strip() for p in parts]
        
        # Ieškome parduotuvės
        found = None
        for i, store in enumerate(data.get(city, {}).get(district, [])):
            if store["name"].lower() == name.lower():
                found = (city, district, i)
                break
        
        if not found:
            await message.answer("Tokios parduotuvės nerasta.")
            return
        
        await state.update_data(store_key=found)
        await state.set_state(PhotoState.waiting_photo)
        await message.answer("Atsiųsk nuotrauką šiai parduotuvei:")
    except:
        await message.answer("Formatas:\n/foto Miestas|Rajonas|Pavadinimas")

@dp.message(PhotoState.waiting_photo, F.photo)
async def save_photo(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    data_state = await state.get_data()
    city, district, idx = data_state["store_key"]
    
    photo_id = message.photo[-1].file_id
    data[city][district][idx]["photo_id"] = photo_id
    save_data(data)
    
    await state.clear()
    await message.answer("✅ Nuotrauka išsaugota!")

@dp.message(Command("list"))
async def list_stores(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if not data:
        await message.answer("Sąrašas tuščias")
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

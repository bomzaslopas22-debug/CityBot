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
TOKEN = "8675019835:AAF2LbTUib6fwdUQonPcuSu23_faKPqcm38"        # Palik savo tokeną
OWNER_ID = 8618585844                       # Tavo Telegram ID
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

# ====================== BOTAS ======================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ---------- Pagalbinės funkcijos ----------
async def get_sol_price_eur():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=eur") as resp:
                result = await resp.json()
                return result["solana"]["eur"]
    except:
        return None

def cities_kb():
    buttons = [[InlineKeyboardButton(text=city, callback_data=f"city:{city}")] for city in data.keys()]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def districts_kb(city):
    buttons = [[InlineKeyboardButton(text=d, callback_data=f"district:{city}:{d}")] for d in data[city].keys()]
    buttons.append([InlineKeyboardButton(text="« Atgal", callback_data="back_cities")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def stores_kb(city, district):
    buttons = []
    for i, store in enumerate(data[city][district]):
        buttons.append([InlineKeyboardButton(
            text=f"{store['name']} — {store['price_eur']} €",
            callback_data=f"store:{city}:{district}:{i}"
        )])
    buttons.append([InlineKeyboardButton(text="« Atgal", callback_data=f"back_districts:{city}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- Vartotojo dalis ----------
@dp.message(CommandStart())
async def start(message: Message):
    if not data:
        await message.answer("Šiuo metu nėra jokių parduotuvių.")
        return
    await message.answer("Pasirinkite miestą:", reply_markup=cities_kb())

@dp.callback_query(F.data == "back_cities")
async def back_cities(callback: CallbackQuery):
    await callback.message.edit_text("Pasirinkite miestą:", reply_markup=cities_kb())
    await callback.answer()

@dp.callback_query(F.data.startswith("city:"))
async def choose_city(callback: CallbackQuery):
    city = callback.data.split(":")[1]
    await callback.message.edit_text(f"Miestas: <b>{city}</b>\nPasirinkite rajoną:", 
                                     reply_markup=districts_kb(city), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("back_districts:"))
async def back_districts(callback: CallbackQuery):
    city = callback.data.split(":")[1]
    await callback.message.edit_text(f"Miestas: <b>{city}</b>\nPasirinkite rajoną:", 
                                     reply_markup=districts_kb(city), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("district:"))
async def choose_district(callback: CallbackQuery):
    _, city, district = callback.data.split(":", 2)
    await callback.message.edit_text(
        f"Miestas: <b>{city}</b>\nRajonas: <b>{district}</b>\n\nPasirinkite parduotuvę:",
        reply_markup=stores_kb(city, district), parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("store:"))
async def choose_store(callback: CallbackQuery):
    _, city, district, idx = callback.data.split(":")
    idx = int(idx)
    store = data[city][district][idx]

    sol_price = await get_sol_price_eur()
    if not sol_price:
        await callback.answer("Nepavyko gauti SOL kurso. Bandykite vėliau.", show_alert=True)
        return

    sol_amount = round(store["price_eur"] / sol_price, 4)
    memo = f"TG{callback.from_user.id}_{city}_{district}_{idx}"

    text = (
        f"<b>{store['name']}</b>\n"
        f"Kaina: <b>{store['price_eur']} €</b>\n"
        f"Reikia sumokėti: <b>{sol_amount} SOL</b>\n\n"
        f"Siųskite į piniginę:\n<code>{OWNER_SOL_WALLET}</code>\n\n"
        f"<b>PRIVALOMA</b> įrašyti memo (komentarą):\n<code>{memo}</code>\n\n"
        f"Kai sumokėsite – parašykite čia /sumokejau"
    )
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()

@dp.message(Command("sumokejau"))
async def payment_claimed(message: Message):
    await bot.send_message(
        OWNER_ID,
        f"🔔 Galimas mokėjimas!\n\n"
        f"Vartotojas: @{message.from_user.username or 'nėra'} (ID: {message.from_user.id})\n"
        f"Patvirtinti: /patvirtinti {message.from_user.id}"
    )
    await message.answer("Ačiū! Laukite patvirtinimo.")

# ---------- Admin komandos ----------
@dp.message(Command("addstore"))
async def add_store(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    # Formatas: /addstore Miestas|Rajonas|Pavadinimas|Adresas|Kaina
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
            "price_eur": price
        })
        save_data(data)
        await message.answer(f"✅ Pridėta: {name} ({price} €)")
    except Exception as e:
        await message.answer("Neteisingas formatas.\nNaudok:\n/addstore Miestas|Rajonas|Pavadinimas|Adresas|Kaina")

@dp.message(Command("patvirtinti"))
async def confirm_payment(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    try:
        user_id = int(message.text.split()[1])
        # Čia paprastumo dėlei kol kas tik pranešame
        # Vėliau pridėsime automatinį adreso davimą + ištrynimą
        await bot.send_message(user_id, "✅ Mokėjimas patvirtintas! Netrukus gausite adresą.")
        await message.answer("Patvirtinta. Dabar reikia rankiniu būdu duoti adresą (kol kas).")
    except:
        await message.answer("Naudok: /patvirtinti USER_ID")

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
            text += f"  {dist}:\n"
            for s in stores:
                text += f"    • {s['name']} — {s['price_eur']}€\n"
    await message.answer(text or "Tuščia", parse_mode="HTML")

# ---------- Paleidimas ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

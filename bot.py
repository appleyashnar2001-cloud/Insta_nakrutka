import os
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Telegram Bot Token va Admin ID
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 7180864511  # Siz taqdim etgan Admin ID

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Baza bilan ishlash
conn = sqlite3.connect("nakrutka.db")
cursor = conn.cursor()

# Jadvallarni yaratish
cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS prices (service TEXT, amount INT, price REAL, PRIMARY KEY (service, amount))''')
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INT PRIMARY KEY, username TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, service TEXT, amount INT, link TEXT, status TEXT)''')
conn.commit()

# Standart sozlamalarni kiritish
services = ['obunachi', 'layk', 'korish', 'komentariya']
amounts = [100, 500, 1000]
for s in services:
    for a in amounts:
        cursor.execute("INSERT OR IGNORE INTO prices VALUES (?, ?, ?)", (s, a, 10000.0))
cursor.execute("INSERT OR IGNORE INTO settings VALUES ('card', '8600000000000000')")
conn.commit()

# FSM (Holatlar)
class AdminStates(StatesGroup):
    set_card = State()
    set_price_value = State()

class UserStates(StatesGroup):
    get_link = State()
    send_check = State()

# --- KLAVIATURALAR ---
def main_menu(user_id):
    kb = [
        [KeyboardButton(text="👤 Obunachi qo'shish"), KeyboardButton(text="❤️ Layk ko'paytirish")],
        [KeyboardButton(text="👁 Ko'rishlarni ko'paytirish"), KeyboardButton(text="💬 Kommentariyalar")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="⚙️ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Karta raqamni o'zgartirish", callback_data="admin_card")],
        [InlineKeyboardButton(text="💰 Narxlarni o'zgartirish", callback_data="admin_prices")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")]
    ])

# --- ADMIN HANDLERS ---
@dp.message(F.text == "⚙️ Admin Panel")
async def open_admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Xush kelibsiz Admin! Kerakli bo'limni tanlang:", reply_markup=admin_menu())

@dp.callback_query(F.data == "admin_card")
async def admin_card_edit(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='card'")
    current_card = cursor.fetchone()[0]
    await call.message.answer(f"Hozirgi karta: `{current_card}`\nYangi karta raqamini yuboring:", parse_mode="Markdown")
    await state.set_state(AdminStates.set_card)

@dp.message(AdminStates.set_card)
async def save_card(message: types.Message, state: FSMContext):
    cursor.execute("UPDATE settings SET value=? WHERE key='card'", (message.text,))
    conn.commit()
    await message.answer("✅ Karta raqami muvaffaqiyatli yangilandi!", reply_markup=main_menu(ADMIN_ID))
    await state.clear()

@dp.callback_query(F.data == "admin_prices")
async def admin_prices_edit(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Obunachi", callback_data="pr_obunachi"), InlineKeyboardButton(text="Layk", callback_data="pr_layk")],
        [InlineKeyboardButton(text="Ko'rishlar", callback_data="pr_korish"), InlineKeyboardButton(text="Kommentariya", callback_data="pr_komentariya")]
    ])
    await call.message.answer("Qaysi bo'lim narxini o'zgartirmoqchisiz?", reply_markup=kb)

@dp.callback_query(F.data.startswith("pr_"))
async def admin_select_amount(call: types.CallbackQuery, state: FSMContext):
    service = call.data.split("_")[1]
    await state.update_data(chosen_service=service)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="100 ta", callback_data="am_100"), InlineKeyboardButton(text="500 ta", callback_data="am_500"), InlineKeyboardButton(text="1000 ta", callback_data="am_1000")]
    ])
    await call.message.answer(f"{service.capitalize()} uchun miqdorni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("am_"))
async def admin_set_price(call: types.CallbackQuery, state: FSMContext):
    amount = int(call.data.split("_")[1])
    await state.update_data(chosen_amount=amount)
    await call.message.answer(f"Yangi narxni kiriting (so'mda):")
    await state.set_state(AdminStates.set_price_value)

@dp.message(AdminStates.set_price_value)
async def save_price(message: types.Message, state: FSMContext):
    try:
        new_price = float(message.text)
        data = await state.get_data()
        cursor.execute("UPDATE prices SET price=? WHERE service=? AND amount=?", (new_price, data['chosen_service'], data['chosen_amount']))
        conn.commit()
        await message.answer(f"✅ Narx saqlandi: {data['chosen_service']} - {data['chosen_amount']} ta = {new_price} so'm", reply_markup=main_menu(ADMIN_ID))
        await state.clear()
    except ValueError:
        await message.answer("Iltimos faqat raqam kiriting!")

@dp.callback_query(F.data == "admin_stats")
async def show_stats(call: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM users")
    u_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status='Tasdiqlandi'")
    o_count = cursor.fetchone()[0]
    await call.message.answer(f"📊 *Bot statistikasi:*\n\n👥 Foydalanuvchilar: {u_count} ta\n✅ Bajarilgan buyurtmalar: {o_count} ta", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_order(call: types.CallbackQuery):
    order_id = call.data.split("_")[1]
    cursor.execute("SELECT user_id, service, amount, link FROM orders WHERE id=?", (order_id,))
    order = cursor.fetchone()
    if order:
        user_id, service, amount, link = order
        cursor.execute("UPDATE orders SET status='Tasdiqlandi' WHERE id=?", (order_id,))
        conn.commit()
        await call.message.edit_text(f"✅ Buyurtma #{order_id} tasdiqlandi!")
        try:
            await bot.send_message(user_id, f"🎉 To'lovingiz tasdiqlandi! *{amount} ta {service}* yuborish boshlandi.\nProfil: {link}", parse_mode="Markdown")
        except: pass

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_order(call: types.CallbackQuery):
    order_id = call.data.split("_")[1]
    cursor.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    user_id = cursor.fetchone()[0]
    cursor.execute("UPDATE orders SET status='Rad etildi' WHERE id=?", (order_id,))
    conn.commit()
    await call.message.edit_text(f"❌ Buyurtma #{order_id} rad etildi.")
    try:
        await bot.send_message(user_id, "❌ Afsuski, siz yuborgan chek tasdiqlanmadi. Agar xatolik bo'lsa, adminga murojaat qiling.")
    except: pass

# --- USER HANDLERS ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?)", (message.from_user.id, message.from_user.username))
    conn.commit()
    await message.answer("Xush kelibsiz! Instagram xizmatlaridan foydalanish uchun quyidagi bo'limlardan birini tanlang:", 
                         reply_markup=main_menu(message.from_user.id))

@dp.message(F.text.in_(["👤 Obunachi qo'shish", "❤️ Layk ko'paytirish", "👁 Ko'rishlarni ko'paytirish", "💬 Kommentariyalar"]))
async def select_service(message: types.Message, state: FSMContext):
    text = message.text
    service_map = {
        "👤 Obunachi qo'shish": "obunachi",
        "❤️ Layk ko'paytirish": "layk",
        "👁 Ko'rishlarni ko'paytirish": "korish",
        "💬 Kommentariyalar": "komentariya"
    }
    service = service_map[text]
    await state.update_data(user_service=service)
    
    cursor.execute("SELECT amount, price FROM prices WHERE service=?", (service,))
    prices = cursor.fetchall()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for amount, price in prices:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{amount} ta - {price} so'm", callback_data=f"user_am_{amount}_{price}")])
        
    await message.answer(f"✨ {text} bo'limi. Miqdorni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("user_am_"))
async def user_amount_select(call: types.CallbackQuery, state: FSMContext):
    _, _, amount, price = call.data.split("_")
    await state.update_data(user_amount=int(amount), user_price=float(price))
    await call.message.answer("🔗 Instagram profilingiz yoki postingiz havolasini (linkini) yuboring:")
    await state.set_state(UserStates.get_link)

@dp.message(UserStates.get_link)
async def user_link_get(message: types.Message, state: FSMContext):
    if not message.text.startswith(("http://", "https://")):
        await message.answer("⚠️ Iltimos, to'g'ri havola yuboring (masalan: https://instagram.com/...)")
        return
        
    await state.update_data(user_link=message.text)
    cursor.execute("SELECT value FROM settings WHERE key='card'")
    card = cursor.fetchone()[0]
    data = await state.get_data()
    
    pay_text = f"💳 *To'lov tafsilotlari:*\n\n" \
               f"💰 To'lov miqdori: *{data['user_price']} so'm*\n" \
               f"📌 Xizmat: {data['user_amount']} ta {data['user_service']}\n"                f"💳 Karta raqam: `{card}`\n\n" \
               f"To'lovni amalga oshirib, *chekni (skrinshot formatida)* shu yerga yuboring."
               
    await message.answer(pay_text, parse_mode="Markdown")
    await state.set_state(UserStates.send_check)

@dp.message(UserStates.send_check, F.photo)
async def user_check_get(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id
    
    cursor.execute("INSERT INTO orders (user_id, service, amount, link, status) VALUES (?, ?, ?, ?, 'Kutilmoqda')",
                   (message.from_user.id, data['user_service'], data['user_amount'], data['user_link'],))
    conn.commit()
    order_id = cursor.lastrowid
    
    await message.answer("⏳ Rahmat! Chek adminga yuborildi. Tasdiqlanishini kuting.")
    await state.clear()
    
    admin_text = f"🔔 *Yangi buyurtma #{order_id}*\n\n" \
                 f"👤 Kimdan: @{message.from_user.username} (ID: {message.from_user.id})\n" \
                 f"📦 Xizmat: {data['user_amount']} ta {data['user_service']}\n" \
                 f"🔗 Link: {data['user_link']}\n" \
                 f"💵 To'lov miqdori: {data['user_price']} so'm"
                 
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm_{order_id}")],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"cancel_{order_id}")]
    ])
    await bot.send_photo(ADMIN_ID, photo=photo_id, caption=admin_text, reply_markup=kb, parse_mode="Markdown")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
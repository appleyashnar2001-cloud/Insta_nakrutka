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

# Jadvallarni yangilash va yaratish
cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS prices (service TEXT, amount INT, price REAL, PRIMARY KEY (service, amount))''')
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INT PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, service TEXT, amount INT, link TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, amount REAL, photo_id TEXT, status TEXT)''')
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
    deposit_amount = State()
    deposit_check = State()
    get_link = State()

# --- KLAVIATURALAR ---
def main_menu(user_id):
    kb = [
        [KeyboardButton(text="👤 Shaxsiy Kabinet / Balans")],
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
        [InlineKeyboardButton(text="📥 To'lovlar bo'limi", callback_data="admin_deposits_menu")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")]
    ])

# --- ADMIN HANDLERS ---
@dp.message(F.text == "⚙️ Admin Panel")
async def open_admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("⚙️ *Admin panelga xush kelibsiz!* Kerakli bo'limni tanlang:", reply_markup=admin_menu(), parse_mode="Markdown")

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

# To'lovlar bo'limi menyusi
@dp.callback_query(F.data == "admin_deposits_menu")
async def admin_deposits_menu(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Kutilayotgan to'lovlar", callback_data="dep_status_Kutilmoqda")],
        [InlineKeyboardButton(text="✅ Tasdiqlanganlar", callback_data="dep_status_Tasdiqlandi")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin")]
    ])
    await call.message.edit_text("📥 *To'lovlar bo'limi:*", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(call: types.CallbackQuery):
    await call.message.edit_text("⚙️ *Admin panelga xush kelibsiz!* Kerakli bo'limni tanlang:", reply_markup=admin_menu(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("dep_status_"))
async def show_deposits_by_status(call: types.CallbackQuery):
    status = call.data.split("_")[2]
    cursor.execute("SELECT id, user_id, amount FROM deposits WHERE status=?", (status,))
    deps = cursor.fetchall()
    
    if not deps:
        await call.answer(f"Bu bo'limda to'lovlar mavjud emas.", show_alert=True)
        return
        
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for dep_id, u_id, amount in deps:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"ID: {dep_id} | Foydalanuvchi: {u_id} | {amount} so'm", callback_data=f"view_dep_{dep_id}")])
    
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_deposits_menu")])
    await call.message.edit_text(f"📥 *{status}* holatidagi to'lovlar ro'yxati:", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("view_dep_"))
async def view_single_deposit(call: types.CallbackQuery):
    dep_id = call.data.split("_")[2]
    cursor.execute("SELECT user_id, amount, photo_id, status FROM deposits WHERE id=?", (dep_id,))
    dep = cursor.fetchone()
    
    if dep:
        user_id, amount, photo_id, status = dep
        caption = f"💵 *To'lov tafsilotlari #{dep_id}*\n\n👤 Foydalanuvchi ID: `{user_id}`\n💰 Miqdor: *{amount} so'm*\n📊 Holati: *{status}*"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        if status == "Kutilmoqda":
            kb.inline_keyboard.append([
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_dep_{dep_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_dep_{dep_id}")
            ])
        kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Ro'yxatga qaytish", callback_data=f"dep_status_{status}")])
        
        await call.message.delete()
        await bot.send_photo(ADMIN_ID, photo=photo_id, caption=caption, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("approve_dep_"))
async def approve_deposit(call: types.CallbackQuery):
    dep_id = call.data.split("_")[2]
    cursor.execute("SELECT user_id, amount, status FROM deposits WHERE id=?", (dep_id,))
    dep = cursor.fetchone()
    
    if dep and dep[2] == "Kutilmoqda":
        user_id, amount, _ = dep
        # Balansni yangilash
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        cursor.execute("UPDATE deposits SET status = 'Tasdiqlandi' WHERE id = ?", (dep_id,))
        conn.commit()
        
        await call.message.edit_caption(caption=f"✅ To'lov #{dep_id} muvaffaqiyatli tasdiqlandi va balansga qo'shildi!")
        try:
            await bot.send_message(user_id, f"🎉 To'lovingiz tasdiqlandi! Balansingizga *{amount} so'm* qo'shildi va botdan to'liq foydalanishingiz mumkin.", parse_mode="Markdown")
        except: pass

@dp.callback_query(F.data.startswith("reject_dep_"))
async def reject_deposit(call: types.CallbackQuery):
    dep_id = call.data.split("_")[2]
    cursor.execute("SELECT user_id, status FROM deposits WHERE id=?", (dep_id,))
    dep = cursor.fetchone()
    
    if dep and dep[1] == "Kutilmoqda":
        user_id = dep[0]
        cursor.execute("UPDATE deposits SET status = 'Rad etildi' WHERE id = ?", (dep_id,))
        conn.commit()
        
        await call.message.edit_caption(caption=f"❌ To'lov #{dep_id} rad etildi.")
        try:
            await bot.send_message(user_id, f"❌ Siz yuborgan chek #{dep_id} admin tomonidan rad etildi. Muammo bo'lsa adminga murojaat qiling.")
        except: pass

@dp.callback_query(F.data == "admin_stats")
async def show_stats(call: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM users")
    u_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders")
    o_count = cursor.fetchone()[0]
    await call.message.answer(f"📊 *Bot statistikasi:*\n\n👥 Jami foydalanuvchilar: {u_count} ta\n📦 Bajarilgan nakrutkalar: {o_count} ta", parse_mode="Markdown")


# --- USER HANDLERS ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (message.from_user.id, message.from_user.username))
    conn.commit()
    await message.answer("✨ Xush kelibsiz! Instagram xizmatlaridan foydalanish uchun quyidagi bo'limlardan birini tanlang:", 
                         reply_markup=main_menu(message.from_user.id))

@dp.message(F.text == "👤 Shaxsiy Kabinet / Balans")
async def user_cabinet(message: types.Message):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (message.from_user.id,))
    balance = cursor.fetchone()[0]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Balansni to'ldirish", callback_data="user_deposit")]
    ])
    await message.answer(f"👤 *Sizning Shaxsiy Kabinetingiz:*\n\n🆔 ID: `{message.from_user.id}`\n💰 Balans: *{balance} so'm*", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "user_deposit")
async def user_deposit_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("📥 To'ldirmoqchi bo'lgan miqdorni kiriting (masalan: 20000):")
    await state.set_state(UserStates.deposit_amount)

@dp.message(UserStates.deposit_amount)
async def user_deposit_amount_get(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        await state.update_data(dep_amount=amount)
        
        cursor.execute("SELECT value FROM settings WHERE key='card'")
        card = cursor.fetchone()[0]
        
        pay_text = f"💳 *To'lov tizimi*\n\n" \
                   f"💰 To'lov miqdori: *{amount} so'm*\n" \
                   f"💳 Karta raqami: `{card}`\n\n" \
                   f"To'lovni amalga oshiring va *chek skrinshotini* shu yerga yuboring:"
        await message.answer(pay_text, parse_mode="Markdown")
        await state.set_state(UserStates.deposit_check)
    except ValueError:
        await message.answer("⚠️ Iltimos, faqat raqam kiriting (masalan: 50000):")

@dp.message(UserStates.deposit_check, F.photo)
async def user_deposit_check_get(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id
    
    cursor.execute("INSERT INTO deposits (user_id, amount, photo_id, status) VALUES (?, ?, ?, 'Kutilmoqda')",
                   (message.from_user.id, data['dep_amount'], photo_id))
    conn.commit()
    dep_id = cursor.lastrowid
    
    await message.answer("⏳ Rahmat! Chekingiz adminga yuborildi. Tasdiqlangandan so'ng balansingiz to'ldiriladi.")
    await state.clear()
    
    # Adminga xabar berish
    try:
        await bot.send_message(ADMIN_ID, f"🔔 *Yangi to'lov kutilmoqda #{dep_id}*\nFoydalanuvchi: {message.from_user.id}\nMiqdor: {data['dep_amount']} so'm\nTasdiqlash uchun Admin Paneldagi 'To'lovlar bo'limi'ga kiring.")
    except: pass

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
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{amount} ta - {price} so'm", callback_data=f"buy_{amount}_{price}")])
        
    await message.answer(f"✨ {text} bo'limi. Miqdorni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_"))
async def user_buy_select(call: types.CallbackQuery, state: FSMContext):
    _, amount, price = call.data.split("_")
    price = float(price)
    amount = int(amount)
    
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,))
    balance = cursor.fetchone()[0]
    
    if balance < price:
        await call.answer("❌ Balansingizda mablag' yetarli emas! Iltimos, shaxsiy kabinet orqali balansni to'ldiring.", show_alert=True)
        return
        
    await state.update_data(user_amount=amount, user_price=price)
    await call.message.answer("🔗 Instagram profilingiz yoki postingiz havolasini (linkini) yuboring:")
    await state.set_state(UserStates.get_link)

@dp.message(UserStates.get_link)
async def user_link_get(message: types.Message, state: FSMContext):
    if not message.text.startswith(("http://", "https://")):
        await message.answer("⚠️ Iltimos, to'g'ri havola yuboring (masalan: https://instagram.com/...)")
        return
        
    data = await state.get_data()
    price = data['user_price']
    
    # Balansni qayta tekshirish xavfsizlik uchun
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (message.from_user.id,))
    balance = cursor.fetchone()[0]
    
    if balance < price:
        await message.answer("❌ Balansingizda mablag' yetarli emas!")
        await state.clear()
        return
        
    # Balansdan pulni ayirish va buyurtmani bazaga yozish
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, message.from_user.id))
    cursor.execute("INSERT INTO orders (user_id, service, amount, link) VALUES (?, ?, ?, ?)",
                   (message.from_user.id, data['user_service'], data['user_amount'], message.text))
    conn.commit()
    
    await message.answer(f"✅ Buyurtma qabul qilindi!\n📦 {data['user_amount']} ta {data['user_service']} uchun balansingizdan {price} so'm yechildi.\nTez orada nakrutka boshlanadi!")
    
    # Adminga xabar yuborish
    try:
        await bot.send_message(ADMIN_ID, f"🚀 *Yangi Nakrutka Buyurtmasi!*\n\n👤 Kimdan: {message.from_user.id}\n📦 Xizmat: {data['user_amount']} ta {data['user_service']}\n🔗 Link: {message.text}")
    except: pass
    
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

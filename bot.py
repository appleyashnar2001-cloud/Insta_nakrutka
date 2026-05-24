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

# Jadvallarni yaratish va yangilash
cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INT PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, service TEXT, amount INT, link TEXT, status TEXT DEFAULT 'Kutilmoqda')''')
cursor.execute('''CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, amount REAL, photo_id TEXT, status TEXT)''')
conn.commit()

# Standart sozlamalarga dastlabki karta raqamini kiritish
cursor.execute("INSERT OR IGNORE INTO settings VALUES ('card', '8600000000000000')")
conn.commit()

# Narxlar matritsasi (Obunachi va Kommentariya uchun asosiy narxlar)
AMOUNTS = [100, 500, 1000, 5000, 10000, 15000, 50000, 100000]
BASE_PRICES = {
    100: 2000.0,
    500: 5000.0,
    1000: 9000.0,
    5000: 25000.0,
    10000: 40000.0,
    15000: 55000.0,
    50000: 130000.0,
    100000: 210000.0
}

def calculate_price(service, amount):
    base = BASE_PRICES.get(amount, 10000.0)
    if service in ['obunachi', 'komentariya']:
        return base
    elif service == 'layk':
        return base / 2  # Yarim narx
    elif service == 'korish':
        return round(base / 3, 2)  # 3/1 narx
    return base

# FSM (Holatlar)
class AdminStates(StatesGroup):
    set_card = State()

class UserStates(StatesGroup):
    deposit_amount = State()
    deposit_check = State()
    get_link = State()

# --- KLAVIATURALAR ---
def main_menu(user_id):
    kb = [
        [KeyboardButton(text="👤 Shaxsiy Kabinet / Balans"), KeyboardButton(text="📦 Mening buyurtmalarim")],
        [KeyboardButton(text="👤 Obunachi qo'shish"), KeyboardButton(text="❤️ Layk ko'paytirish")],
        [KeyboardButton(text="👁 Ko'rishlarni ko'paytirish"), KeyboardButton(text="💬 Kommentariyalar")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="⚙️ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def cancel_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Karta raqamni o'zgartirish", callback_data="admin_card")],
        [InlineKeyboardButton(text="📥 To'lovlar bo'limi", callback_data="admin_deposits_menu")],
        [InlineKeyboardButton(text="📦 Buyurtmalar boshqaruvi", callback_data="admin_orders_menu")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")]
    ])

# --- GLOBAL GLOBAL GLOBAL BEKOR QILISH HANDLERI ---
@dp.message(F.text == "❌ Bekor qilish")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
    await message.answer("❌ Jarayon bekor qilindi. Asosiy menyuga qaytdingiz.", reply_markup=main_menu(message.from_user.id))

# --- ADMIN HANDLERS ---
@dp.message(F.text == "⚙️ Admin Panel")
async def open_admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("⚙️ *Admin panelga xush kelibsiz!*", reply_markup=admin_menu(), parse_mode="Markdown")

@dp.callback_query(F.data == "admin_card")
async def admin_card_edit(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT value FROM settings WHERE key='card'")
    current_card = cursor.fetchone()[0]
    await call.message.answer(f"Hozirgi karta: `{current_card}`\nYangi karta raqamini yuboring:", reply_markup=cancel_menu(), parse_mode="Markdown")
    await state.set_state(AdminStates.set_card)

@dp.message(AdminStates.set_card)
async def save_card(message: types.Message, state: FSMContext):
    cursor.execute("UPDATE settings SET value=? WHERE key='card'", (message.text,))
    conn.commit()
    await message.answer("✅ Karta raqami yangilandi!", reply_markup=main_menu(ADMIN_ID))
    await state.clear()

# To'lovlar (Deposits) boshqaruvi
@dp.callback_query(F.data == "admin_deposits_menu")
async def admin_deposits_menu(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Kutilayotgan to'lovlar", callback_data="dep_status_Kutilmoqda")],
        [InlineKeyboardButton(text="✅ Tasdiqlangan to'lovlar", callback_data="dep_status_Tasdiqlandi")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin")]
    ])
    await call.message.edit_text("📥 *To'lovlar bo'limi:*", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(call: types.CallbackQuery):
    await call.message.edit_text("⚙️ *Admin panelga xush kelibsiz!*", reply_markup=admin_menu(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("dep_status_"))
async def show_deposits(call: types.CallbackQuery):
    status = call.data.split("_")[2]
    cursor.execute("SELECT id, user_id, amount FROM deposits WHERE status=?", (status,))
    deps = cursor.fetchall()
    if not deps:
        await call.answer("Bu bo'limda to'lovlar mavjud emas.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for dep_id, u_id, amount in deps:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"ID: {dep_id} | Foydalanuvchi: {u_id} | {amount} so'm", callback_data=f"view_dep_{dep_id}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_deposits_menu")])
    await call.message.edit_text(f"📥 *{status}* to'lovlar ro'yxati:", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("view_dep_"))
async def view_deposit(call: types.CallbackQuery):
    dep_id = call.data.split("_")[2]
    cursor.execute("SELECT user_id, amount, photo_id, status FROM deposits WHERE id=?", (dep_id,))
    dep = cursor.fetchone()
    if dep:
        user_id, amount, photo_id, status = dep
        caption = f"💵 *To'lov #{dep_id}*\n\n👤 Foydalanuvchi ID: `{user_id}`\n💰 Miqdor: *{amount} so'm*\n📊 Holati: *{status}*"
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        if status == "Kutilmoqda":
            kb.inline_keyboard.append([
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"app_dep_{dep_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_dep_{dep_id}")
            ])
        kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"dep_status_{status}")])
        await call.message.delete()
        await bot.send_photo(ADMIN_ID, photo=photo_id, caption=caption, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("app_dep_"))
async def app_dep(call: types.CallbackQuery):
    dep_id = call.data.split("_")[2]
    cursor.execute("SELECT user_id, amount, status FROM deposits WHERE id=?", (dep_id,))
    dep = cursor.fetchone()
    if dep and dep[2] == "Kutilmoqda":
        user_id, amount, _ = dep
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        cursor.execute("UPDATE deposits SET status = 'Tasdiqlandi' WHERE id = ?", (dep_id,))
        conn.commit()
        await call.message.edit_caption(caption=f"✅ To'lov #{dep_id} tasdiqlandi!")
        try: await bot.send_message(user_id, f"🎉 To'lovingiz tasdiqlandi! Balansingizga *{amount} so'm* qo'shildi.")
        except: pass

@dp.callback_query(F.data.startswith("rej_dep_"))
async def reject_dep(call: types.CallbackQuery):
    dep_id = call.data.split("_")[2]
    cursor.execute("SELECT user_id, status FROM deposits WHERE id=?", (dep_id,))
    dep = cursor.fetchone()
    if dep and dep[1] == "Kutilmoqda":
        user_id = dep[0]
        cursor.execute("UPDATE deposits SET status = 'Rad etildi' WHERE id = ?", (dep_id,))
        conn.commit()
        await call.message.edit_caption(caption=f"❌ To'lov #{dep_id} rad etildi.")
        try: await bot.send_message(user_id, f"❌ Siz yuborgan chek #{dep_id} rad etildi.")
        except: pass

# Nakrutka Buyurtmalari (Orders) boshqaruvi
@dp.callback_query(F.data == "admin_orders_menu")
async def admin_orders_menu(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Kutilayotgan buyurtmalar", callback_data="ord_status_Kutilmoqda")],
        [InlineKeyboardButton(text="🔄 Bajarilayotganlar", callback_data="ord_status_Bajarilmoqda")],
        [InlineKeyboardButton(text="✅ Tugallanganlar", callback_data="ord_status_Tugallangan")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin")]
    ])
    await call.message.edit_text("📦 *Buyurtmalar boshqaruv bo'limi:*", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("ord_status_"))
async def show_orders_admin(call: types.CallbackQuery):
    status = call.data.split("_")[2]
    cursor.execute("SELECT id, user_id, service, amount FROM orders WHERE status=?", (status,))
    ords = cursor.fetchall()
    if not ords:
        await call.answer("Ushbu bo'limda buyurtmalar yo'q.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for o_id, u_id, svc, amt in ords:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"#{o_id} | {svc} | {amt} ta", callback_data=f"view_ord_{o_id}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_orders_menu")])
    await call.message.edit_text(f"📦 *{status}* holatidagi buyurtmalar:", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("view_ord_"))
async def view_order_admin(call: types.CallbackQuery):
    o_id = call.data.split("_")[2]
    cursor.execute("SELECT user_id, service, amount, link, status FROM orders WHERE id=?", (o_id,))
    ord_info = cursor.fetchone()
    if ord_info:
        user_id, service, amount, link, status = ord_info
        text = f"📦 *Buyurtma #{o_id}*\n\n👤 Foydalanuvchi: `{user_id}`\n🛠 Xizmat: *{service}*\n🔢 Miqdor: *{amount} ta*\n🔗 Havola: {link}\n📊 Holat: *{status}*"
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        if status == "Kutilmoqda":
            kb.inline_keyboard.append([InlineKeyboardButton(text="🔄 Bajarishni boshlash", callback_data=f"set_ord_Bajarilmoqda_{o_id}")])
        if status == "Bajarilmoqda":
            kb.inline_keyboard.append([InlineKeyboardButton(text="✅ Tugatish", callback_data=f"set_ord_Tugallangan_{o_id}")])
        kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"ord_status_{status}")])
        await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("set_ord_"))
async def change_order_status(call: types.CallbackQuery):
    _, _, new_status, o_id = call.data.split("_")
    cursor.execute("SELECT user_id, service, amount FROM orders WHERE id=?", (o_id,))
    u_id, svc, amt = cursor.fetchone()
    cursor.execute("UPDATE orders SET status=? WHERE id=?", (new_status, o_id))
    conn.commit()
    await call.message.edit_text(f"✅ Buyurtma #{o_id} holati *{new_status}* ga o'zgartirildi!", parse_mode="Markdown")
    try: await bot.send_message(u_id, f"📦 Sizning #{o_id} raqamli buyurtmangiz (*{amt} ta {svc}*) holati o'zgardi:\n📊 Yangi holat: *{new_status}*", parse_mode="Markdown")
    except: pass

@dp.callback_query(F.data == "admin_stats")
async def show_stats(call: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM users")
    u_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status='Tugallangan'")
    o_count = cursor.fetchone()[0]
    await call.message.answer(f"📊 *Bot statistikasi:*\n\n👥 Jami foydalanuvchilar: {u_count} ta\n✅ Muwaffaqiyatli tugallangan buyurtmalar: {o_count} ta", parse_mode="Markdown")


# --- USER HANDLERS ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (message.from_user.id, message.from_user.username))
    conn.commit()
    await message.answer("✨ Xush kelibsiz! Instagram xizmatlaridan foydalanish uchun quyidagi bo'limlardan birini tanlang:", reply_markup=main_menu(message.from_user.id))

@dp.message(F.text == "👤 Shaxsiy Kabinet / Balans")
async def user_cabinet(message: types.Message):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (message.from_user.id,))
    balance = cursor.fetchone()[0]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Balansni to'ldirish", callback_data="user_deposit")]])
    await message.answer(f"👤 *Sizning Shaxsiy Kabinetingiz:*\n\n🆔 ID: `{message.from_user.id}`\n💰 Balans: *{balance} so'm*", reply_markup=kb, parse_mode="Markdown")

@dp.message(F.text == "📦 Mening buyurtmalarim")
async def user_orders(message: types.Message):
    cursor.execute("SELECT id, service, amount, status FROM orders WHERE user_id=? ORDER BY id DESC", (message.from_user.id,))
    my_ords = cursor.fetchall()
    if not my_ords:
        await message.answer("ℹ️ Sizda hali hech qanday buyurtmalar maintuzilmagan.")
        return
    text = "📦 *Sizning buyurtmalaringiz ro'yxati:*\n\n"
    for o_id, svc, amt, status in my_ords:
        emoji = "⏳" if status == "Kutilmoqda" else ("🔄" if status == "Bajarilmoqda" else "✅")
        text += f"{emoji} *Buyurtma #{o_id}*\n🛠 Xizmat: {svc.capitalize()}\n🔢 Miqdor: {amt} ta\n📊 Holat: *{status}*\n\n"
    await message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data == "user_deposit")
async def user_deposit_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("📥 To'ldirmoqchi bo'lgan miqdorni kiriting (so'mda):\n\n*(Jarayonni to'xtatish uchun pastdagi tugmani bosing)*", reply_markup=cancel_menu())
    await state.set_state(UserStates.deposit_amount)

@dp.message(UserStates.deposit_amount)
async def user_deposit_amount_get(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        await state.update_data(dep_amount=amount)
        cursor.execute("SELECT value FROM settings WHERE key='card'")
        card = cursor.fetchone()[0]
        pay_text = f"💳 *To'lov tizimi*\n\n💰 To'lov miqdori: *{amount} so'm*\n💳 Karta raqami: `{card}`\n\nTo'lovni amalga oshiring va *chek skrinshotini* shu yerga yuboring:"
        await message.answer(pay_text, reply_markup=cancel_menu(), parse_mode="Markdown")
        await state.set_state(UserStates.deposit_check)
    except ValueError:
        await message.answer("⚠️ Iltimos, faqat raqam kiriting:")

@dp.message(UserStates.deposit_check, F.photo)
async def user_deposit_check_get(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id
    cursor.execute("INSERT INTO deposits (user_id, amount, photo_id, status) VALUES (?, ?, ?, 'Kutilmoqda')", (message.from_user.id, data['dep_amount'], photo_id))
    conn.commit()
    dep_id = cursor.lastrowid
    await message.answer("⏳ Rahmat! Chekingiz adminga yuborildi. Tasdiqlangandan so'ng balansingiz to'ldiriladi.", reply_markup=main_menu(message.from_user.id))
    await state.clear()
    try: await bot.send_message(ADMIN_ID, f"🔔 *Yangi to'lov kutilmoqda #{dep_id}*\nFoydalanuvchi: {message.from_user.id}\nMiqdor: {data['dep_amount']} so'm\nTasdiqlash uchun Admin Paneldagi 'To'lovlar bo'limi'ga kiring.")
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
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for amt in AMOUNTS:
        price = calculate_price(service, amt)
        label = f"{amt} ta" if amt < 1000 else f"{amt//1000}k"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{label} - {int(price)} so'm", callback_data=f"buy_{service}_{amt}")])
        
    await message.answer(f"✨ {text} bo'limi. Miqdorni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_"))
async def user_buy_select(call: types.CallbackQuery, state: FSMContext):
    _, service, amount = call.data.split("_")
    amount = int(amount)
    price = calculate_price(service, amount)
    
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,))
    balance = cursor.fetchone()[0]
    
    if balance < price:
        await call.answer("❌ Balansingizda mablag' yetarli emas! Iltimos, balansni to'ldiring.", show_alert=True)
        return
        
    await state.update_data(user_amount=amount, user_price=price)
    await call.message.answer("🔗 Instagram profilingiz yoki postingiz havolasini (linkini) yuboring:", reply_markup=cancel_menu())
    await state.set_state(UserStates.get_link)

@dp.message(UserStates.get_link)
async def user_link_get(message: types.Message, state: FSMContext):
    if not message.text.startswith(("http://", "https://")):
        await message.answer("⚠️ Iltimos, to'g'ri havola yuboring (https://...)")
        return
        
    data = await state.get_data()
    price = data['user_price']
    
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (message.from_user.id,))
    balance = cursor.fetchone()[0]
    if balance < price:
        await message.answer("❌ Balansingizda mablag' yetarli emas!", reply_markup=main_menu(message.from_user.id))
        await state.clear()
        return
        
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, message.from_user.id))
    cursor.execute("INSERT INTO orders (user_id, service, amount, link, status) VALUES (?, ?, ?, ?, 'Kutilmoqda')",
                   (message.from_user.id, data['user_service'], data['user_amount'], message.text))
    conn.commit()
    o_id = cursor.lastrowid
    
    await message.answer(f"✅ Buyurtma qabul qilindi! (Buyurtma ID: #{o_id})\n📦 {data['user_amount']} ta {data['user_service']} uchun balansingizdan {int(price)} so'm yechildi.\n\nJarayonni 'Mening buyurtmalarim' bo'limidan kuzatib borishingiz mumkin.", reply_markup=main_menu(message.from_user.id))
    try: await bot.send_message(ADMIN_ID, f"🚀 *Yangi Nakrutka Buyurtmasi #{o_id}!*\n\n👤 Kimdan: {message.from_user.id}\n📦 Xizmat: {data['user_amount']} ta {data['user_service']}\n🔗 Link: {message.text}")
    except: pass
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

# bot.py — Напоминалка с повторами и удалением (с отладкой для Render)

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import aiofiles
import json
import os
from datetime import datetime, timedelta
import random

# === НАСТРОЙКИ ===
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ Не установлен BOT_TOKEN")

# === СОЗДАНИЕ БОТА И ДИСПЕТЧЕРА ===
bot = Bot(token=TOKEN)
dp = Dispatcher()

# === КНОПКИ ===
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Новое напоминание")],
            [KeyboardButton(text="📋 Мои напоминания")],
        ],
        resize_keyboard=True
    )

# Типы повторов
REPEAT_TYPES = {
    "daily": "🔁 Ежедневно",
    "weekly": "📅 Еженедельно",
    "monthly": "🗓️ Ежемесячно",
    "none": "🚫 Без повтора"
}

# === ХРАНЕНИЕ ===
REMIND_FILE = "reminders.json"
reminders = []  # [{user_id, message, time, repeat}]
user_state = {}  # {user_id: {step, data}}

# === ЗАГРУЗКА / СОХРАНЕНИЕ ===
async def load_reminders():
    global reminders
    print("🔧 Попытка загрузить напоминания...")
    if os.path.exists(REMIND_FILE):
        try:
            async with aiofiles.open(REMIND_FILE, "r", encoding="utf-8") as f:
                content = await f.read()
                reminders = json.loads(content)
            print(f"✅ Загружено {len(reminders)} напоминаний")
        except Exception as e:
            print(f"❌ Ошибка загрузки: {e}")
            reminders = []
    else:
        print("📝 Файл напоминаний не найден — начнём с пустого списка")
        reminders = []

async def save_reminders():
    print(f"💾 Сохраняем {len(reminders)} напоминаний...")
    try:
        async with aiofiles.open(REMIND_FILE, "w", encoding="utf-8") as f:
            await f.write(json.dumps(reminders, ensure_ascii=False, indent=2))
        print("✅ Напоминания сохранены")
    except Exception as e:
        print(f"❌ Не удалось сохранить: {e}")

# === /start ===
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    user_state[user_id] = None
    print(f"👤 Пользователь {user_id} запустил бота")
    await message.answer(
        "👋 Привет! Я бот-напоминалка с повторами и удалением.",
        reply_markup=get_main_keyboard()
    )

# === КНОПКИ МЕНЮ ===
@dp.message(lambda m: m.text == "➕ Новое напоминание")
async def start_remind(message: types.Message):
    user_id = message.from_user.id
    user_state[user_id] = {"step": "waiting_message"}
    print(f"📝 Пользователь {user_id} начал создание напоминания")
    await message.answer("📝 Введи сообщение для напоминания:")

@dp.message(lambda m: m.text == "📋 Мои напоминания")
async def show_reminders(message: types.Message):
    user_id = message.from_user.id
    user_rems = [r for r in reminders if r["user_id"] == user_id]

    if not user_rems:
        await message.answer("📌 У тебя нет активных напоминаний.")
        return

    # Создаём список с кнопками удаления
    for i, r in enumerate(user_rems):
        time_str = datetime.fromisoformat(r["time"]).strftime("%d.%m %H:%M")
        repeat_text = REPEAT_TYPES.get(r.get("repeat", "none"), "Без повтора")

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete_{i}")]
        ])

        await message.answer(
            f"🔔 Напоминание #{i+1}\n"
            f"💬 {r['message']}\n"
            f"⏰ {time_str}\n"
            f"🔄 {repeat_text}",
            reply_markup=kb
        )

# === УДАЛЕНИЕ ЧЕРЕЗ КНОПКУ ===
@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def delete_reminder(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_rems = [r for r in reminders if r["user_id"] == user_id]
    index = int(callback.data.split("_")[1])

    if 0 <= index < len(user_rems):
        removed = user_rems[index]
        reminders.remove(removed)
        await save_reminders()
        print(f"🗑️ Напоминание удалено: {removed['message']}")
        await callback.answer("✅ Напоминание удалено!")
        await callback.message.edit_text("❌ Это напоминание удалено.")
    else:
        await callback.answer("❌ Уже удалено.")

# === ОБРАБОТКА СООБЩЕНИЯ ===
@dp.message(lambda m: user_state.get(m.from_user.id, {}).get("step") == "waiting_message")
async def get_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    if not text:
        await message.answer("❌ Сообщение не может быть пустым.")
        return

    user_state[user_id] = {"step": "waiting_time", "message": text}
    print(f"⏳ Пользователь {user_id} ввёл сообщение: {text}")
    await message.answer("⏰ Введи время (чч:мм), например: 15:30")

# === ОБРАБОТКА ВРЕМЕНИ ===
@dp.message(lambda m: user_state.get(m.from_user.id, {}).get("step") == "waiting_time")
async def get_time(message: types.Message):
    user_id = message.from_user.id
    time_input = message.text.strip()
    try:
        hours, minutes = map(int, time_input.split(":"))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError

        now = datetime.now()
        remind_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        if remind_time < now:
            remind_time += timedelta(days=1)

        user_state[user_id]["step"] = "waiting_repeat"
        user_state[user_id]["time"] = remind_time.isoformat()

        # Кнопки выбора повтора
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=REPEAT_TYPES["none"], callback_data="repeat_none")],
            [InlineKeyboardButton(text=REPEAT_TYPES["daily"], callback_data="repeat_daily")],
            [InlineKeyboardButton(text=REPEAT_TYPES["weekly"], callback_data="repeat_weekly")],
            [InlineKeyboardButton(text=REPEAT_TYPES["monthly"], callback_data="repeat_monthly")]
        ])
        await message.answer("🔁 Выбери, как часто повторять:", reply_markup=kb)

    except Exception:
        await message.answer("❌ Неверный формат. Введи чч:мм (например, 09:00)")

# === ВЫБОР ПОВТОРА ===
@dp.callback_query(lambda c: c.data.startswith("repeat_"))
async def set_repeat(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = user_state.get(user_id)
    if not data or data["step"] != "waiting_repeat":
        await callback.answer("❌ Сессия устарела.")
        return

    repeat_key = callback.data.replace("repeat_", "")
    reminder = {
        "user_id": user_id,
        "message": data["message"],
        "time": data["time"],
        "repeat": repeat_key  # none, daily, weekly, monthly
    }
    reminders.append(reminder)
    await save_reminders()

    time_str = datetime.fromisoformat(data["time"]).strftime("%d.%m %H:%M")
    repeat_text = REPEAT_TYPES.get(repeat_key, "Без повтора")

    await callback.message.edit_text(
        f"✅ Напоминание добавлено!\n"
        f"💬 {reminder['message']}\n"
        f"⏰ {time_str}\n"
        f"🔄 {repeat_text}"
    )
    user_state[user_id] = None
    print(f"✅ Напоминание добавлено: {reminder['message']} — {time_str}")
    await callback.answer()

# === ФОН: ПРОВЕРКА И ПОВТОРЫ ===
async def check_reminders():
    print("⏱️ Запущена фоновая проверка напоминаний (каждые 10 сек)")
    while True:
        now = datetime.now()
        due_reminders = [r for r in reminders if datetime.fromisoformat(r["time"]) <= now]

        for r in due_reminders:
            try:
                await bot.send_message(r["user_id"], f"🔔 Напоминание:\n{r['message']}")
                print(f"📨 Отправлено: {r['message']} (пользователю {r['user_id']})")
            except Exception as e:
                print(f"❌ Ошибка отправки: {e}")
                reminders.remove(r)
                await save_reminders()
                continue

            # Удаляем старое
            reminders.remove(r)

            # Если нужен повтор — создаём новое
            repeat = r.get("repeat", "none")
            new_time = None

            if repeat == "daily":
                new_time = now + timedelta(days=1)
            elif repeat == "weekly":
                new_time = now + timedelta(weeks=1)
            elif repeat == "monthly":
                new_time = now + timedelta(days=30)

            if new_time:
                new_rem = r.copy()
                new_rem["time"] = new_time.replace(hour=new_time.hour, minute=new_time.minute).isoformat()
                reminders.append(new_rem)
                print(f"🔁 Повтор создан: {new_rem['message']} — {new_rem['time']}")

        if due_reminders:
            await save_reminders()

        await asyncio.sleep(10)

# === МИНИ-СЕРВЕР ДЛЯ RENDER (чтобы не падало по SIGTERM) ===
from aiohttp import web

app = web.Application()
app.router.add_get("/", lambda _: web.Response(text="OK", status=200))
app.router.add_get("/health", lambda _: web.Response(text="OK", status=200))

# === ЗАПУСК ===
async def main():
    print("🚀 Запуск бота...")
    print("🔧 Шаг 1: Загрузка напоминаний...")
    await load_reminders()

    print("🔧 Шаг 2: Запуск фоновой проверки...")
    asyncio.create_task(check_reminders())

    print("🔧 Шаг 3: Запуск веб-сервера для Render...")
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Веб-сервер запущен на порту {port}")

    print("🚀 Шаг 4: Запуск polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
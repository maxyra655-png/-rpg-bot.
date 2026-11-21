import asyncio
import json
import logging
import os
import random
import time
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATA_FILE = "crmp_bot_data.json"

SHIFT_COOLDOWN = 45   # секунд между сменами
CRIME_COOLDOWN = 60   # секунд между криминальными делами

LOCATIONS = {
    "spalnik": "🏘 Спальный район",
    "center": "🏛 Центр города",
    "market": "🚗 Авторынок",
    "promzona": "🏭 Промзона",
}

JOBS = {
    "none": {"name": "Безработный", "pay": (40, 80), "min_lvl": 1},
    "courier": {"name": "📦 Курьер доставки", "pay": (90, 150), "min_lvl": 1},
    "trucker": {"name": "🚛 Дальнобойщик", "pay": (180, 290), "min_lvl": 2},
    "mechanic": {"name": "🔧 Автомеханик", "pay": (150, 240), "min_lvl": 2},
    "dps": {"name": "🚓 Инспектор ДПС", "pay": (240, 380), "min_lvl": 3},
    "mchs": {"name": "🚒 Спасатель МЧС", "pay": (220, 350), "min_lvl": 3},
}

CARS = {
    "none": {"name": "Пешком", "price": 0, "escape_bonus": 0},
    "vaz2107": {"name": "🚗 ВАЗ-2107", "price": 500, "escape_bonus": 5},
    "priora": {"name": "🚘 Lada Priora", "price": 1500, "escape_bonus": 12},
    "camry": {"name": "🚙 Toyota Camry 3.5", "price": 4500, "escape_bonus": 22},
    "bmw_m5": {"name": "🏎 BMW M5 F90", "price": 12000, "escape_bonus": 35},
    "gelik": {"name": "🖤 Mercedes G63", "price": 25000, "escape_bonus": 45},
}


def load_data() -> dict[str, dict]:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
            return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def save_data(data: dict[str, dict]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


players: dict[str, dict] = load_data()


def get_player(uid: int, name: str = "") -> dict:
    key = str(uid)
    if key not in players:
        players[key] = {
            "id": uid,
            "name": name or f"Игрок_{uid}",
            "money": 500,
            "lvl": 1,
            "xp": 0,
            "wanted": 0,
            "job": "none",
            "car": "none",
            "location": "spalnik",
            "last_shift": 0.0,
            "last_crime": 0.0,
        }
        save_data(players)
    else:
        players[key]["id"] = uid
        if name:
            players[key]["name"] = name
    return players[key]


def add_xp(player: dict, amount: int) -> bool:
    player["xp"] += amount
    leveled_up = False
    while player["xp"] >= player["lvl"] * 100:
        player["xp"] -= player["lvl"] * 100
        player["lvl"] += 1
        leveled_up = True
    return leveled_up


def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🪪 Паспорт", callback_data="p_profile"),
                InlineKeyboardButton(text="🗺 Районы", callback_data="p_map"),
            ],
            [
                InlineKeyboardButton(text="💼 Работа / Смена", callback_data="p_work"),
                InlineKeyboardButton(text="🔫 Криминал", callback_data="p_crime"),
            ],
            [
                InlineKeyboardButton(text="🚗 Авторынок", callback_data="p_cars"),
                InlineKeyboardButton(text="🏆 Топ игроков", callback_data="p_top"),
            ],
        ]
    )


def format_passport(p: dict) -> str:
    job_name = JOBS.get(p["job"], JOBS["none"])["name"]
    car_name = CARS.get(p["car"], CARS["none"])["name"]
    loc_name = LOCATIONS.get(p["location"], LOCATIONS["spalnik"])
    stars = "⭐" * p["wanted"] if p["wanted"] > 0 else "Чист"
    need_xp = p["lvl"] * 100
    return (
        f"🪪 **Паспорт гражданина: {p['name']}**\n"
        f"🆔 ID: `{p['id']}`\n\n"
        f"💵 Наличные: **{p['money']} ₽**\n"
        f"🎖 Уровень: **{p['lvl']}** (`{p['xp']}/{need_xp} XP`)\n"
        f"💼 Работа: **{job_name}**\n"
        f"🚘 Транспорт: **{car_name}**\n"
        f"📍 Локация: **{loc_name}**\n"
        f"🚨 Розыск: **{stars}**"
    )


dp = Dispatcher()


@dp.message(CommandStart())
@dp.message(Command("menu"))
async def cmd_start(message: Message):
    p = get_player(message.from_user.id, message.from_user.full_name)
    await message.answer(
        "🏙 **Добро пожаловать в CRMP-проект!**\n"
        "Перевод денег другому игроку: `/pay ID сумма`\n\n"
        + format_passport(p),
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )


@dp.message(Command("pay"))
async def cmd_pay(message: Message):
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Использование: `/pay <ID_игрока> <сумма>`", parse_mode="Markdown")
        return

    try:
        target_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("ID и сумма должны быть целыми числами.")
        return

    if amount <= 0:
        await message.answer("Сумма перевода должна быть больше нуля.")
        return

    sender = get_player(message.from_user.id, message.from_user.full_name)
    if sender["id"] == target_id:
        await message.answer("Нельзя перевести деньги самому себе.")
        return

    if str(target_id) not in players:
        await message.answer("Игрок с таким ID ещё не заходил в бота.")
        return

    if sender["money"] < amount:
        await message.answer(f"Недостаточно средств. У тебя на руках: **{sender['money']} ₽**", parse_mode="Markdown")
        return

    receiver = get_player(target_id)
    sender["money"] -= amount
    receiver["money"] += amount
    save_data(players)

    await message.answer(
        f"💸 Ты перевёл **{amount} ₽** игроку **{receiver['name']}** (`{target_id}`).",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )


@dp.callback_query(F.data == "p_profile")
async def cb_profile(callback: CallbackQuery):
    p = get_player(callback.from_user.id, callback.from_user.full_name)
    await callback.message.answer(format_passport(p), reply_markup=main_kb(), parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "p_map")
async def cb_map(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"go:{loc_id}")]
            for loc_id, title in LOCATIONS.items()
        ]
        + [[InlineKeyboardButton(text="⬅️ Назад", callback_data="p_profile")]]
    )
    await callback.message.answer("🗺 **Выбери район для поездки:**", reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data.startswith("go:"))
async def cb_go(callback: CallbackQuery):
    loc_id = callback.data.split(":", 1)[1]
    if loc_id not in LOCATIONS:
        await callback.answer("Неизвестный район", show_alert=True)
        return
    p = get_player(callback.from_user.id, callback.from_user.full_name)
    p["location"] = loc_id
    save_data(players)
    await callback.message.answer(
        f"🚕 Ты приехал в район: **{LOCATIONS[loc_id]}**",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "p_work")
async def cb_work(callback: CallbackQuery):
    p = get_player(callback.from_user.id, callback.from_user.full_name)
    rows = [[InlineKeyboardButton(text="💵 Отработать смену", callback_data="do_shift")]]
    for j_id, info in JOBS.items():
        if j_id == "none":
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{info['name']} (от {info['min_lvl']} ур.)",
                    callback_data=f"setjob:{j_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="p_profile")])
    await callback.message.answer(
        f"💼 **Биржа труда**\nТекущая должность: **{JOBS[p['job']]['name']}**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("setjob:"))
async def cb_setjob(callback: CallbackQuery):
    j_id = callback.data.split(":", 1)[1]
    info = JOBS.get(j_id)
    if not info:
        await callback.answer("Должность не найдена", show_alert=True)
        return
    p = get_player(callback.from_user.id, callback.from_user.full_name)
    if p["lvl"] < info["min_lvl"]:
        await callback.answer(f"Нужен {info['min_lvl']} уровень!", show_alert=True)
        return
    if p["wanted"] > 0 and j_id in ("dps", "mchs"):
        await callback.answer("С розыском в госструктуры не берут!", show_alert=True)
        return
    p["job"] = j_id
    save_data(players)
    await callback.message.answer(
        f"✅ Ты устроился на должность: **{info['name']}**!",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "do_shift")
async def cb_do_shift(callback: CallbackQuery):
    p = get_player(callback.from_user.id, callback.from_user.full_name)
    now = time.time()
    rem = int(SHIFT_COOLDOWN - (now - p["last_shift"]))
    if rem > 0:
        await callback.answer(f"⏳ Отдохни перед следующей сменой ещё {rem} сек.", show_alert=True)
        return

    job = JOBS.get(p["job"], JOBS["none"])
    pay = random.randint(*job["pay"])
    xp_gain = random.randint(20, 35)
    p["last_shift"] = now
    p["money"] += pay
    lvl_up = add_xp(p, xp_gain)
    save_data(players)

    extra = f"\n🎉 **Новый уровень: {p['lvl']}!**" if lvl_up else ""
    await callback.message.answer(
        f"💼 Смена окончена (**{job['name']}**)\n"
        f"💵 Зарплата: **+{pay} ₽**\n"
        f"✨ Опыт: **+{xp_gain} XP**{extra}",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "p_crime")
async def cb_crime(callback: CallbackQuery):
    p = get_player(callback.from_user.id, callback.from_user.full_name)
    bribe_cost = max(200, p["wanted"] * 250)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🦹 Пойти на дело", callback_data="do_crime")],
            [InlineKeyboardButton(text=f"🕵️ Снять розыск ({bribe_cost} ₽)", callback_data="clear_wanted")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="p_profile")],
        ]
    )
    await callback.message.answer(
        "🔫 **Теневой сектор**\n"
        "Чем лучше тачка — тем выше шанс уйти от патруля.",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "do_crime")
async def cb_do_crime(callback: CallbackQuery):
    p = get_player(callback.from_user.id, callback.from_user.full_name)
    now = time.time()
    rem = int(CRIME_COOLDOWN - (now - p["last_crime"]))
    if rem > 0:
        await callback.answer(f"⏳ Подожди ещё {rem} сек. перед новым делом.", show_alert=True)
        return

    p["last_crime"] = now
    escape_bonus = CARS.get(p["car"], CARS["none"])["escape_bonus"]
    chance = min(90, 45 + escape_bonus)

    if random.randint(1, 100) <= chance:
        loot = random.randint(250, 600)
        xp_gain = 30
        p["money"] += loot
        lvl_up = add_xp(p, xp_gain)
        save_data(players)
        extra = f"\n🎉 **Новый уровень: {p['lvl']}!**" if lvl_up else ""
        await callback.message.answer(
            f"🔥 **Дело прошло чисто!**\n"
            f"💰 Куш: **+{loot} ₽** | ✨ **+{xp_gain} XP**{extra}",
            reply_markup=main_kb(),
            parse_mode="Markdown",
        )
    else:
        fine = min(p["money"], random.randint(120, 260))
        p["money"] -= fine
        p["wanted"] = min(5, p["wanted"] + 1)
        save_data(players)
        await callback.message.answer(
            f"🚨 **Облава!** Патруль засёк тебя.\n"
            f"💸 Потери: **-{fine} ₽**\n"
            f"⭐ Розыск: **{p['wanted']}/5**",
            reply_markup=main_kb(),
            parse_mode="Markdown",
        )
    await callback.answer()


@dp.callback_query(F.data == "clear_wanted")
async def cb_clear_wanted(callback: CallbackQuery):
    p = get_player(callback.from_user.id, callback.from_user.full_name)
    if p["wanted"] == 0:
        await callback.answer("Розыска нет.", show_alert=True)
        return
    cost = p["wanted"] * 250
    if p["money"] < cost:
        await callback.answer(f"Нужно {cost} ₽!", show_alert=True)
        return
    p["money"] -= cost
    p["wanted"] = 0
    save_data(players)
    await callback.message.answer(
        f"🕵️ Розыск снят за **{cost} ₽**.",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "p_cars")
async def cb_cars(callback: CallbackQuery):
    rows = []
    for c_id, info in CARS.items():
        if c_id == "none":
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{info['name']} — {info['price']} ₽ (+{info['escape_bonus']}% уход)",
                    callback_data=f"buycar:{c_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="p_profile")])
    await callback.message.answer(
        "🚗 **Авторынок**\nВыбери транспорт:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("buycar:"))
async def cb_buycar(callback: CallbackQuery):
    c_id = callback.data.split(":", 1)[1]
    info = CARS.get(c_id)
    if not info:
        await callback.answer("Машина не найдена", show_alert=True)
        return
    p = get_player(callback.from_user.id, callback.from_user.full_name)
    if p["car"] == c_id:
        await callback.answer("Эта тачка уже у тебя!", show_alert=True)
        return
    if p["money"] < info["price"]:
        await callback.answer(f"Не хватает денег! Нужно {info['price']} ₽", show_alert=True)
        return
    p["money"] -= info["price"]
    p["car"] = c_id
    save_data(players)
    await callback.message.answer(
        f"🎉 Куплен транспорт: **{info['name']}**!",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "p_top")
async def cb_top(callback: CallbackQuery):
    if not players:
        await callback.answer("Пока нет игроков", show_alert=True)
        return
    ranked = sorted(players.values(), key=lambda x: (x.get("lvl", 1), x.get("money", 0)), reverse=True)[:10]
    lines = ["🏆 **Топ-10 игроков:**\n"]
    for i, u in enumerate(ranked, start=1):
        lines.append(f"{i}. **{u['name']}** — {u['lvl']} ур. | {u['money']} ₽")
    await callback.message.answer("\n".join(lines), reply_markup=main_kb(), parse_mode="Markdown")
    await callback.answer()


async def main() -> None:
    if not TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN в переменных окружения!")
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
import os
from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from . import texts
from .calculator import calculate, load_catalog
from .editing import DIMENSIONS, InputError, parse_corners, parse_number, parse_openings, set_dimension
from .models import ROOF_NAMES, House
from .vision import AnalysisError, analyze_photos

MAX_PHOTOS = 5

FIELD_PROMPTS = {
    "length_m": "Введите длину дома по карнизной стороне, м (например 10,5):",
    "width_m": "Введите ширину дома по торцу, м:",
    "wall_height_m": "Введите высоту стен от цоколя до карниза, м:",
    "gable_height_m": "Введите высоту фронтона от карниза до конька, м:",
    "windows": "Введите окна в формате ширина×высота×количество, группы через «;».\n"
    "Например: <code>1,2х1,4х6; 0,6х0,6х2</code>. Нет окон — 0.",
    "doors": "Введите двери в формате ширина×высота×количество.\nНапример: <code>0,9х2,1х1</code>. Нет дверей — 0.",
    "corners": "Введите число наружных углов и через пробел внутренних.\n"
    "Например: <code>4</code> или <code>6 2</code>.",
}


@dataclass
class Session:
    photo_ids: list[str] = field(default_factory=list)
    house: House | None = None
    comment: str | None = None
    confirmed: set[str] = field(default_factory=set)
    awaiting: str | None = None
    analyzing: bool = False


sessions: dict[int, Session] = {}
catalog = load_catalog()
allowed_users = {int(x) for x in os.getenv("ALLOWED_USERS", "").replace(" ", "").split(",") if x}
dp = Dispatcher()


def get_session(user_id: int) -> Session:
    return sessions.setdefault(user_id, Session())


def photos_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Анализировать", callback_data="analyze")],
            [InlineKeyboardButton(text="🗑 Сбросить фото", callback_data="reset")],
        ]
    )


def card_keyboard(house: House) -> InlineKeyboardMarkup:
    def btn(text: str, data: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=data)

    rows = [
        [btn("Длина", "edit:length_m"), btn("Ширина", "edit:width_m"), btn("Высота", "edit:wall_height_m")],
        [btn("Кровля", "roof")],
    ]
    if house.roof_type in ("gable", "shed"):
        rows[1].append(btn("Фронтон", "edit:gable_height_m"))
    rows += [
        [btn("Окна", "edit:windows"), btn("Двери", "edit:doors"), btn("Углы", "edit:corners")],
        [btn("✅ Рассчитать", "calc")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_card(message: Message, session: Session) -> None:
    assert session.house is not None
    await message.answer(
        texts.house_card(session.house, session.confirmed, session.comment),
        reply_markup=card_keyboard(session.house),
    )


@dp.message.middleware()
@dp.callback_query.middleware()
async def access_middleware(handler, event, data):
    if allowed_users and event.from_user and event.from_user.id not in allowed_users:
        if isinstance(event, Message):
            await event.answer("Бот доступен только сотрудникам. Ваш ID: " f"<code>{event.from_user.id}</code>")
        return None
    return await handler(event, data)


@dp.message(CommandStart())
@dp.message(Command("new"))
async def cmd_start(message: Message) -> None:
    sessions[message.from_user.id] = Session()
    await message.answer(texts.START)


@dp.message(Command("manual"))
async def cmd_manual(message: Message) -> None:
    session = Session(
        house=House(
            length_m=10,
            width_m=8,
            wall_height_m=3,
            roof_type="gable",
            gable_height_m=2.5,
            outside_corners=4,
            inside_corners=0,
            windows=[],
            doors=[],
        ),
        confirmed=set(DIMENSIONS),
        comment="Шаблон: поправьте размеры, окна и двери кнопками ниже.",
    )
    sessions[message.from_user.id] = session
    await send_card(message, session)


@dp.message(F.photo)
async def on_photo(message: Message) -> None:
    session = get_session(message.from_user.id)
    if len(session.photo_ids) >= MAX_PHOTOS:
        if not message.media_group_id:
            await message.answer(f"Хватит {MAX_PHOTOS} фото. Нажмите «Анализировать».", reply_markup=photos_keyboard())
        return
    first_in_batch = not session.photo_ids
    session.photo_ids.append(message.photo[-1].file_id)
    # На альбом отвечаем один раз, чтобы не заспамить чат.
    if message.media_group_id and not first_in_batch:
        return
    await message.answer(
        "Фото принято. Можно добавить ещё (другие стороны дома) или сразу анализировать.",
        reply_markup=photos_keyboard(),
    )


@dp.callback_query(F.data == "reset")
async def on_reset(call: CallbackQuery) -> None:
    sessions[call.from_user.id] = Session()
    await call.message.answer("Фото сброшены. Пришлите новые.")
    await call.answer()


@dp.callback_query(F.data == "analyze")
async def on_analyze(call: CallbackQuery, bot: Bot) -> None:
    session = get_session(call.from_user.id)
    if not session.photo_ids:
        await call.answer("Сначала пришлите фото дома", show_alert=True)
        return
    if session.analyzing:
        await call.answer("Уже анализирую…")
        return
    await call.answer()
    session.analyzing = True
    status = await call.message.answer(f"Анализирую фото ({len(session.photo_ids)} шт.), это займёт до минуты…")
    try:
        photos = [(await bot.download(file_id)).read() for file_id in session.photo_ids]
        analysis = await analyze_photos(photos)
    except AnalysisError as e:
        await status.edit_text(f"Не получилось: {e}")
        return
    finally:
        session.analyzing = False

    session.comment = analysis.comment
    session.house = House.model_validate(analysis.model_dump(exclude={"comment"}))
    session.confirmed = set()
    await status.delete()
    await send_card(call.message, session)


@dp.callback_query(F.data.startswith("edit:"))
async def on_edit(call: CallbackQuery) -> None:
    session = get_session(call.from_user.id)
    if session.house is None:
        await call.answer("Сначала пришлите фото или /manual", show_alert=True)
        return
    session.awaiting = call.data.removeprefix("edit:")
    await call.message.answer(FIELD_PROMPTS[session.awaiting])
    await call.answer()


@dp.callback_query(F.data == "roof")
async def on_roof(call: CallbackQuery) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=name, callback_data=f"roof:{key}")] for key, name in ROOF_NAMES.items()]
    )
    await call.message.answer("Выберите тип кровли:", reply_markup=keyboard)
    await call.answer()


@dp.callback_query(F.data.startswith("roof:"))
async def on_roof_selected(call: CallbackQuery) -> None:
    session = get_session(call.from_user.id)
    if session.house is None:
        await call.answer()
        return
    roof = call.data.removeprefix("roof:")
    update: dict = {"roof_type": roof}
    if roof in ("hip", "flat"):
        update["gable_height_m"] = 0
    elif session.house.gable_height_m == 0:
        update["gable_height_m"] = round(session.house.width_m * 0.3, 2)
    session.house = session.house.model_copy(update=update)
    await call.answer()
    await send_card(call.message, session)


@dp.callback_query(F.data == "calc")
async def on_calc(call: CallbackQuery) -> None:
    session = get_session(call.from_user.id)
    if session.house is None:
        await call.answer("Нет данных для расчёта", show_alert=True)
        return
    await call.answer()
    estimate = calculate(session.house, catalog)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✏️ Изменить параметры", callback_data="card")]]
    )
    await call.message.answer(texts.estimate_text(estimate), reply_markup=keyboard)


@dp.callback_query(F.data == "card")
async def on_card(call: CallbackQuery) -> None:
    session = get_session(call.from_user.id)
    await call.answer()
    if session.house:
        await send_card(call.message, session)


@dp.message(F.text)
async def on_text(message: Message) -> None:
    session = get_session(message.from_user.id)
    if session.house is None or session.awaiting is None:
        await message.answer("Пришлите фото дома или начните с /manual. Помощь: /start")
        return

    field_name = session.awaiting
    note = ""
    try:
        if field_name in DIMENSIONS:
            first_scale = not (session.confirmed & set(DIMENSIONS))
            value = parse_number(message.text, 0.5, 100)
            session.house = set_dimension(session.house, field_name, value, session.confirmed)
            if first_scale:
                note = "Остальные размеры пересчитал пропорционально фото. Если знаете их точно — поправьте.\n\n"
        elif field_name == "gable_height_m":
            value = parse_number(message.text, 0, 20)
            session.house = session.house.model_copy(update={"gable_height_m": value})
            session.confirmed.add(field_name)
        elif field_name in ("windows", "doors"):
            session.house = session.house.model_copy(update={field_name: parse_openings(message.text)})
        elif field_name == "corners":
            outside, inside = parse_corners(message.text)
            session.house = session.house.model_copy(update={"outside_corners": outside, "inside_corners": inside})
    except InputError as e:
        await message.answer(f"{e}. Попробуйте ещё раз.")
        return

    session.awaiting = None
    if note:
        await message.answer(note.strip())
    await send_card(message, session)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Не задан TELEGRAM_BOT_TOKEN (см. .env.example)")
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


def run() -> None:
    asyncio.run(main())

"""
Booking scenario (Scenario 1).

FSM States:
  SelectService → SelectDate → SelectTime → EnterName → SharePhone → ConfirmBooking

Phone is collected via Telegram's native contact-sharing button (no manual typing).
/start works from any state — clears FSM and returns to main menu.
"""
from __future__ import annotations

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

from services import db, calendar as cal, notifications

router = Router()

CANCEL_BTN = InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_to_menu")


class BookingFSM(StatesGroup):
    select_service = State()
    select_date = State()
    select_time = State()
    enter_name = State()
    share_phone = State()
    confirm = State()


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[CANCEL_BTN]])


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💅 Записаться", callback_data="start_booking")],
        [InlineKeyboardButton(text="📋 Мои записи", callback_data="my_bookings")],
    ])


def _services_kb(services: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{s['name']} — {s['price']} ₽",
            callback_data=f"svc:{s['id']}",
        )]
        for s in services
    ]
    rows.append([CANCEL_BTN])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _dates_kb(dates: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=_fmt_date(d), callback_data=f"date:{d}")]
        for d in dates
    ]
    rows.append([CANCEL_BTN])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _times_kb(slots: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=str(s["slot_time"])[:5],
            callback_data=f"time:{s['id']}:{str(s['slot_time'])[:5]}",
        )]
        for s in slots
    ]
    rows.append([CANCEL_BTN])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_booking")],
        [CANCEL_BTN],
    ])


def _phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _fmt_date(d: str) -> str:
    """YYYY-MM-DD → 'D мес'"""
    try:
        from datetime import date
        dt = date.fromisoformat(d)
        months = [
            "", "янв", "фев", "мар", "апр", "май", "июн",
            "июл", "авг", "сен", "окт", "ноя", "дек",
        ]
        return f"{dt.day} {months[dt.month]}"
    except Exception:
        return d


# ---------------------------------------------------------------------------
# /start — works from ANY FSM state
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я помогу записаться на процедуру наращивания ресниц 💅\n\n"
        "Выберите действие:",
        reply_markup=_main_menu_kb(),
    )


@router.callback_query(F.data == "cancel_to_menu")
async def cancel_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Действие отменено.")
    await callback.message.answer("Главное меню:", reply_markup=_main_menu_kb())
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 1 — select service
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "start_booking")
async def step_select_service(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    services = db.get_services()
    if not services:
        await callback.message.edit_text(
            "На данный момент список услуг недоступен. Попробуйте позже."
        )
        await callback.answer()
        return

    await state.set_state(BookingFSM.select_service)
    await callback.message.edit_text(
        "Выберите услугу:", reply_markup=_services_kb(services)
    )
    await callback.answer()


@router.message(BookingFSM.select_service, ~F.text.startswith("/"))
async def step_select_service_text(message: Message, state: FSMContext) -> None:
    services = db.get_services()
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_services_kb(services),
    )


@router.callback_query(BookingFSM.select_service, F.data.startswith("svc:"))
async def step_service_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    svc_id = callback.data.split(":", 1)[1]
    services = db.get_services()
    service = next((s for s in services if str(s["id"]) == svc_id), None)
    if not service:
        await callback.answer("Услуга не найдена.", show_alert=True)
        return

    await state.update_data(
        service_id=svc_id,
        service_name=service["name"],
        duration_min=service["duration_min"],
    )

    dates = db.get_free_slots_dates()
    if not dates:
        await callback.message.edit_text(
            "Свободных дат нет. Пожалуйста, попробуйте позже.",
            reply_markup=_cancel_kb(),
        )
        await callback.answer()
        return

    await state.set_state(BookingFSM.select_date)
    await callback.message.edit_text(
        f"Услуга: <b>{service['name']}</b>\n\nВыберите дату:",
        parse_mode="HTML",
        reply_markup=_dates_kb(dates),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 2 — select date
# ---------------------------------------------------------------------------

@router.message(BookingFSM.select_date, ~F.text.startswith("/"))
async def step_select_date_text(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_dates_kb(db.get_free_slots_dates()),
    )


@router.callback_query(BookingFSM.select_date, F.data.startswith("date:"))
async def step_date_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    slot_date = callback.data.split(":", 1)[1]
    await state.update_data(slot_date=slot_date)

    slots = db.get_free_slots_for_date(slot_date)
    if not slots:
        await callback.message.edit_text(
            "На эту дату уже нет свободных слотов. Выберите другую дату.",
            reply_markup=_dates_kb(db.get_free_slots_dates()),
        )
        await callback.answer()
        return

    await state.set_state(BookingFSM.select_time)
    await callback.message.edit_text(
        f"Дата: <b>{_fmt_date(slot_date)}</b>\n\nВыберите время:",
        parse_mode="HTML",
        reply_markup=_times_kb(slots),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 3 — select time
# ---------------------------------------------------------------------------

@router.message(BookingFSM.select_time, ~F.text.startswith("/"))
async def step_select_time_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    slots = db.get_free_slots_for_date(data["slot_date"])
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_times_kb(slots),
    )


@router.callback_query(BookingFSM.select_time, F.data.startswith("time:"))
async def step_time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    _, slot_id, slot_time = callback.data.split(":", 2)
    await state.update_data(slot_id=slot_id, slot_time=slot_time)

    await state.set_state(BookingFSM.enter_name)
    await callback.message.edit_text(
        "Отлично! Введите ваше имя:",
        reply_markup=_cancel_kb(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 4 — enter name
# ---------------------------------------------------------------------------

@router.message(BookingFSM.enter_name, F.text, ~F.text.startswith("/"))
async def step_name_entered(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer(
            "Имя слишком короткое. Введите ваше имя:",
            reply_markup=_cancel_kb(),
        )
        return
    await state.update_data(client_name=name)
    await state.set_state(BookingFSM.share_phone)
    await message.answer(
        f"Имя: <b>{name}</b>\n\n"
        "Нажмите кнопку ниже, чтобы поделиться номером телефона.\n\n"
        "<i>Чтобы отменить — напишите /start</i>",
        parse_mode="HTML",
        reply_markup=_phone_kb(),
    )


# ---------------------------------------------------------------------------
# Step 5 — share phone via contact button
# ---------------------------------------------------------------------------

@router.message(BookingFSM.share_phone, F.contact)
async def step_phone_contact(message: Message, state: FSMContext) -> None:
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone

    await state.update_data(client_phone=phone)
    data = await state.get_data()

    summary = (
        "📋 <b>Итого по записи:</b>\n\n"
        f"💅 Услуга: {data['service_name']}\n"
        f"📅 Дата: {_fmt_date(data['slot_date'])}\n"
        f"🕐 Время: {data['slot_time']}\n"
        f"👤 Имя: {data['client_name']}\n"
        f"📞 Телефон: {phone}\n\n"
        "Всё верно?"
    )
    await state.set_state(BookingFSM.confirm)
    # Remove the reply keyboard, then show inline confirmation
    await message.answer("✅ Номер получен!", reply_markup=ReplyKeyboardRemove())
    await message.answer(summary, parse_mode="HTML", reply_markup=_confirm_kb())


@router.message(BookingFSM.share_phone, ~F.text.startswith("/"))
async def step_phone_fallback(message: Message) -> None:
    await message.answer(
        "Нажмите кнопку «📱 Поделиться номером» 👇",
        reply_markup=_phone_kb(),
    )


# ---------------------------------------------------------------------------
# Step 6 — confirm booking
# ---------------------------------------------------------------------------

@router.callback_query(BookingFSM.confirm, F.data == "confirm_booking")
async def step_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()

    db.mark_slot_busy(data["slot_id"])

    slot_row = db.get_slot_by_id(data["slot_id"])
    if slot_row and slot_row.get("calendar_event_id"):
        cal.mark_slot_event_busy(slot_row["calendar_event_id"])

    booking_cal_id = cal.create_booking_event(
        client_name=data["client_name"],
        service_name=data["service_name"],
        client_phone=data["client_phone"],
        slot_date=data["slot_date"],
        slot_time=data["slot_time"],
        duration_min=data["duration_min"],
    )

    db.create_booking(
        telegram_id=callback.from_user.id,
        client_name=data["client_name"],
        client_phone=data["client_phone"],
        service_id=data["service_id"],
        slot_id=data["slot_id"],
        calendar_event_id=booking_cal_id,
    )

    await notifications.notify_new_booking(
        bot=bot,
        client_name=data["client_name"],
        service_name=data["service_name"],
        slot_date=data["slot_date"],
        slot_time=data["slot_time"],
        client_phone=data["client_phone"],
    )

    await state.clear()
    await callback.message.edit_text(
        f"✅ Запись подтверждена!\n\n"
        f"💅 {data['service_name']}\n"
        f"📅 {_fmt_date(data['slot_date'])} в {data['slot_time']}\n\n"
        "Напомним за 24 и за 2 часа до записи 🔔"
    )
    await callback.answer("Запись сохранена!")


@router.message(BookingFSM.confirm, ~F.text.startswith("/"))
async def step_confirm_text(message: Message) -> None:
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_confirm_kb(),
    )

"""
Booking scenario (Scenario 1).

FSM States:
  SelectService → SelectDate → SelectTime → EnterName → EnterPhone → ConfirmBooking
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
)

from services import db, calendar as cal, notifications

router = Router()

CANCEL_BTN = InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_to_menu")


class BookingFSM(StatesGroup):
    select_service = State()
    select_date = State()
    select_time = State()
    enter_name = State()
    enter_phone = State()
    confirm = State()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[CANCEL_BTN]])


def _services_kb(services: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{s['name']} — {s['price']} ₽",
            callback_data=f"svc:{s['id']}",  # max ~40 bytes (uuid=36), well within 64-byte limit
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
            text=s["slot_time"][:5],
            callback_data=f"time:{s['id']}:{s['slot_time'][:5]}",
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


def _fmt_date(d: str) -> str:
    """YYYY-MM-DD → DD.MM.YYYY"""
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
# Entry: /start → main menu
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💅 Записаться", callback_data="start_booking")],
        [InlineKeyboardButton(text="📋 Мои записи", callback_data="my_bookings")],
    ])
    await message.answer(
        "Привет! Я помогу записаться на процедуру наращивания ресниц 💅\n\n"
        "Выберите действие:",
        reply_markup=kb,
    )


@router.callback_query(F.data == "cancel_to_menu")
async def cancel_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Действие отменено.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💅 Записаться", callback_data="start_booking")],
        [InlineKeyboardButton(text="📋 Мои записи", callback_data="my_bookings")],
    ])
    await callback.message.answer("Главное меню:", reply_markup=kb)
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 1 — select service
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "start_booking")
async def step_select_service(callback: CallbackQuery, state: FSMContext) -> None:
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


@router.message(BookingFSM.select_service)
async def step_select_service_text(message: Message, state: FSMContext) -> None:
    services = db.get_services()
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_services_kb(services),
    )


@router.callback_query(BookingFSM.select_service, F.data.startswith("svc:"))
async def step_service_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    svc_id = callback.data.split(":", 1)[1]

    # Look up service details from DB — name/duration are NOT stored in callback_data
    # to stay within Telegram's 64-byte callback_data limit
    services = db.get_services()
    service = next((s for s in services if str(s["id"]) == svc_id), None)
    if not service:
        await callback.answer("Услуга не найдена.", show_alert=True)
        return

    svc_name = service["name"]
    duration = service["duration_min"]

    await state.update_data(
        service_id=svc_id, service_name=svc_name, duration_min=duration
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
        f"Услуга: <b>{svc_name}</b>\n\nВыберите дату:",
        parse_mode="HTML",
        reply_markup=_dates_kb(dates),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 2 — select date
# ---------------------------------------------------------------------------

@router.message(BookingFSM.select_date)
async def step_select_date_text(message: Message, state: FSMContext) -> None:
    dates = db.get_free_slots_dates()
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_dates_kb(dates),
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

@router.message(BookingFSM.select_time)
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
        "Отлично! Теперь введите ваше имя:",
        reply_markup=_cancel_kb(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Step 4 — enter name
# ---------------------------------------------------------------------------

@router.message(BookingFSM.enter_name, F.text)
async def step_name_entered(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer(
            "Имя слишком короткое. Пожалуйста, введите ваше имя:",
            reply_markup=_cancel_kb(),
        )
        return
    await state.update_data(client_name=name)
    await state.set_state(BookingFSM.enter_phone)
    await message.answer(
        f"Имя: <b>{name}</b>\n\nВведите номер телефона (например, +7 999 123-45-67):",
        parse_mode="HTML",
        reply_markup=_cancel_kb(),
    )


# ---------------------------------------------------------------------------
# Step 5 — enter phone
# ---------------------------------------------------------------------------

@router.message(BookingFSM.enter_phone, F.text)
async def step_phone_entered(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 10:
        await message.answer(
            "Номер телефона кажется неверным. Введите номер ещё раз:",
            reply_markup=_cancel_kb(),
        )
        return

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
    await message.answer(summary, parse_mode="HTML", reply_markup=_confirm_kb())


# ---------------------------------------------------------------------------
# Step 6 — confirm booking
# ---------------------------------------------------------------------------

@router.callback_query(BookingFSM.confirm, F.data == "confirm_booking")
async def step_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()

    # 1. Mark slot busy in Supabase
    db.mark_slot_busy(data["slot_id"])

    # 2. Mark slot event busy in Google Calendar "Слоты"
    slot_row = db.get_slot_by_id(data["slot_id"])
    if slot_row and slot_row.get("calendar_event_id"):
        cal.mark_slot_event_busy(slot_row["calendar_event_id"])

    # 3. Create event in "Записи клиентов"
    booking_cal_id = cal.create_booking_event(
        client_name=data["client_name"],
        service_name=data["service_name"],
        client_phone=data["client_phone"],
        slot_date=data["slot_date"],
        slot_time=data["slot_time"],
        duration_min=data["duration_min"],
    )

    # 4. Save booking to Supabase
    db.create_booking(
        telegram_id=callback.from_user.id,
        client_name=data["client_name"],
        client_phone=data["client_phone"],
        service_id=data["service_id"],
        slot_id=data["slot_id"],
        calendar_event_id=booking_cal_id,
    )

    # 5. Notify master
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
        "Мы пришлём вам напоминание за 24 и за 2 часа до записи."
    )
    await callback.answer("Запись сохранена!")


@router.message(BookingFSM.confirm)
async def step_confirm_text(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_confirm_kb(),
    )

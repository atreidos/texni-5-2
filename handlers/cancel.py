"""
Cancel / Reschedule scenario (Scenario 3).

FSM States (reschedule reuses BookingFSM from booking.py):
  MyBookings → BookingAction → (cancel | reschedule → BookingFSM)
"""
from __future__ import annotations

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from services import db, calendar as cal, notifications
from handlers.booking import (
    BookingFSM,
    _dates_kb,
    _times_kb,
    _confirm_kb,
    _fmt_date,
    CANCEL_BTN,
)

router = Router()


class CancelFSM(StatesGroup):
    choose_action = State()
    reschedule_select_date = State()
    reschedule_select_time = State()
    reschedule_confirm = State()


def _bookings_kb(bookings: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for b in bookings:
        slot = b.get("slots", {})
        svc = b.get("services", {})
        label = (
            f"{svc.get('name','?')} — "
            f"{_fmt_date(slot.get('slot_date',''))} "
            f"{str(slot.get('slot_time',''))[:5]}"
        )
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"booking_action:{b['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="cancel_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _action_kb(booking_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"do_cancel:{booking_id}")],
        [InlineKeyboardButton(text="🔄 Перенести запись", callback_data=f"do_reschedule:{booking_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="my_bookings")],
    ])


# ---------------------------------------------------------------------------
# Entry: my bookings
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "my_bookings")
async def show_my_bookings(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    bookings = db.get_active_bookings_for_user(callback.from_user.id)
    if not bookings:
        await callback.message.edit_text(
            "У вас нет активных записей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💅 Записаться", callback_data="start_booking")],
            ]),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "Ваши активные записи:", reply_markup=_bookings_kb(bookings)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("booking_action:"))
async def booking_action(callback: CallbackQuery, state: FSMContext) -> None:
    booking_id = callback.data.split(":", 1)[1]
    booking = db.get_booking_by_id(booking_id)
    if not booking:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    slot = booking.get("slots", {})
    svc = booking.get("services", {})
    text = (
        f"💅 <b>{svc.get('name','?')}</b>\n"
        f"📅 {_fmt_date(slot.get('slot_date',''))} в {str(slot.get('slot_time',''))[:5]}\n\n"
        "Что хотите сделать?"
    )
    await state.set_state(CancelFSM.choose_action)
    await state.update_data(booking_id=booking_id)
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=_action_kb(booking_id)
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Cancel flow
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("do_cancel:"))
async def do_cancel(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    booking_id = callback.data.split(":", 1)[1]
    booking = db.get_booking_by_id(booking_id)
    if not booking:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    slot = booking.get("slots", {})
    svc = booking.get("services", {})

    # 1. Cancel in Supabase
    db.cancel_booking(booking_id)

    # 2. Free the slot in Supabase
    db.mark_slot_free(booking["slot_id"])

    # 3. Free the slot event in Google Calendar "Слоты"
    if slot.get("calendar_event_id"):
        cal.mark_slot_event_free(slot["calendar_event_id"])

    # 4. Delete event from "Записи клиентов"
    if booking.get("calendar_event_id"):
        cal.delete_booking_event(booking["calendar_event_id"])

    # 5. Notify master
    await notifications.notify_cancelled_booking(
        bot=bot,
        client_name=booking["client_name"],
        service_name=svc.get("name", "?"),
        slot_date=slot.get("slot_date", ""),
        slot_time=str(slot.get("slot_time", "")),
    )

    await state.clear()
    await callback.message.edit_text(
        "✅ Запись отменена. Надеемся увидеть вас снова! 💅"
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Reschedule flow — select new date/time
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("do_reschedule:"))
async def do_reschedule_start(callback: CallbackQuery, state: FSMContext) -> None:
    booking_id = callback.data.split(":", 1)[1]
    booking = db.get_booking_by_id(booking_id)
    if not booking:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    svc = booking.get("services", {})
    await state.update_data(
        reschedule_booking_id=booking_id,
        service_id=svc.get("id"),
        service_name=svc.get("name"),
        duration_min=svc.get("duration_min", 60),
        old_slot_id=booking["slot_id"],
        old_cal_event_id=booking.get("calendar_event_id"),
        client_name=booking["client_name"],
        client_phone=booking["client_phone"],
    )

    dates = db.get_free_slots_dates()
    if not dates:
        await callback.message.edit_text(
            "Нет свободных дат для переноса. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[CANCEL_BTN]]),
        )
        await callback.answer()
        return

    await state.set_state(CancelFSM.reschedule_select_date)
    await callback.message.edit_text(
        f"Выберите новую дату для переноса ({svc.get('name','')}):",
        reply_markup=_dates_kb(dates),
    )
    await callback.answer()


@router.message(CancelFSM.reschedule_select_date)
async def reschedule_date_text(message: Message, state: FSMContext) -> None:
    dates = db.get_free_slots_dates()
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_dates_kb(dates),
    )


@router.callback_query(CancelFSM.reschedule_select_date, F.data.startswith("date:"))
async def reschedule_date_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    slot_date = callback.data.split(":", 1)[1]
    await state.update_data(new_slot_date=slot_date)

    slots = db.get_free_slots_for_date(slot_date)
    if not slots:
        await callback.message.edit_text(
            "На эту дату нет свободных слотов. Выберите другую:",
            reply_markup=_dates_kb(db.get_free_slots_dates()),
        )
        await callback.answer()
        return

    await state.set_state(CancelFSM.reschedule_select_time)
    await callback.message.edit_text(
        f"Дата: <b>{_fmt_date(slot_date)}</b>\n\nВыберите время:",
        parse_mode="HTML",
        reply_markup=_times_kb(slots),
    )
    await callback.answer()


@router.message(CancelFSM.reschedule_select_time)
async def reschedule_time_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    slots = db.get_free_slots_for_date(data["new_slot_date"])
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_times_kb(slots),
    )


@router.callback_query(CancelFSM.reschedule_select_time, F.data.startswith("time:"))
async def reschedule_time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    _, slot_id, slot_time = callback.data.split(":", 2)
    await state.update_data(new_slot_id=slot_id, new_slot_time=slot_time)

    data = await state.get_data()
    summary = (
        "📋 <b>Перенос записи:</b>\n\n"
        f"💅 Услуга: {data['service_name']}\n"
        f"📅 Новая дата: {_fmt_date(data['new_slot_date'])}\n"
        f"🕐 Новое время: {slot_time}\n\n"
        "Подтвердить перенос?"
    )
    await state.set_state(CancelFSM.reschedule_confirm)
    await callback.message.edit_text(
        summary, parse_mode="HTML", reply_markup=_confirm_kb()
    )
    await callback.answer()


@router.callback_query(CancelFSM.reschedule_confirm, F.data == "confirm_booking")
async def reschedule_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    booking_id = data["reschedule_booking_id"]
    booking = db.get_booking_by_id(booking_id)
    if not booking:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    old_slot = booking.get("slots", {})

    # 1. Free old slot in Supabase + Calendar
    db.mark_slot_free(data["old_slot_id"])
    if old_slot.get("calendar_event_id"):
        cal.mark_slot_event_free(old_slot["calendar_event_id"])

    # 2. Mark new slot busy in Supabase + Calendar
    db.mark_slot_busy(data["new_slot_id"])
    new_slot_row = db.get_slot_by_id(data["new_slot_id"])
    if new_slot_row and new_slot_row.get("calendar_event_id"):
        cal.mark_slot_event_busy(new_slot_row["calendar_event_id"])

    # 3. Update event in "Записи клиентов"
    new_cal_id = cal.update_booking_event(
        calendar_event_id=data["old_cal_event_id"],
        client_name=data["client_name"],
        service_name=data["service_name"],
        client_phone=data["client_phone"],
        slot_date=data["new_slot_date"],
        slot_time=data["new_slot_time"],
        duration_min=data["duration_min"],
    )

    # 4. Update booking in Supabase: new slot, reset reminders, update cal event
    from services import db as _db
    _db.get_client().table("bookings").update({
        "slot_id": data["new_slot_id"],
        "calendar_event_id": new_cal_id,
        "reminder_24h_sent": False,
        "reminder_2h_sent": False,
    }).eq("id", booking_id).execute()

    # 5. Notify master
    await notifications.notify_rescheduled_booking(
        bot=bot,
        client_name=data["client_name"],
        service_name=data["service_name"],
        old_date=old_slot.get("slot_date", ""),
        old_time=str(old_slot.get("slot_time", "")),
        new_date=data["new_slot_date"],
        new_time=data["new_slot_time"],
    )

    await state.clear()
    await callback.message.edit_text(
        f"✅ Запись перенесена!\n\n"
        f"💅 {data['service_name']}\n"
        f"📅 {_fmt_date(data['new_slot_date'])} в {data['new_slot_time']}"
    )
    await callback.answer("Запись перенесена!")


@router.message(CancelFSM.reschedule_confirm)
async def reschedule_confirm_text(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_confirm_kb(),
    )

"""
Master slot management (Scenario 4).
Only accessible when telegram_id == MASTER_CHAT_ID.

FSM States: MasterSelectDate → MasterSelectTime → MasterConfirmSlot
"""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

import config
from services import db, calendar as cal

router = Router()

# Preset time buttons (HH:MM, 30-minute grid)
TIME_OPTIONS = [
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    "12:00", "12:30", "13:00", "13:30", "14:00", "14:30",
    "15:00", "15:30", "16:00", "16:30", "17:00", "17:30",
    "18:00", "18:30", "19:00",
]

CANCEL_BTN = InlineKeyboardButton(text="❌ Отменить", callback_data="master_cancel")


class MasterFSM(StatesGroup):
    select_date = State()
    select_time = State()
    confirm_slot = State()


# ---------------------------------------------------------------------------
# Access guard
# ---------------------------------------------------------------------------

def _is_master(telegram_id: int) -> bool:
    return telegram_id == config.MASTER_CHAT_ID


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def _master_dates_kb() -> InlineKeyboardMarkup:
    """Offer the next 14 days as date options."""
    today = date.today()
    rows = []
    for i in range(14):
        d = today + timedelta(days=i)
        label = d.strftime("%d.%m.%Y (%a)")
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"mdate:{d.isoformat()}",
            )
        ])
    rows.append([CANCEL_BTN])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _master_times_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t, callback_data=f"mtime:{t}")]
        for t in TIME_OPTIONS
    ]
    rows.append([CANCEL_BTN])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _master_confirm_kb(slot_date: str, slot_time: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Да, сохранить",
            callback_data=f"mconfirm:{slot_date}:{slot_time}",
        )],
        [CANCEL_BTN],
    ])


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@router.message(Command("addslots"))
async def cmd_addslots(message: Message, state: FSMContext) -> None:
    if not _is_master(message.from_user.id):
        await message.answer("Эта команда доступна только мастеру.")
        return

    await state.clear()
    await state.set_state(MasterFSM.select_date)
    await message.answer(
        "Выберите дату для нового слота:",
        reply_markup=_master_dates_kb(),
    )


@router.callback_query(F.data == "master_cancel")
async def master_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Добавление слота отменено.")
    await callback.answer()


@router.message(MasterFSM.select_date)
async def master_select_date_text(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_master_dates_kb(),
    )


@router.callback_query(MasterFSM.select_date, F.data.startswith("mdate:"))
async def master_date_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    slot_date = callback.data.split(":", 1)[1]
    await state.update_data(slot_date=slot_date)
    await state.set_state(MasterFSM.select_time)
    await callback.message.edit_text(
        f"Дата: <b>{slot_date}</b>\n\nВыберите время слота:",
        parse_mode="HTML",
        reply_markup=_master_times_kb(),
    )
    await callback.answer()


@router.message(MasterFSM.select_time)
async def master_select_time_text(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_master_times_kb(),
    )


@router.callback_query(MasterFSM.select_time, F.data.startswith("mtime:"))
async def master_time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    slot_time = callback.data.split(":", 1)[1]
    await state.update_data(slot_time=slot_time)
    data = await state.get_data()

    await state.set_state(MasterFSM.confirm_slot)
    await callback.message.edit_text(
        f"Добавить слот?\n\n📅 {data['slot_date']} в {slot_time}",
        reply_markup=_master_confirm_kb(data["slot_date"], slot_time),
    )
    await callback.answer()


@router.message(MasterFSM.confirm_slot)
async def master_confirm_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=_master_confirm_kb(data["slot_date"], data["slot_time"]),
    )


@router.callback_query(MasterFSM.confirm_slot, F.data.startswith("mconfirm:"))
async def master_confirm_slot(callback: CallbackQuery, state: FSMContext) -> None:
    _, slot_date, slot_time = callback.data.split(":", 2)

    # 1. Create event in Google Calendar "Слоты"
    cal_event_id = cal.create_slot_event(slot_date, slot_time)

    # 2. Save slot to Supabase
    db.create_slot(slot_date, slot_time, cal_event_id)

    await state.clear()
    await callback.message.edit_text(
        f"✅ Слот добавлен!\n\n📅 {slot_date} в {slot_time}"
    )
    await callback.answer("Слот сохранён!")


@router.message(Command("master"))
async def cmd_master_menu(message: Message) -> None:
    """Master control panel — quick overview."""
    if not _is_master(message.from_user.id):
        await message.answer("Эта команда доступна только мастеру.")
        return

    await message.answer(
        "🛠 <b>Панель мастера</b>\n\n"
        "/addslots — добавить рабочий слот",
        parse_mode="HTML",
    )

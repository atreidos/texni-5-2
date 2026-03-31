"""
Master slot management (Scenario 4).
Only accessible when telegram_id == MASTER_CHAT_ID.

Two modes:
  1. Single  — pick individual time slots one by one
  2. Period  — pick start → end time, creates all 30-min slots in range

After saving, options:
  - Copy to tomorrow (one tap, no extra steps)
  - Copy to specific days of current week (checkboxes)
  - Done

Already-existing slots are filtered out from all time pickers.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from aiogram import Router, F
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

TIME_OPTIONS = [
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    "12:00", "12:30", "13:00", "13:30", "14:00", "14:30",
    "15:00", "15:30", "16:00", "16:30", "17:00", "17:30",
    "18:00", "18:30", "19:00",
]

WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

CANCEL_BTN = InlineKeyboardButton(text="❌ Отменить", callback_data="master_cancel")


class MasterFSM(StatesGroup):
    select_mode = State()
    select_date = State()
    # single mode
    select_time = State()
    confirm_single = State()
    # period mode
    period_start = State()
    period_end = State()
    confirm_period = State()
    # post-save
    after_save = State()
    select_weekdays = State()


# ---------------------------------------------------------------------------
# Access guard
# ---------------------------------------------------------------------------

def _is_master(telegram_id: int) -> bool:
    return telegram_id == config.MASTER_CHAT_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_week_dates() -> list[date]:
    """Mon–Sun of the current week."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def _slots_in_range(start: str, end: str) -> list[str]:
    """All TIME_OPTIONS slots from start to end inclusive."""
    try:
        si = TIME_OPTIONS.index(start)
        ei = TIME_OPTIONS.index(end)
        return TIME_OPTIONS[si: ei + 1]
    except ValueError:
        return [start]


async def _save_slots(slot_date: str, times: list[str]) -> list[str]:
    """Save slots, silently skip duplicates. Returns list of newly saved times."""
    existing = db.get_existing_times_for_date(slot_date)
    saved: list[str] = []
    for t in times:
        if t in existing:
            continue
        try:
            cal_event_id = cal.create_slot_event(slot_date, t)
        except Exception:
            cal_event_id = ""
        db.create_slot(slot_date, t, cal_event_id)
        saved.append(t)
    return saved


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def _mode_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕐 По одному", callback_data="mmode:single")],
        [InlineKeyboardButton(text="⏱ Периодом (с… по)", callback_data="mmode:period")],
        [CANCEL_BTN],
    ])


def _master_dates_kb() -> InlineKeyboardMarkup:
    today = date.today()
    rows = []
    for i in range(14):
        d = today + timedelta(days=i)
        rows.append([InlineKeyboardButton(
            text=d.strftime("%d.%m (%a)"),
            callback_data=f"mdate:{d.isoformat()}",
        )])
    rows.append([CANCEL_BTN])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _available_times_kb(slot_date: str) -> InlineKeyboardMarkup:
    """Times not yet added to this date."""
    existing = db.get_existing_times_for_date(slot_date)
    rows = [
        [InlineKeyboardButton(text=t, callback_data=f"mtime:{t}")]
        for t in TIME_OPTIONS
        if t not in existing
    ]
    if not rows:
        rows = [[InlineKeyboardButton(text="Все слоты уже добавлены", callback_data="noop")]]
    rows.append([CANCEL_BTN])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _period_end_kb(slot_date: str, start_time: str) -> InlineKeyboardMarkup:
    """Times strictly after start_time that are not yet added."""
    existing = db.get_existing_times_for_date(slot_date)
    try:
        start_idx = TIME_OPTIONS.index(start_time)
    except ValueError:
        start_idx = 0
    rows = [
        [InlineKeyboardButton(text=t, callback_data=f"mperiod_end:{t}")]
        for t in TIME_OPTIONS[start_idx + 1:]
        if t not in existing
    ]
    if not rows:
        rows = [[InlineKeyboardButton(text="Нет доступных слотов после этого времени", callback_data="noop")]]
    rows.append([CANCEL_BTN])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _after_save_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Скопировать на завтра", callback_data="mafter:tomorrow")],
        [InlineKeyboardButton(text="📆 Выбрать дни недели", callback_data="mafter:weekdays")],
        [InlineKeyboardButton(text="✅ Готово", callback_data="mafter:done")],
    ])


def _weekdays_kb(selected: list[int], week_dates: list[date]) -> InlineKeyboardMarkup:
    rows = []
    for i, d in enumerate(week_dates):
        mark = "✅" if i in selected else "⬜"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {WEEKDAYS_RU[d.weekday()]} {d.strftime('%d.%m')}",
            callback_data=f"mwd:{i}",
        )])
    rows.append([
        InlineKeyboardButton(text="💾 Сохранить", callback_data="mwd:save"),
        CANCEL_BTN,
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _single_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, сохранить", callback_data="mconfirm_single")],
        [CANCEL_BTN],
    ])


def _period_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, сохранить", callback_data="mconfirm_period")],
        [CANCEL_BTN],
    ])


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

@router.message(Command("addslots"))
async def cmd_addslots(message: Message, state: FSMContext) -> None:
    if not _is_master(message.from_user.id):
        await message.answer("Эта команда доступна только мастеру.")
        return
    await state.clear()
    await state.set_state(MasterFSM.select_mode)
    await message.answer("Как добавить слоты?", reply_markup=_mode_kb())


@router.message(Command("master"))
async def cmd_master_menu(message: Message) -> None:
    if not _is_master(message.from_user.id):
        await message.answer("Эта команда доступна только мастеру.")
        return
    await message.answer(
        "🛠 <b>Панель мастера</b>\n\n/addslots — добавить рабочие слоты",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "master_cancel")
async def master_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Добавление слотов отменено.")
    await callback.answer()


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------

@router.callback_query(MasterFSM.select_mode, F.data.startswith("mmode:"))
async def master_mode_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.split(":")[1]
    await state.update_data(mode=mode)
    await state.set_state(MasterFSM.select_date)
    await callback.message.edit_text("Выберите дату:", reply_markup=_master_dates_kb())
    await callback.answer()


@router.message(MasterFSM.select_mode)
async def master_mode_text(message: Message) -> None:
    await message.answer("Пожалуйста, используйте кнопки 👇", reply_markup=_mode_kb())


# ---------------------------------------------------------------------------
# Date selection
# ---------------------------------------------------------------------------

@router.message(MasterFSM.select_date)
async def master_select_date_text(message: Message) -> None:
    await message.answer("Пожалуйста, используйте кнопки 👇", reply_markup=_master_dates_kb())


@router.callback_query(MasterFSM.select_date, F.data.startswith("mdate:"))
async def master_date_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    slot_date = callback.data.split(":", 1)[1]
    await state.update_data(slot_date=slot_date)
    data = await state.get_data()
    mode = data.get("mode", "single")

    if mode == "single":
        await state.set_state(MasterFSM.select_time)
        await callback.message.edit_text(
            f"📅 <b>{slot_date}</b>\n\nВыберите время слота:",
            parse_mode="HTML",
            reply_markup=_available_times_kb(slot_date),
        )
    else:
        await state.set_state(MasterFSM.period_start)
        await callback.message.edit_text(
            f"📅 <b>{slot_date}</b>\n\nВыберите время <b>начала</b> периода:",
            parse_mode="HTML",
            reply_markup=_available_times_kb(slot_date),
        )
    await callback.answer()


# ---------------------------------------------------------------------------
# Single mode
# ---------------------------------------------------------------------------

@router.message(MasterFSM.select_time)
async def master_select_time_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer(
        "Пожалуйста, используйте кнопки 👇",
        reply_markup=_available_times_kb(data.get("slot_date", "")),
    )


@router.callback_query(MasterFSM.select_time, F.data.startswith("mtime:"))
async def master_time_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    slot_time = callback.data.split(":", 1)[1]
    data = await state.get_data()
    await state.update_data(slot_time=slot_time)
    await state.set_state(MasterFSM.confirm_single)
    await callback.message.edit_text(
        f"Добавить слот?\n\n📅 {data['slot_date']} в {slot_time}",
        reply_markup=_single_confirm_kb(),
    )
    await callback.answer()


@router.message(MasterFSM.confirm_single)
async def master_confirm_single_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer(
        "Пожалуйста, используйте кнопки 👇",
        reply_markup=_single_confirm_kb(),
    )


@router.callback_query(MasterFSM.confirm_single, F.data == "mconfirm_single")
async def master_confirm_single(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    saved = await _save_slots(data["slot_date"], [data["slot_time"]])

    await state.update_data(saved_times=saved if saved else [data["slot_time"]])
    await state.set_state(MasterFSM.after_save)

    if saved:
        text = f"✅ Слот добавлен: {data['slot_date']} в {data['slot_time']}\n\nЧто дальше?"
    else:
        text = f"⚠️ Слот {data['slot_date']} {data['slot_time']} уже существует.\n\nЧто дальше?"

    await callback.message.edit_text(text, reply_markup=_after_save_kb())
    await callback.answer()


# ---------------------------------------------------------------------------
# Period mode
# ---------------------------------------------------------------------------

@router.message(MasterFSM.period_start)
async def master_period_start_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer(
        "Пожалуйста, используйте кнопки 👇",
        reply_markup=_available_times_kb(data.get("slot_date", "")),
    )


@router.callback_query(MasterFSM.period_start, F.data.startswith("mtime:"))
async def master_period_start_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    start_time = callback.data.split(":", 1)[1]
    data = await state.get_data()
    await state.update_data(period_start=start_time)
    await state.set_state(MasterFSM.period_end)
    await callback.message.edit_text(
        f"📅 {data['slot_date']}\n⏱ Начало: <b>{start_time}</b>\n\nВыберите время <b>конца</b>:",
        parse_mode="HTML",
        reply_markup=_period_end_kb(data["slot_date"], start_time),
    )
    await callback.answer()


@router.message(MasterFSM.period_end)
async def master_period_end_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer(
        "Пожалуйста, используйте кнопки 👇",
        reply_markup=_period_end_kb(data.get("slot_date", ""), data.get("period_start", "")),
    )


@router.callback_query(MasterFSM.period_end, F.data.startswith("mperiod_end:"))
async def master_period_end_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    end_time = callback.data.split(":", 1)[1]
    data = await state.get_data()
    slots = _slots_in_range(data["period_start"], end_time)
    await state.update_data(period_end=end_time, period_slots=slots)
    await state.set_state(MasterFSM.confirm_period)
    await callback.message.edit_text(
        f"📅 <b>{data['slot_date']}</b>\n"
        f"⏱ Период: {data['period_start']} — {end_time}\n"
        f"🔢 Слотов: {len(slots)} ({', '.join(slots)})\n\n"
        "Сохранить?",
        parse_mode="HTML",
        reply_markup=_period_confirm_kb(),
    )
    await callback.answer()


@router.message(MasterFSM.confirm_period)
async def master_confirm_period_text(message: Message) -> None:
    await message.answer("Пожалуйста, используйте кнопки 👇", reply_markup=_period_confirm_kb())


@router.callback_query(MasterFSM.confirm_period, F.data == "mconfirm_period")
async def master_confirm_period(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    slots = data.get("period_slots", [])
    saved = await _save_slots(data["slot_date"], slots)

    await state.update_data(saved_times=saved if saved else slots)
    await state.set_state(MasterFSM.after_save)

    if saved:
        text = (
            f"✅ Добавлено {len(saved)} слот(ов) на {data['slot_date']}:\n"
            f"{', '.join(saved)}\n\nЧто дальше?"
        )
    else:
        text = f"⚠️ Все слоты на {data['slot_date']} уже существуют.\n\nЧто дальше?"

    await callback.message.edit_text(text, reply_markup=_after_save_kb())
    await callback.answer()


# ---------------------------------------------------------------------------
# After save — copy to tomorrow / weekdays / done
# ---------------------------------------------------------------------------

@router.callback_query(MasterFSM.after_save, F.data.startswith("mafter:"))
async def master_after_save(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":")[1]
    data = await state.get_data()

    if action == "done":
        await state.clear()
        await callback.message.edit_text("✅ Готово!")
        await callback.answer()
        return

    if action == "tomorrow":
        tomorrow = (date.fromisoformat(data["slot_date"]) + timedelta(days=1)).isoformat()
        saved = await _save_slots(tomorrow, data.get("saved_times", []))
        if saved:
            text = f"✅ Скопировано на {tomorrow}: {', '.join(saved)}\n\nЧто дальше?"
        else:
            text = f"⚠️ Слоты на {tomorrow} уже существуют.\n\nЧто дальше?"
        await callback.message.edit_text(text, reply_markup=_after_save_kb())
        await callback.answer()
        return

    if action == "weekdays":
        week_dates = _get_week_dates()
        await state.update_data(
            weekday_selected=[],
            week_dates=[d.isoformat() for d in week_dates],
        )
        await state.set_state(MasterFSM.select_weekdays)
        await callback.message.edit_text(
            "Выберите дни недели для копирования слотов:",
            reply_markup=_weekdays_kb([], week_dates),
        )
        await callback.answer()


# ---------------------------------------------------------------------------
# Weekday multi-select
# ---------------------------------------------------------------------------

@router.callback_query(MasterFSM.select_weekdays, F.data.startswith("mwd:"))
async def master_weekday_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":")[1]
    data = await state.get_data()
    week_dates = [date.fromisoformat(d) for d in data.get("week_dates", [])]
    selected: list[int] = list(data.get("weekday_selected", []))

    if action == "save":
        if not selected:
            await callback.answer("Выберите хотя бы один день!", show_alert=True)
            return

        results: list[str] = []
        for idx in selected:
            d = week_dates[idx].isoformat()
            saved = await _save_slots(d, data.get("saved_times", []))
            if saved:
                results.append(f"{d}: {', '.join(saved)}")

        if results:
            text = "✅ Скопировано:\n" + "\n".join(results) + "\n\nЧто дальше?"
        else:
            text = "⚠️ Слоты уже существуют на выбранных днях.\n\nЧто дальше?"

        await state.update_data(weekday_selected=[])
        await state.set_state(MasterFSM.after_save)
        await callback.message.edit_text(text, reply_markup=_after_save_kb())
        await callback.answer()
        return

    # Toggle day
    idx = int(action)
    if idx in selected:
        selected.remove(idx)
    else:
        selected.append(idx)
    await state.update_data(weekday_selected=selected)
    await callback.message.edit_reply_markup(
        reply_markup=_weekdays_kb(selected, week_dates)
    )
    await callback.answer()

"""
Reminder scheduler (Scenario 2).

Runs as a background APScheduler job every 5 minutes.
Sends reminders at 24h and 2h before the appointment.
Uses reminder_24h_sent / reminder_2h_sent flags to avoid duplicates.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

import config
from services import db

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(pytz.timezone(config.TIMEZONE))


def _appointment_dt(slot: dict) -> datetime | None:
    """Combine slot_date and slot_time into a timezone-aware datetime."""
    try:
        tz = pytz.timezone(config.TIMEZONE)
        slot_date = slot["slot_date"]          # "YYYY-MM-DD"
        slot_time = str(slot["slot_time"])     # "HH:MM:SS" or "HH:MM"
        dt_str = f"{slot_date} {slot_time[:5]}"
        return tz.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))
    except Exception as e:
        logger.warning(f"Could not parse appointment datetime: {e}")
        return None


async def _send_reminder(bot: Bot, booking: dict, hours_before: int) -> None:
    slot = booking.get("slots", {})
    svc = booking.get("services", {})
    slot_date = slot.get("slot_date", "")
    slot_time = str(slot.get("slot_time", ""))[:5]

    if hours_before == 24:
        timing_text = "завтра"
    else:
        timing_text = "через 2 часа"

    text = (
        f"⏰ <b>Напоминание о записи</b>\n\n"
        f"У вас запись {timing_text}!\n\n"
        f"💅 Услуга: {svc.get('name', '?')}\n"
        f"📅 Дата: {slot_date}\n"
        f"🕐 Время: {slot_time}\n\n"
        "Если вам нужно перенести или отменить запись — нажмите /start"
    )
    try:
        await bot.send_message(booking["telegram_id"], text, parse_mode="HTML")
        db.mark_reminder_sent(booking["id"], hours_before)
        logger.info(
            f"Reminder {hours_before}h sent to telegram_id={booking['telegram_id']}"
        )
    except Exception as e:
        logger.error(f"Failed to send reminder: {e}")


async def check_and_send_reminders(bot: Bot) -> None:
    """Called by scheduler every 5 minutes."""
    now = _now()

    for hours in config.REMINDER_HOURS:
        bookings = db.get_bookings_needing_reminder(hours, now)
        for booking in bookings:
            apt_dt = _appointment_dt(booking.get("slots", {}))
            if apt_dt is None:
                continue
            diff = apt_dt - now
            window_start = timedelta(hours=hours) - timedelta(minutes=10)
            window_end = timedelta(hours=hours) + timedelta(minutes=5)
            if window_start <= diff <= window_end:
                await _send_reminder(bot, booking, hours)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)
    scheduler.add_job(
        check_and_send_reminders,
        trigger="interval",
        minutes=5,
        kwargs={"bot": bot},
        id="reminders",
        replace_existing=True,
    )
    return scheduler

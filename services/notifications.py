"""
Notifications to the master via Telegram.
All functions accept a bot instance to avoid circular imports.
"""
from __future__ import annotations

from aiogram import Bot

import config


async def notify_new_booking(
    bot: Bot,
    client_name: str,
    service_name: str,
    slot_date: str,
    slot_time: str,
    client_phone: str,
) -> None:
    text = (
        "🆕 <b>Новая запись!</b>\n\n"
        f"👤 Клиент: {client_name}\n"
        f"💅 Услуга: {service_name}\n"
        f"📅 Дата: {slot_date}\n"
        f"🕐 Время: {slot_time[:5]}\n"
        f"📞 Телефон: {client_phone}"
    )
    await bot.send_message(config.MASTER_CHAT_ID, text, parse_mode="HTML")


async def notify_cancelled_booking(
    bot: Bot,
    client_name: str,
    service_name: str,
    slot_date: str,
    slot_time: str,
) -> None:
    text = (
        "❌ <b>Запись отменена</b>\n\n"
        f"👤 Клиент: {client_name}\n"
        f"💅 Услуга: {service_name}\n"
        f"📅 Освободилась дата: {slot_date} в {slot_time[:5]}"
    )
    await bot.send_message(config.MASTER_CHAT_ID, text, parse_mode="HTML")


async def notify_rescheduled_booking(
    bot: Bot,
    client_name: str,
    service_name: str,
    old_date: str,
    old_time: str,
    new_date: str,
    new_time: str,
) -> None:
    text = (
        "🔄 <b>Перенос записи</b>\n\n"
        f"👤 Клиент: {client_name}\n"
        f"💅 Услуга: {service_name}\n"
        f"📅 Было: {old_date} в {old_time[:5]}\n"
        f"📅 Стало: {new_date} в {new_time[:5]}"
    )
    await bot.send_message(config.MASTER_CHAT_ID, text, parse_mode="HTML")

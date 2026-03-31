"""
Supabase data access layer.
All writes are gated: only called after the user confirms (booking) or the
master issues a command — anonymous/unauthenticated writes never reach here.
"""
from __future__ import annotations

from datetime import date, time, datetime
from typing import Optional
from uuid import UUID

from supabase import create_client, Client

import config

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _client


# ---------------------------------------------------------------------------
# services
# ---------------------------------------------------------------------------

def get_services() -> list[dict]:
    """Return all active services ordered by name."""
    res = (
        get_client()
        .table("services")
        .select("*")
        .eq("is_active", True)
        .order("name")
        .execute()
    )
    return res.data or []


# ---------------------------------------------------------------------------
# slots
# ---------------------------------------------------------------------------

def get_free_slots_dates() -> list[str]:
    """Return sorted unique dates that have at least one free slot (YYYY-MM-DD)."""
    res = (
        get_client()
        .table("slots")
        .select("slot_date")
        .eq("status", "free")
        .order("slot_date")
        .execute()
    )
    seen: set[str] = set()
    result: list[str] = []
    for row in res.data or []:
        d = row["slot_date"]
        if d not in seen:
            seen.add(d)
            result.append(d)
    return result


def get_free_slots_for_date(slot_date: str) -> list[dict]:
    """Return free slots for the given date, sorted by time."""
    res = (
        get_client()
        .table("slots")
        .select("*")
        .eq("slot_date", slot_date)
        .eq("status", "free")
        .order("slot_time")
        .execute()
    )
    return res.data or []


def mark_slot_busy(slot_id: str) -> None:
    get_client().table("slots").update({"status": "busy"}).eq("id", slot_id).execute()


def mark_slot_free(slot_id: str) -> None:
    get_client().table("slots").update({"status": "free"}).eq("id", slot_id).execute()


def create_slot(
    slot_date: str,
    slot_time: str,
    calendar_event_id: str,
) -> dict:
    """Insert a new free slot and return the created row."""
    res = (
        get_client()
        .table("slots")
        .insert(
            {
                "slot_date": slot_date,
                "slot_time": slot_time,
                "status": "free",
                "calendar_event_id": calendar_event_id,
            }
        )
        .execute()
    )
    return res.data[0]


def get_slot_by_id(slot_id: str) -> Optional[dict]:
    res = (
        get_client().table("slots").select("*").eq("id", slot_id).limit(1).execute()
    )
    data = res.data or []
    return data[0] if data else None


# ---------------------------------------------------------------------------
# bookings
# ---------------------------------------------------------------------------

def create_booking(
    telegram_id: int,
    client_name: str,
    client_phone: str,
    service_id: str,
    slot_id: str,
    calendar_event_id: str,
) -> dict:
    res = (
        get_client()
        .table("bookings")
        .insert(
            {
                "telegram_id": telegram_id,
                "client_name": client_name,
                "client_phone": client_phone,
                "service_id": service_id,
                "slot_id": slot_id,
                "status": "active",
                "calendar_event_id": calendar_event_id,
                "reminder_24h_sent": False,
                "reminder_2h_sent": False,
            }
        )
        .execute()
    )
    return res.data[0]


def get_active_bookings_for_user(telegram_id: int) -> list[dict]:
    """Return active bookings for a user with slot and service data joined."""
    res = (
        get_client()
        .table("bookings")
        .select("*, slots(*), services(*)")
        .eq("telegram_id", telegram_id)
        .eq("status", "active")
        .order("created_at", desc=False)
        .execute()
    )
    return res.data or []


def get_booking_by_id(booking_id: str) -> Optional[dict]:
    res = (
        get_client()
        .table("bookings")
        .select("*, slots(*), services(*)")
        .eq("id", booking_id)
        .limit(1)
        .execute()
    )
    data = res.data or []
    return data[0] if data else None


def cancel_booking(booking_id: str) -> None:
    get_client().table("bookings").update({"status": "cancelled"}).eq(
        "id", booking_id
    ).execute()


def update_booking_calendar_event(booking_id: str, calendar_event_id: str) -> None:
    get_client().table("bookings").update(
        {"calendar_event_id": calendar_event_id}
    ).eq("id", booking_id).execute()


def get_bookings_needing_reminder(hours_before: int, now: datetime) -> list[dict]:
    """
    Return active bookings that need a reminder at `hours_before` hours before
    the appointment and haven't had this reminder sent yet.
    """
    flag_field = f"reminder_{hours_before}h_sent"
    res = (
        get_client()
        .table("bookings")
        .select("*, slots(*), services(*)")
        .eq("status", "active")
        .eq(flag_field, False)
        .execute()
    )
    return res.data or []


def mark_reminder_sent(booking_id: str, hours_before: int) -> None:
    flag_field = f"reminder_{hours_before}h_sent"
    get_client().table("bookings").update({flag_field: True}).eq(
        "id", booking_id
    ).execute()

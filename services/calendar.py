"""
Google Calendar integration.
Two calendars:
  - CALENDAR_SLOTS_ID    ("Слоты")           — working calendar for the bot
  - CALENDAR_BOOKINGS_ID ("Записи клиентов") — display calendar for the master
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pytz
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config

SCOPES = ["https://www.googleapis.com/auth/calendar"]

_service = None


def get_service():
    global _service
    if _service is None:
        creds_dict = config.get_google_credentials_dict()
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _service


def _tz() -> pytz.BaseTzInfo:
    return pytz.timezone(config.TIMEZONE)


def _dt_to_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = _tz().localize(dt)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Slots calendar ("Слоты")
# ---------------------------------------------------------------------------

def create_slot_event(slot_date: str, slot_time: str) -> str:
    """
    Create a free slot event in the Slots calendar.
    Returns the Google Calendar event ID.
    """
    tz = _tz()
    start_dt = tz.localize(
        datetime.strptime(f"{slot_date} {slot_time}", "%Y-%m-%d %H:%M")
    )
    end_dt = start_dt + timedelta(minutes=config.DEFAULT_SLOT_DURATION_MIN)

    body = {
        "summary": f"Слот: {slot_time[:5]}",
        "description": "status: free",
        "start": {"dateTime": _dt_to_rfc3339(start_dt), "timeZone": config.TIMEZONE},
        "end": {"dateTime": _dt_to_rfc3339(end_dt), "timeZone": config.TIMEZONE},
        "extendedProperties": {
            "private": {"status": "free"}
        },
    }
    event = (
        get_service()
        .events()
        .insert(calendarId=config.CALENDAR_SLOTS_ID, body=body)
        .execute()
    )
    return event["id"]


def mark_slot_event_busy(calendar_event_id: str) -> None:
    """Update the slot event description and extended property to 'busy'."""
    try:
        event = (
            get_service()
            .events()
            .get(calendarId=config.CALENDAR_SLOTS_ID, eventId=calendar_event_id)
            .execute()
        )
        event["description"] = "status: busy"
        event.setdefault("extendedProperties", {}).setdefault("private", {})[
            "status"
        ] = "busy"
        get_service().events().update(
            calendarId=config.CALENDAR_SLOTS_ID,
            eventId=calendar_event_id,
            body=event,
        ).execute()
    except HttpError:
        pass


def mark_slot_event_free(calendar_event_id: str) -> None:
    """Restore the slot event to 'free'."""
    try:
        event = (
            get_service()
            .events()
            .get(calendarId=config.CALENDAR_SLOTS_ID, eventId=calendar_event_id)
            .execute()
        )
        event["description"] = "status: free"
        event.setdefault("extendedProperties", {}).setdefault("private", {})[
            "status"
        ] = "free"
        get_service().events().update(
            calendarId=config.CALENDAR_SLOTS_ID,
            eventId=calendar_event_id,
            body=event,
        ).execute()
    except HttpError:
        pass


# ---------------------------------------------------------------------------
# Bookings calendar ("Записи клиентов")
# ---------------------------------------------------------------------------

def create_booking_event(
    client_name: str,
    service_name: str,
    client_phone: str,
    slot_date: str,
    slot_time: str,
    duration_min: int,
) -> str:
    """
    Create a booking event in the Bookings calendar.
    Returns the Google Calendar event ID.
    """
    tz = _tz()
    start_dt = tz.localize(
        datetime.strptime(f"{slot_date} {slot_time}", "%Y-%m-%d %H:%M")
    )
    end_dt = start_dt + timedelta(minutes=duration_min)

    date_fmt = start_dt.strftime("%d.%m.%Y в %H:%M")
    body = {
        "summary": f"{client_name} — {service_name}",
        "description": (
            f"Телефон: {client_phone}\n"
            f"Услуга: {service_name}\n"
            f"Дата: {date_fmt}"
        ),
        "start": {"dateTime": _dt_to_rfc3339(start_dt), "timeZone": config.TIMEZONE},
        "end": {"dateTime": _dt_to_rfc3339(end_dt), "timeZone": config.TIMEZONE},
    }
    event = (
        get_service()
        .events()
        .insert(calendarId=config.CALENDAR_BOOKINGS_ID, body=body)
        .execute()
    )
    return event["id"]


def delete_booking_event(calendar_event_id: str) -> None:
    """Delete a booking event from the Bookings calendar."""
    try:
        get_service().events().delete(
            calendarId=config.CALENDAR_BOOKINGS_ID, eventId=calendar_event_id
        ).execute()
    except HttpError:
        pass


def update_booking_event(
    calendar_event_id: str,
    client_name: str,
    service_name: str,
    client_phone: str,
    slot_date: str,
    slot_time: str,
    duration_min: int,
) -> str:
    """
    Update an existing booking event (used on reschedule).
    Returns the (possibly same) event ID.
    """
    try:
        tz = _tz()
        start_dt = tz.localize(
            datetime.strptime(f"{slot_date} {slot_time}", "%Y-%m-%d %H:%M")
        )
        end_dt = start_dt + timedelta(minutes=duration_min)
        date_fmt = start_dt.strftime("%d.%m.%Y в %H:%M")

        event = (
            get_service()
            .events()
            .get(calendarId=config.CALENDAR_BOOKINGS_ID, eventId=calendar_event_id)
            .execute()
        )
        event["summary"] = f"{client_name} — {service_name}"
        event["description"] = (
            f"Телефон: {client_phone}\n"
            f"Услуга: {service_name}\n"
            f"Дата: {date_fmt}"
        )
        event["start"] = {
            "dateTime": _dt_to_rfc3339(start_dt),
            "timeZone": config.TIMEZONE,
        }
        event["end"] = {
            "dateTime": _dt_to_rfc3339(end_dt),
            "timeZone": config.TIMEZONE,
        }
        updated = (
            get_service()
            .events()
            .update(
                calendarId=config.CALENDAR_BOOKINGS_ID,
                eventId=calendar_event_id,
                body=event,
            )
            .execute()
        )
        return updated["id"]
    except HttpError:
        # If the old event is gone, create a new one
        return create_booking_event(
            client_name, service_name, client_phone, slot_date, slot_time, duration_min
        )

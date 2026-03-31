# Architecture

## Project structure

```
bot.py                    — Entry point: Bot + Dispatcher + scheduler startup
config.py                 — All settings read from .env
handlers/
  booking.py              — Scenario 1: booking FSM (SelectService → … → Confirm)
  cancel.py               — Scenario 3: cancel / reschedule FSM
  master.py               — Scenario 4: master adds slots via /addslots
  reminders.py            — Scenario 2: APScheduler sends reminders at 24h & 2h
services/
  db.py                   — Supabase data access layer (all DB operations)
  calendar.py             — Google Calendar API (slots + bookings calendars)
  notifications.py        — Master Telegram notifications
  ai_service.py           — Reserved for AI v2 (all stubs, AI_ENABLED=false)
supabase_schema.sql       — DB schema + seed data (run once in Supabase SQL editor)
.env.example              — Environment variable template
```

## FSM state map

### Booking (handlers/booking.py — BookingFSM)
```
/start → MAIN_MENU
  → start_booking callback
    → [select_service]
    → [select_date]
    → [select_time]
    → [enter_name]      ← free text input
    → [share_phone]     ← Telegram contact-sharing button (ReplyKeyboard)
    → [confirm]         ← button only
      → write Supabase + mark Calendar + notify master
```
Any state: "cancel_to_menu" callback → clears FSM → main menu.
Any state: unexpected text → "use buttons" message + repeat keyboard.

### Cancel / Reschedule (handlers/cancel.py — CancelFSM)
```
my_bookings callback
  → [choose_action] (per-booking)
    → do_cancel: cancel in Supabase + free slot + delete Calendar event + notify
    → do_reschedule:
        → [reschedule_select_date]
        → [reschedule_select_time]
        → [reschedule_confirm]
          → free old slot + mark new slot + update Calendar event + notify
```

### Master slots (handlers/master.py — MasterFSM)
```
/addslots (MASTER_CHAT_ID only)
  → [select_date]
  → [select_time]
  → [confirm_slot]
    → create event in Calendar "Слоты" + write Supabase
```

## Data flow

```
Client Telegram message
  → aiogram handler
    → services/db.py     (read/write Supabase)
    → services/calendar  (read/write Google Calendar)
    → services/notifications (send to MASTER_CHAT_ID)
  → response to client
```

## AI extension points (v2)

- `services/ai_service.py` — all stubs, activated via `AI_ENABLED=true`
- `enter_name` accepts free text — AI normalisation plugs in transparently
- `share_phone` uses Telegram contact sharing; in v2 AI can also parse text phone input as fallback
- `select_date` / `select_time` — will add text branch → `ai_service.parse_datetime()` → same callback path
- `MAIN_MENU` text input → `ai_service.detect_intent()` → route to FSM state
- RAG: pgvector extension in same Supabase project, no new services needed

## Google Calendar setup

Two separate calendars in the master's Google account:
1. **"Слоты"** (`CALENDAR_SLOTS_ID`) — working calendar; bot reads free slots, marks them busy/free
2. **"Записи клиентов"** (`CALENDAR_BOOKINGS_ID`) — display calendar; bot creates/updates/deletes events; master reads only

Authentication: Google Service Account JSON, shared to both calendars with **Editor** role.

## Reminder logic

APScheduler job runs every 5 minutes.
For each active booking where `reminder_Xh_sent = false`:
- Checks if appointment is within [hours-10min, hours+5min] window
- Sends message to `booking.telegram_id`
- Sets `reminder_Xh_sent = true`

## Deployment (Railway)

All config comes from env vars — code is unchanged.
`GOOGLE_CREDENTIALS_JSON` can be either a file path (local) or the raw JSON string (Railway).

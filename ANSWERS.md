# Answers & decisions log

## Why Supabase + Google Calendar (not just one of them)?

Supabase — fast queries, filtering, joins, source of truth for bot logic.
Google Calendar — convenient UI for the master on her phone, no extra interface needed.
She simply opens Google Calendar and sees her schedule.

## Why MemoryStorage for FSM?

v1 simplicity. On Railway restart FSM state is lost but bookings are in Supabase so
no data is lost — user just needs to restart the conversation.
Can upgrade to RedisStorage later without changing FSM logic.

## Why APScheduler inside the bot process?

Simplest setup for single-instance bot. Runs as asyncio-aware scheduler in the same
event loop. For multi-instance or Railway restarts consider a separate worker process
or a Supabase scheduled function.

## Google Calendar "Слоты" vs "Записи клиентов" — why two?

"Слоты" — machine-readable: bot reads free slots, marks busy/free. Contains technical data.
"Записи клиентов" — human-readable: master sees client name and service. Clean visual calendar.
Keeping them separate prevents master accidentally deleting a slot event the bot depends on.

## Why slot duration is fixed at 30 min in slots calendar but services have their own duration?

Slots define availability windows (smallest unit). Service duration determines the
end time of the booking event in "Записи клиентов". In v2 the bot can check that
enough consecutive slots are free for longer services.

## Reminder window logic

Checking every 5 minutes. Window is [hours - 10min, hours + 5min] to handle
cases where the scheduler wakes up slightly before or after the exact target time.

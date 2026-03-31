# Security decisions

## Anonymous users do not write to DB

Principle: no DB mutations for unauthenticated/anonymous users.

In this bot "authentication" = having a confirmed Telegram identity (all Telegram users
are identified by `from_user.id`). Write operations are only triggered after explicit
user confirmation (Confirm button in booking flow or /addslots command by master).

## Master-only commands

`/addslots` and `/master` check `telegram_id == MASTER_CHAT_ID` before any action.
This check is in `handlers/master.py → _is_master()`.
Backend-level: MASTER_CHAT_ID is read from `.env`, never hardcoded.

## Secrets management

All credentials stored in `.env` (not in repository).
`.env` must be in `.gitignore`.
`.env.example` contains only placeholder values — safe to commit.

## Google Calendar access

Service Account with minimum required scope: `https://www.googleapis.com/auth/calendar`.
Service Account email must be added as Editor to both calendars — no other Google resources accessible.

## Supabase

Uses anon key (SUPABASE_KEY). For production consider:
- Row Level Security (RLS) policies on all tables
- Service role key only for server-side operations
- Never expose service role key to client-side code

## No sensitive data in logs

Logging uses INFO level. Client phone numbers and names are not logged.
If debug logging is needed, ensure PII fields are masked.

## Bot token

TELEGRAM_BOT_TOKEN must never be committed or logged.
Rotate immediately if accidentally exposed.

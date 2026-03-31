# TODO — tasks requiring manual action

## Setup tasks (must do before running the bot)

- [ ] Create `.gitignore` and add `.env` to it
- [ ] Fill in `.env` with real values (copy from `.env.example`)
- [ ] Run `supabase_schema.sql` in Supabase SQL editor
- [ ] Create Google Service Account, download credentials JSON
- [ ] Create two Google Calendars: "Слоты" and "Записи клиентов"
- [ ] Share both calendars to the Service Account email with **Editor** role
- [ ] Get your Telegram `MASTER_CHAT_ID` (send any message to @userinfobot)
- [ ] Create the bot via @BotFather, get `TELEGRAM_BOT_TOKEN`

## Production tasks (before Railway deploy)

- [ ] Enable Row Level Security (RLS) on Supabase tables
- [ ] Set `GOOGLE_CREDENTIALS_JSON` as a raw JSON string in Railway env vars
- [ ] Review APScheduler persistence (MemoryStorage resets on restart — bookmarks reminders may re-trigger after redeploy)

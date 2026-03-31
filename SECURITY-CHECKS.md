# Security checks log

## Check after initial implementation — 2026-03-30

| # | Check | Result |
|---|---|---|
| 1 | `.env` in `.gitignore`? | ✅ `.gitignore` created with `.env` entry |
| 2 | `.env.example` contains no real secrets | ✅ Only placeholder values |
| 3 | Master-only commands gated by `_is_master()` | ✅ handlers/master.py lines ~35,44,96 |
| 4 | DB writes only after user confirmation (Confirm button / /addslots) | ✅ booking.py step_confirm, master.py master_confirm_slot |
| 5 | Bot token not logged | ✅ Only `config.TELEGRAM_BOT_TOKEN` used in Bot() constructor |
| 6 | Client phone/name not logged | ✅ No PII in logging calls |
| 7 | Google credentials JSON handled via helper, not raw env | ✅ config.get_google_credentials_dict() |
| 8 | Supabase key type | ⚠️ Using anon key — consider RLS policies in production |

## Check .gitignore audit — 2026-03-31

| # | Check | Result |
|---|---|---|
| 1 | `.env` и все варианты `.env.*` в `.gitignore` | ✅ `.env`, `.env.local`, `.env.production`, `.env.staging` |
| 2 | Google Service Account JSON (`lash-*.json`) в `.gitignore` | ✅ явная запись + паттерны `credentials*.json`, `service_account*.json` |
| 3 | Лог-файлы (`*.log`) в `.gitignore` | ✅ добавлено |
| 4 | Playwright артефакты в `.gitignore` | ✅ `playwright-report/`, `test-results/`, `screenshots/` добавлено |
| 5 | Локальные БД (`*.sqlite`, `*.db`) в `.gitignore` | ✅ добавлено |
| 6 | `.env.example` содержит только плейсхолдеры | ✅ реальных значений нет |
| 7 | Реальные токены/ключи не попадают ни в один `.md` файл | ✅ проверено — в SECURITY-CHECKS.md, ANSWERS.md, QA.md реальных секретов нет |

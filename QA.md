# QA log

## Tests to run after implementation

User actions to verify through Playwright / manual testing:

1. `/start` → main menu shows two buttons
2. Записаться → select service → select date → select time → enter name → enter phone → confirm → success message
3. Unexpected text at any FSM step → "use buttons" message + keyboard repeated
4. Cancel button at any step → main menu
5. Мои записи → shows active bookings
6. Cancel booking → confirmation + master notification
7. Reschedule → full re-booking flow + old slot freed
8. `/addslots` as master → date → time → confirm → slot appears in Supabase
9. `/addslots` as non-master → access denied message
10. Reminder job runs every 5 min and sends messages at correct windows

---

Tests will be added here after each test run in format:

Тест N1
1 — Тест "[название]": статус
2 — Ошибка: (если была)
3 — Исправил: (если было)
4 — Скриншот: (путь)
---

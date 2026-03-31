import os
import json
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Required environment variable '{key}' is not set")
    return value


# Telegram
TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
MASTER_CHAT_ID: int = int(_require("MASTER_CHAT_ID"))

# Supabase
SUPABASE_URL: str = _require("SUPABASE_URL")
SUPABASE_KEY: str = _require("SUPABASE_KEY")

# Google Calendar
GOOGLE_CREDENTIALS_JSON: str = _require("GOOGLE_CREDENTIALS_JSON")
CALENDAR_SLOTS_ID: str = _require("CALENDAR_SLOTS_ID")
CALENDAR_BOOKINGS_ID: str = _require("CALENDAR_BOOKINGS_ID")

# AI module toggle (reserved for v2)
AI_ENABLED: bool = os.getenv("AI_ENABLED", "false").lower() == "true"

# Timezone for all date/time operations
TIMEZONE = "Europe/Moscow"

# Reminder intervals in hours
REMINDER_HOURS = [24, 2]

# Default slot duration in minutes (used when creating slots)
DEFAULT_SLOT_DURATION_MIN = 30


def get_google_credentials_dict() -> dict:
    """
    Accepts either a file path or a raw JSON string.
    On Railway, pass the JSON string directly in the env variable.
    """
    raw = GOOGLE_CREDENTIALS_JSON
    if raw.strip().startswith("{"):
        return json.loads(raw)
    with open(raw, "r", encoding="utf-8") as f:
        return json.load(f)

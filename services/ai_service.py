"""
AI service — reserved for v2.

Enable via AI_ENABLED=true in .env.
Will implement:
  - parse_datetime(text) -> Optional[tuple[str, str]]   — date+time from free text
  - detect_intent(text)  -> Optional[str]               — FSM state name from text
  - answer_faq(question) -> str                         — RAG via pgvector in Supabase
  - parse_schedule(text) -> list[dict]                  — batch slot creation from text
"""
from __future__ import annotations

from typing import Optional

import config


def is_enabled() -> bool:
    return config.AI_ENABLED


async def parse_datetime(text: str) -> Optional[tuple[str, str]]:
    """
    Parse date and time from a free-text message.
    Returns (YYYY-MM-DD, HH:MM) or None if not enabled / not recognised.
    """
    if not is_enabled():
        return None
    # TODO: implement in v2 (e.g. via OpenAI function calling)
    return None


async def detect_intent(text: str) -> Optional[str]:
    """
    Detect user intent and return the target FSM state name.
    Returns None if not enabled / confidence too low.
    """
    if not is_enabled():
        return None
    # TODO: implement in v2
    return None


async def answer_faq(question: str) -> Optional[str]:
    """
    Answer questions from the knowledge base using RAG (pgvector in Supabase).
    Returns None if not enabled.
    """
    if not is_enabled():
        return None
    # TODO: implement in v2
    return None


async def parse_schedule(text: str) -> list[dict]:
    """
    Parse a batch of slots from free-text master input.
    Returns a list of {slot_date, slot_time} dicts.
    """
    if not is_enabled():
        return []
    # TODO: implement in v2
    return []

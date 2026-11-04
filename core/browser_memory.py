"""Browser-local memory bridge: explicit notes survive tab and app restarts.

This is storage on the current browser only, NOT authenticated PostgreSQL sync.
No user content is interpolated into JavaScript; data flows as component args.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.user_memory import import_library

STORAGE_KEY = "cano.user_notes.v1"


def decode_snapshot(snapshot: Any) -> list[dict]:
    """Fail closed on an unavailable or corrupted browser store."""
    if not isinstance(snapshot, dict) or snapshot.get("status") != "ok":
        raise ValueError("Browser memory unavailable")
    payload = snapshot.get("payload")
    if not isinstance(payload, str):
        raise ValueError("Invalid browser memory payload")
    return import_library(payload) if payload else []


def write_confirmed(snapshot: Any, pending: Any) -> bool:
    """A successful write requires a matching token AND actual read-back."""
    return (
        isinstance(snapshot, dict) and snapshot.get("status") == "ok"
        and isinstance(pending, dict)
        and snapshot.get("ack") == pending.get("token")
        and snapshot.get("payload") == pending.get("payload")
    )


def browser_memory_component(write: dict | None = None) -> dict | None:
    from streamlit.components.v1 import declare_component

    component = declare_component(
        "cano_browser_memory",
        path=str(Path(__file__).with_name("browser_memory_frontend")),
    )
    return component(write=write, key="cano_browser_memory", default=None)

def explicit_memory_request(message: str) -> bool:
    """Recognize clear user requests to persist a short note."""
    if not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
        return False
    lowered = message.casefold()
    return bool(re.search(
        r"(?:hafızana\s+kaydet|hafızaya\s+kaydet|bunu\s+kaydet|"
        r"aklında\s+tut|unutma\b)",
        lowered,
    ))

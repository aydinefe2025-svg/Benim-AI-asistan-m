"""Explicitly opted-in browser-local CANO colony backup.

Browser storage is *not* encrypted, account-scoped or server-side durable.
Never store until the user opts in. The Streamlit frontend component performs
localStorage readback without evaluating user-provided code.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

MAX_BROWSER_PAYLOAD_BYTES = 1_000_000


def _validate_snapshot_shape(snapshot):
    if not isinstance(snapshot, dict) or not all(
            isinstance(snapshot.get(k), list)
            for k in ("agents", "feedback", "reviews", "missions")):
        raise ValueError("Invalid browser colony collections")
    return snapshot


def encode_browser_colony_backup(snapshot):
    """Create a stable, capped write; only call after explicit local opt-in."""
    snapshot = _validate_snapshot_shape(snapshot)
    payload = json.dumps(
        {"version": 1, "opted_in": True, "snapshot": snapshot},
        ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)
    if len(payload.encode("utf-8")) > MAX_BROWSER_PAYLOAD_BYTES:
        raise ValueError("Browser colony backup exceeds local quota")
    return {"token": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "payload": payload}


def decode_browser_colony_backup(report):
    """Parse but never trust browser data; transactional restore validates rows."""
    if not isinstance(report, dict) or report.get("status") != "ok":
        raise ValueError("Browser colony store unavailable")
    payload = report.get("payload")
    if (not isinstance(payload, str) or not payload
            or len(payload.encode("utf-8")) > MAX_BROWSER_PAYLOAD_BYTES):
        raise ValueError("Missing or invalid browser colony backup")
    try:
        data = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid browser colony JSON") from exc
    if (not isinstance(data, dict) or data.get("version") != 1
            or data.get("opted_in") is not True):
        raise ValueError("Untrusted browser colony backup format")
    return _validate_snapshot_shape(data.get("snapshot"))


def browser_write_confirmed(report, write):
    return (isinstance(report, dict) and report.get("status") == "ok"
            and isinstance(write, dict)
            and report.get("ack") == write.get("token")
            and report.get("payload") == write.get("payload"))


def browser_colony_component(*, write=None, clear=False):
    from streamlit.components.v1 import declare_component
    component = declare_component(
        "cano_browser_colony_backup",
        path=str(Path(__file__).with_name("browser_colony_frontend")))
    return component(write=write, clear=bool(clear),
                     key="cano_browser_colony_backup", default=None)

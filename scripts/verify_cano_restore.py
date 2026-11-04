"""Fail-closed validation for a restored CANO SQLite audit file.

Only locally restored evidence is inspected. No agent is activated.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def verify_restored_state(path: str | Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"CANO previous database missing: {path}")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Restored CANO database has integrity error: {integrity}")
        stored = db.execute("SELECT COUNT(*) FROM colony_tick").fetchone()[0]
        row = db.execute(
            "SELECT tick_id, candidates, state FROM colony_tick ORDER BY tick_id DESC LIMIT 1"
        ).fetchone()
        if stored < 1 or row is None:
            raise RuntimeError("Restored CANO database has no verified tick")
        candidates = json.loads(row[1])
        if not isinstance(candidates, list) or row[2] not in ("proposed", "no_capacity"):
            raise RuntimeError("Restored CANO tick contains invalid candidate/state data")
    return {"db_integrity": integrity, "stored_ticks": stored, "last_tick_id": row[0]}


if __name__ == "__main__":
    print(json.dumps(verify_restored_state("artifacts/colony-cycle.sqlite3")))

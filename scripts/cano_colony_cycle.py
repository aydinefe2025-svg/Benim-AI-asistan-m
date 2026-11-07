"""Scheduled colony cycle: auditable proposals, never uncontrolled activation."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from core.continuous_colony import ContinuousColony
from core.virtual_generation import run_virtual_generation


def main() -> None:
    output = Path(os.environ.get("CANO_CYCLE_OUTPUT", "artifacts/colony-cycle.json"))
    db_path = os.environ.get("CANO_CYCLE_DB", "artifacts/colony-cycle.sqlite3")
    colony = ContinuousColony(db_path, max_active=12, max_candidates_per_tick=3)
    colony.initialize()
    founder = {"id": "cano-research-founder", "generation": 0}
    prior_history = colony.history(limit=1)
    prior_tick_id = prior_history[0]["tick_id"] if prior_history else None
    with closing(sqlite3.connect(db_path)) as db:
        previous_tick_count = db.execute("SELECT COUNT(*) FROM colony_tick").fetchone()[0]
    result = colony.tick([founder])
    virtual_generation = run_virtual_generation(db_path, result["tick_id"])
    with closing(sqlite3.connect(db_path)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        stored = db.execute("SELECT COUNT(*) FROM colony_tick").fetchone()[0]
        row = db.execute(
            "SELECT active_count,candidates,state FROM colony_tick WHERE tick_id=?",
            (result["tick_id"],),
        ).fetchone()
        generation_row = db.execute(
            "SELECT lesson_status FROM virtual_generation WHERE tick_id=?",
            (result["tick_id"],),
        ).fetchone()
    if (integrity != "ok" or stored != previous_tick_count + 1
            or row is None or row[0] != result["active_count"]
            or json.loads(row[1]) != result["candidates"] or row[2] != result["state"]
            or generation_row is None
            or generation_row[0] != virtual_generation["lesson_status"]):
        raise RuntimeError("Colony audit database failed integrity/readback check")
    record = {
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "db_integrity": integrity,
        "stored_ticks": stored,
        "verified_tick_id": result["tick_id"],
        "continuity": {
            "had_prior_state": prior_tick_id is not None,
            "previous_tick_id": prior_tick_id,
            "previous_tick_count": previous_tick_count,
            "increment_verified": stored == previous_tick_count + 1,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cycle": result,
        "virtual_generation": virtual_generation,
        "mode": "bounded_virtual_reproduction_with_held_out_validation",
        "scope": "authorized_github_runner",
        "note": "Digital organisms reproduce only inside the bounded toy VM. A mutation-rate lesson transfers only after paired development and held-out confirmation. Four isolated read-only validation workers run afterward. No LLM inference, deployment, or unrestricted coding agents are started.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish verified reports atomically, avoiding truncated JSON on crash.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent,
            prefix=f".{output.name}.", suffix=".tmp", delete=False
        ) as handle:
            tmp_path = Path(handle.name)
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, output)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
    print(json.dumps({"tick_id": result["tick_id"], "proposed": len(result["candidates"]),
                      "activated": result["activated"],
                      "virtual_generation": virtual_generation["generation_id"],
                      "lesson_status": virtual_generation["lesson_status"],
                      "artifact": str(output)}))


if __name__ == "__main__":
    main()

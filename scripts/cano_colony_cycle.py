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
from scripts.cano_specialist_agents import attach_agent_results


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
        tick_row = db.execute("SELECT candidates,state FROM colony_tick WHERE tick_id=?",
                              (result["tick_id"],)).fetchone()
        generation_row = db.execute("SELECT lesson_status FROM virtual_generation WHERE tick_id=?",
                                    (result["tick_id"],)).fetchone()
    if (integrity != "ok" or stored != previous_tick_count + 1 or tick_row is None
            or json.loads(tick_row[0]) != result["candidates"]
            or tick_row[1] != result["state"] or generation_row is None
            or generation_row[0] != virtual_generation["lesson_status"]):
        raise RuntimeError("Colony cycle failed SQLite integrity/readback validation")
    record = {
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "db_integrity": integrity,
        "stored_ticks": stored,
        "verified_tick_id": result["tick_id"],
        "continuity": {"had_prior_state": prior_tick_id is not None,
                       "previous_tick_id": prior_tick_id,
                       "previous_tick_count": previous_tick_count,
                       "increment_verified": stored == previous_tick_count + 1},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cycle": result,
        "virtual_generation": virtual_generation,
        "mode": "bounded_virtual_reproduction_with_held_out_validation",
        "scope": "authorized_github_runner",
        "note": "Digital organisms reproduce only inside the bounded toy VM. A mutation-rate lesson transfers only after paired development and held-out confirmation. No LLM inference, deployment, or independent software agents are started.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=f".{output.name}.", suffix=".tmp",
                                         delete=False) as handle:
            temp_path = Path(handle.name)
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, output)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    # Keep the same independently executed read-only checks visible in the
    # public artifact consumed by the hosted dashboard.
    attach_agent_results(output, db_path)
    print(json.dumps({"tick_id": result["tick_id"], "proposed": len(result["candidates"]),
                      "activated": result["activated"],
                      "virtual_generation": virtual_generation["generation_id"],
                      "lesson_status": virtual_generation["lesson_status"],
                      "artifact": str(output)}))


if __name__ == "__main__":
    main()

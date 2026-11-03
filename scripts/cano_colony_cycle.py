"""Scheduled colony cycle: auditable proposals, never uncontrolled activation."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from core.continuous_colony import ContinuousColony


def main() -> None:
    output = Path(os.environ.get("CANO_CYCLE_OUTPUT", "artifacts/colony-cycle.json"))
    db_path = os.environ.get("CANO_CYCLE_DB", "artifacts/colony-cycle.sqlite3")
    colony = ContinuousColony(db_path, max_active=12, max_candidates_per_tick=3)
    colony.initialize()
    founder = {"id": "cano-research-founder", "generation": 0}
    result = colony.tick([founder])
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cycle": result,
        "mode": "proposal_only",
        "scope": "authorized_github_runner",
        "note": "No LLM inference, deployment, or active agents are started by this job.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tick_id": result["tick_id"], "proposed": len(result["candidates"]),
                      "activated": result["activated"], "artifact": str(output)}))


if __name__ == "__main__":
    main()

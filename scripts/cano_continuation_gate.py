"""Gate CANO follow-up cycles on a validated positive learning transfer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_ROLES = {"evidence", "generation", "continuity", "security"}


def is_eligible(report: Any, source_run_id: str) -> bool:
    """Only continue from this run when integrity, workers and both evals pass."""
    if not isinstance(report, dict) or str(report.get("github_run_id")) != str(source_run_id):
        return False
    if report.get("db_integrity") != "ok":
        return False

    specialists = report.get("specialist_agents")
    roles = specialists.get("roles") if isinstance(specialists, dict) else None
    if not isinstance(roles, list) or specialists.get("status") != "passed":
        return False
    if len(roles) != len(REQUIRED_ROLES):
        return False
    if {row.get("role") for row in roles if isinstance(row, dict)} != REQUIRED_ROLES:
        return False
    if any(
        not isinstance(row, dict)
        or row.get("status") != "passed"
        or row.get("execution") != "isolated_read_only_subprocess"
        or row.get("model_calls") != 0
        for row in roles
    ):
        return False

    generation = report.get("virtual_generation")
    if not isinstance(generation, dict) or generation.get("lesson_status") != "transferred":
        return False
    training = generation.get("training")
    confirmation = generation.get("held_out_confirmation")
    return (
        isinstance(training, dict)
        and training.get("positive_evidence") is True
        and isinstance(confirmation, dict)
        and confirmation.get("positive_evidence") is True
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    eligible = is_eligible(report, args.source_run_id)
    args.output.write_text(
        f"eligible={'true' if eligible else 'false'}\n", encoding="utf-8"
    )
    print("positive validated transfer; follow-up eligible" if eligible
          else "no positive validated transfer; follow-up skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

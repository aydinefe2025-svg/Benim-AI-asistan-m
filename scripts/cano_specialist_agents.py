"""Run bounded, isolated specialist agents against one CANO cycle artifact.

Each agent is a separate Python process with a minimal environment. Agents only
read the cycle report and SQLite database; they have no model/API credentials,
network client, or write permission. They independently check evidence,
generation gating, persistence continuity, and secret exposure.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROLES = ("evidence", "generation", "continuity", "security")
ROLE_LABELS = {
    "evidence": "Kanıt ve kapsam ajanı",
    "generation": "Nesil doğrulama ajanı",
    "continuity": "Kayıt sürekliliği ajanı",
    "security": "Güvenlik tarama ajanı",
}
MAX_REPORT_BYTES = 1_000_000
SECRET_PATTERN = re.compile(
    r"(?:gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{24,})"
)


def _read_report(report_path: str) -> tuple[dict, bytes]:
    payload = Path(report_path).read_bytes()
    if not payload or len(payload) > MAX_REPORT_BYTES:
        raise ValueError("report size is outside the allowed bound")
    report = json.loads(payload)
    if not isinstance(report, dict):
        raise ValueError("report must be an object")
    return report, payload


def _worker(role: str, report_path: str, database_path: str) -> dict:
    if role not in ROLES:
        raise ValueError("unknown specialist role")
    report, payload = _read_report(report_path)
    cycle = report.get("cycle")
    generation = report.get("virtual_generation")
    if not isinstance(cycle, dict) or not isinstance(generation, dict):
        raise ValueError("cycle or virtual generation record is missing")
    checks: list[str] = []

    if role == "evidence":
        if (report.get("mode") != "bounded_virtual_reproduction_with_held_out_validation"
                or report.get("scope") != "authorized_github_runner"
                or generation.get("offspring_scope") != "bounded toy digital VM only"
                or generation.get("model_weights_updated") is not False):
            raise ValueError("simulation scope or model-weight claim is unsafe")
        checks.extend(("simulation_scope", "no_model_weight_claim"))

    elif role == "generation":
        for arm in ("training", "held_out_confirmation"):
            result = generation.get(arm)
            if not isinstance(result, dict) or result.get("paired_seeds", 0) < 2:
                raise ValueError("paired generation evidence is incomplete")
            if not isinstance(result.get("ci95_low"), (int, float)):
                raise ValueError("confidence bound is missing")
        transferred = (
            generation["training"]["ci95_low"] > 0
            and generation["held_out_confirmation"]["ci95_low"] > 0
        )
        expected_status = "transferred" if transferred else "rejected"
        if (generation.get("lesson_status") != expected_status
                or generation.get("next_generation_mutation_rate")
                != (generation.get("candidate_mutation_rate")
                    if transferred else generation.get("parent_mutation_rate"))):
            raise ValueError("candidate transfer gate does not match independent evidence")
        checks.extend(("paired_training", "held_out_confirmation", "transfer_gate"))

    elif role == "continuity":
        if report.get("db_integrity") != "ok":
            raise ValueError("SQLite integrity flag is not clean")
        continuity = report.get("continuity")
        tick_id = report.get("verified_tick_id")
        if (not isinstance(continuity, dict)
                or continuity.get("increment_verified") is not True
                or continuity.get("previous_tick_id") not in (None, tick_id - 1)
                or continuity.get("previous_tick_count", 0) + 1
                != report.get("stored_ticks")):
            raise ValueError("reported cycle continuity is inconsistent")
        uri = Path(database_path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite read-only integrity check failed")
            row = db.execute(
                "SELECT lesson_status FROM virtual_generation WHERE tick_id=?",
                (tick_id,),
            ).fetchone()
            if row is None or row[0] != generation.get("lesson_status"):
                raise ValueError("persisted generation status does not match artifact")
        checks.extend(("cycle_increment", "sqlite_readback", "read_only_access"))

    elif role == "security":
        if SECRET_PATTERN.search(payload.decode("utf-8", errors="replace")):
            raise ValueError("credential-like value detected in public report")
        if len(payload) > MAX_REPORT_BYTES:
            raise ValueError("report exceeded the public artifact bound")
        checks.extend(("credential_pattern_scan", "artifact_size_bound"))

    return {
        "role": role,
        "label": ROLE_LABELS[role],
        "status": "passed",
        "checks": checks,
        "execution": "isolated_read_only_subprocess",
        "model_calls": 0,
    }


def _minimal_environment() -> dict[str, str]:
    # Do not pass provider, database, or GitHub credentials into worker processes.
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
    return {key: os.environ[key] for key in allowed if os.environ.get(key)}


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_agents(report_path: str | Path, database_path: str | Path) -> list[dict]:
    report_path = str(Path(report_path).resolve())
    database_path = str(Path(database_path).resolve())

    def run_one(role: str) -> dict:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--worker-role", role, "--report", report_path, "--database", database_path],
            check=False, capture_output=True, text=True, timeout=20,
            env=_minimal_environment(),
        )
        if completed.returncode != 0:
            raise RuntimeError(f"{role} specialist failed its checks")
        result = json.loads(completed.stdout)
        if result.get("role") != role or result.get("status") != "passed":
            raise RuntimeError(f"{role} specialist returned an invalid result")
        return result

    with ThreadPoolExecutor(max_workers=len(ROLES)) as pool:
        results = list(pool.map(run_one, ROLES))
    # Fixed role ordering makes reports deterministic and easy to review.
    return results


def attach_agent_results(report_path: str | Path, database_path: str | Path) -> list[dict]:
    path = Path(report_path)
    report, _ = _read_report(str(path))
    results = run_agents(path, database_path)
    report["specialist_agents"] = {
        "status": "passed",
        "launched": len(results),
        "roles": results,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "execution_scope": "four isolated read-only Python subprocesses; no model/network/API access",
    }
    _atomic_write(path, report)
    # Verify the final on-disk report after every specialist finishes.
    saved, _ = _read_report(str(path))
    if saved.get("specialist_agents") != report["specialist_agents"]:
        raise RuntimeError("specialist result readback failed")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-role", choices=ROLES)
    parser.add_argument("--report", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    if args.worker_role:
        result = _worker(args.worker_role, args.report, args.database)
        # Worker stdout must remain ASCII-safe under Windows code pages.
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0
    results = attach_agent_results(args.report, args.database)
    print(json.dumps({"launched": len(results), "passed": len(results),
                      "roles": [result["role"] for result in results]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

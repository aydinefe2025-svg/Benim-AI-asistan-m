"""A bounded, restartable calendar-driven *digital simulation*, not agent deployment.

Invoked by an external schedule. A date maps to one deterministic target tick;
rerunning the same date does not reproduce extra organisms. The existing genome
checkpoint is the authoritative state, with deterministic readback verification.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .genome_checkpoint import (
    MAX_TICKS, _replay, _serialize, _snapshot, advance_checkpoint,
    initialize_checkpoint, read_checkpoint,
)
from .audit_store import _exclusive_lock

EPOCH = date(2026, 11, 7)
TICKS_PER_DAY = 8
SEED = 17
CAPACITY = 24
RESOURCES_PER_TICK = 12
MUTATION_RATE = 0.02
SCHEMA = "cano-calendar-digital-cycle-v1"


def _atomic_bytes(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, scratch = tempfile.mkstemp(prefix=".calendar-cycle-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fp:
            fp.write(payload)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(scratch, path)
    finally:
        if os.path.exists(scratch):
            os.unlink(scratch)


def _day_and_tick(day: str) -> tuple[date, int]:
    if not isinstance(day, str):
        raise ValueError("Run day must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(day)
    except ValueError as exc:
        raise ValueError("Run day must be YYYY-MM-DD") from exc
    if parsed.isoformat() != day:
        raise ValueError("Run day must be YYYY-MM-DD")
    number = (parsed - EPOCH).days + 1
    tick = number * TICKS_PER_DAY
    if not (1 <= number and tick <= MAX_TICKS):
        raise ValueError("Day outside finite simulation budget")
    return parsed, tick


def _report_for_day(day: str, tick: int, parameters: dict) -> dict:
    experimental = _replay(parameters, tick)
    control = _replay({**parameters, "allow_replication": False}, tick)
    observed = experimental.metrics()
    reference = control.metrics()
    body = {
        "schema": SCHEMA,
        "day": day,
        "tick": tick,
        "parameters": parameters,
        "observed": observed,
        "division_disabled_control": reference,
        "state_sha256": hashlib.sha256(_serialize(_snapshot(experimental))).hexdigest(),
        "interpretation": "Deterministic offline digital organism simulation; births are not proof of learning or physical self-replication.",
    }
    return {**body, "sha256": hashlib.sha256(_serialize(body)).hexdigest()}


def run_day(root: str | Path, *, day: str):
    """Idempotently advance once per UTC calendar day with bounded replay.

    Uses two separate existing lock mechanisms: the outer calendar lock handles
    report/checkpoint as a unit for this entry point; genome checkpoint's own
    cross-process lock also protects readers/writers of its state file.
    """
    _, tick = _day_and_tick(day)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = root / "genome-state.json"
    report_file = root / "daily" / f"{day}.json"
    with _exclusive_lock(root / "calendar-cycle"):
        if not checkpoint.exists():
            try:
                initialize_checkpoint(
                    checkpoint, seed=SEED, capacity=CAPACITY,
                    resources_per_tick=RESOURCES_PER_TICK,
                    mutation_rate=MUTATION_RATE, target_tick=0,
                )
            except FileExistsError:  # An independent writer initialized it.
                pass
        current = read_checkpoint(checkpoint)
        parameters = current["parameters"]
        if parameters != {
            "seed": SEED, "capacity": CAPACITY,
            "resources_per_tick": RESOURCES_PER_TICK,
            "mutation_rate": MUTATION_RATE, "allow_replication": True,
        }:
            raise ValueError("Unexpected simulation parameters; refusing to mix experiments")
        if current["ticks"] < tick:
            current = advance_checkpoint(checkpoint, target_tick=tick)
        else:
            current = read_checkpoint(checkpoint)
        expected = _report_for_day(day, tick, parameters)
        if current["ticks"] == tick:
            if hashlib.sha256(_serialize(current["state"])).hexdigest() != expected["state_sha256"]:
                raise ValueError("Report and checkpoint disagree")
        if report_file.exists():
            existing = json.loads(report_file.read_text(encoding="utf-8"))
            if existing != expected:
                raise ValueError("Prior daily report differs from deterministic replay")
        else:
            _atomic_bytes(report_file, _serialize(expected))
        if json.loads(report_file.read_text(encoding="utf-8")) != expected:
            raise ValueError("Daily report readback failed")
        return expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--day", default=datetime.now(timezone.utc).date().isoformat(),
                        help="Run key in UTC YYYY-MM-DD")
    args = parser.parse_args(argv)
    doc = run_day(args.state_dir, day=args.day)
    print(json.dumps({
        "date": doc["day"], "tick": doc["tick"],
        "births": doc["observed"]["births"],
        "population": doc["observed"]["population"],
        "control_births": doc["division_disabled_control"]["births"],
        "report_sha256": doc["sha256"],
        "verified": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
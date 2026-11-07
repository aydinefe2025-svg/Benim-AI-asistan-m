"""Read-only watchdog for an already-persisted daily digital-organism cycle.

This file does not reproduce organisms, update a checkpoint, or deploy services.
It verifies the authoritative digital genome checkpoint by replay and compares
its day-specific report to an independent deterministic recomputation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .calendar_cycle import _day_and_tick, _report_for_day
from .genome_checkpoint import _serialize, read_checkpoint


def inspect_day(root: str | Path, *, day: str) -> dict:
    """Fail closed if the expected daily archive is stale, missing or altered.

    The caller decides when the scheduled run should have completed. This
    function only validates the specified UTC day; no network or file writes.
    """
    _, expected_tick = _day_and_tick(day)
    root = Path(root)
    state_file = root / "genome-state.json"
    report_file = root / "daily" / f"{day}.json"
    checkpoint = read_checkpoint(state_file)
    if checkpoint["ticks"] != expected_tick:
        raise ValueError("Stale or future checkpoint; expected tick %s" % expected_tick)
    report = json.loads(report_file.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("Daily report must be an object")
    expected = _report_for_day(day, expected_tick, checkpoint["parameters"])
    if report != expected:
        raise ValueError("Daily report differs from deterministic replay")
    digest = hashlib.sha256(_serialize(checkpoint["state"])).hexdigest()
    if digest != report["state_sha256"]:
        raise ValueError("Genome and daily state digests differ")
    result = {
        "status": "verified",
        "day": day,
        "tick": expected_tick,
        "population": checkpoint["state"]["metrics"]["population"],
        "births": checkpoint["state"]["metrics"]["births"],
        "control_births": report["division_disabled_control"]["births"],
        "state_sha256": checkpoint["sha256"],
        "daily_sha256": report["sha256"],
    }
    if result["control_births"] != 0:
        raise ValueError("Control produced unexpected births")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--day", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args(argv)
    print(json.dumps(inspect_day(args.state_dir, day=args.day), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

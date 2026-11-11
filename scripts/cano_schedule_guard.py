"""Fail-open freshness guard for scheduled bounded colony cycles."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

REPORT_URL = (
    "https://raw.githubusercontent.com/aydinefe2025-svg/"
    "Benim-AI-asistan-m/cano-latest/colony-cycle.json"
)
MAX_REPORT_AGE = timedelta(minutes=50)
MAX_REPORT_BYTES = 1_000_000
EXPECTED_MODE = "bounded_virtual_reproduction_with_held_out_validation"
EXPECTED_ROLES = {"evidence", "generation", "continuity", "security"}


def _is_complete_report(report: object) -> bool:
    """Only let a structurally validated published result suppress a cycle."""
    if not isinstance(report, dict):
        return False
    if (report.get("db_integrity") != "ok"
            or report.get("mode") != EXPECTED_MODE
            or report.get("scope") != "authorized_github_runner"):
        return False

    cycle = report.get("cycle")
    if not isinstance(cycle, dict):
        return False
    tick = cycle.get("tick_id")
    if type(tick) is not int or tick < 1:
        return False
    if (report.get("stored_ticks") != tick
            or report.get("verified_tick_id") != tick
            or cycle.get("state") != "proposed"):
        return False

    generation = report.get("virtual_generation")
    if not isinstance(generation, dict) or generation.get("generation_id") != tick:
        return False
    if generation.get("lesson_status") not in {"transferred", "rejected"}:
        return False

    continuity = report.get("continuity")
    if not isinstance(continuity, dict):
        return False
    if continuity.get("had_prior_state") is True:
        if (continuity.get("increment_verified") is not True
                or continuity.get("previous_tick_id") != tick - 1
                or continuity.get("previous_tick_count") != tick - 1):
            return False
    elif continuity.get("had_prior_state") is not False:
        return False

    specialists = report.get("specialist_agents")
    roles = specialists.get("roles") if isinstance(specialists, dict) else None
    if (not isinstance(roles, list)
            or specialists.get("status") != "passed"
            or specialists.get("launched") != len(EXPECTED_ROLES)):
        return False
    if {item.get("role") for item in roles if isinstance(item, dict)} != EXPECTED_ROLES:
        return False
    return all(
        isinstance(item, dict)
        and item.get("status") == "passed"
        and item.get("execution") == "isolated_read_only_subprocess"
        and item.get("model_calls") == 0
        for item in roles
    )


def should_run_cycle(
    event_name: str,
    report_payload: bytes | str | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Run manual/push requests and fail open for stale or invalid reports."""
    if event_name != "schedule":
        return True
    if report_payload is None:
        return True
    try:
        payload_size = len(report_payload.encode("utf-8") if isinstance(report_payload, str)
                           else report_payload)
        if payload_size > MAX_REPORT_BYTES:
            return True
        report = json.loads(report_payload)
        if not _is_complete_report(report):
            return True
        timestamp = datetime.fromisoformat(str(report["timestamp"]).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return True
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        age = current.astimezone(timezone.utc) - timestamp.astimezone(timezone.utc)
        return age < timedelta(0) or age >= MAX_REPORT_AGE
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError):
        return True


def fetch_public_report() -> bytes | None:
    request = Request(REPORT_URL, headers={"User-Agent": "CANO-freshness-guard"})
    try:
        with urlopen(request, timeout=8) as response:
            if response.status != 200:
                return None
            payload = response.read(MAX_REPORT_BYTES + 1)
        return payload if len(payload) <= MAX_REPORT_BYTES else None
    except Exception:
        # The report is public and contains no credentials. Fail open so a read
        # outage triggers the bounded cycle instead of silently suppressing it.
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args()
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    payload = fetch_public_report() if event_name == "schedule" else None
    run_cycle = should_run_cycle(event_name, payload)
    value = "true" if run_cycle else "false"
    if args.output:
        with Path(args.output).open("a", encoding="utf-8") as output:
            output.write(f"run_cycle={value}\n")
    print(f"CANO freshness guard: run_cycle={value}; event={event_name or 'unknown'}")


if __name__ == "__main__":
    main()

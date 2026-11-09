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


def should_run_cycle(
    event_name: str,
    report_payload: bytes | str | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Run every manual/push request and fail open for stale or invalid reports."""
    if event_name != "schedule":
        return True
    if report_payload is None:
        return True
    try:
        report = json.loads(report_payload)
        timestamp = datetime.fromisoformat(str(report["timestamp"]).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return True
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        age = current.astimezone(timezone.utc) - timestamp.astimezone(timezone.utc)
        return age < timedelta(0) or age >= MAX_REPORT_AGE
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return True


def fetch_public_report() -> bytes | None:
    request = Request(REPORT_URL, headers={"User-Agent": "CANO-freshness-guard"})
    try:
        with urlopen(request, timeout=8) as response:
            if response.status != 200:
                return None
            payload = response.read(1_000_001)
        return payload if len(payload) <= 1_000_000 else None
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

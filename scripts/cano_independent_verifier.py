"""Run CANO's free read-only live acceptance probes and emit a redacted receipt.

Usage:
    python -m scripts.cano_independent_verifier --output /tmp/cano-verification.json

This program never authenticates to user accounts, edits code or deploys.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.cano_continuous_verifier import run_checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        import requests
        report = run_checks(requests.get)
    except Exception:
        # Redact any future unexpected startup import or network errors.
        report = {
            "verdict": "failed",
            "checks": {
                "public_startup": {"ok": False},
                "current_weather_failover": {"ok": False},
                "dated_forecast_failover": {"ok": False},
            },
            "failures": [
                "public_startup", "current_weather_failover",
                "dated_forecast_failover",
            ],
            "scope": {
                "authenticated_e2e": False,
                "primary_weather_provider_simulated_unavailable": True,
                "third_party_credentials_sent": False,
            },
        }
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["verdict"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())

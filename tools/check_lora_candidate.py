"""Run the non-activating LoRA evaluation gate on three stored JSON reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.lora_candidate_gate import candidate_gate


def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("evaluation must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="baseline evaluation JSON")
    parser.add_argument("--candidate", required=True, help="candidate evaluation JSON")
    parser.add_argument("--safety", required=True, help="candidate safety evaluation JSON")
    args = parser.parse_args()
    try:
        result = candidate_gate(
            load(args.baseline), load(args.candidate), load(args.safety)
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        print(json.dumps({
            "decision": "preflight_failed",
            "error": "evaluation input could not be read or validated",
        }))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["decision"] == "eligible_for_human_review" else 1


if __name__ == "__main__":
    sys.exit(main())


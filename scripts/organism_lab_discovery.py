"""Run one bounded digital-lab candidate search and save its auditable report."""
import argparse
import json
from pathlib import Path

from organism_lab.discovery_sweep import (run_discovery_sweep, save_discovery_sweep,
                                          validate_discovery_sweep)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("organism_lab_output/discovery-sweep.json"))
    args = parser.parse_args(argv)
    report = run_discovery_sweep()
    saved = save_discovery_sweep(report, args.output)
    validate_discovery_sweep(saved)
    print(json.dumps({"status": saved["status"], "candidate": saved["selected_candidate"],
                      "confirmation": saved["confirmation"], "output": str(args.output)},
                     ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


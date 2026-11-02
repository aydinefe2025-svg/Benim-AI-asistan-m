"""Command-line experiment runner with deterministic JSON and CSV output."""
import argparse
import json
from pathlib import Path
from .experiments import run_experiment, to_csv
from .lineage import run_lineage, evaluate_improvement
from .shared_world import run_shared_world

def report(*, seed=0, steps=20, energy=40, materials=12, resources=10):
    if type(steps) is not int or not 0 <= steps <= 10000:
        raise ValueError("Invalid steps")
    evolution = run_experiment(seed=seed, steps=steps, resources=resources)
    lineage = run_lineage(seed=seed, steps=steps, resources=resources)
    shared = run_shared_world(steps=steps, energy=energy, materials=materials)
    return {"parameters": {"seed": seed, "steps": steps, "energy": energy,
                           "materials": materials, "resources": resources},
            "evolution": evolution, "lineage_summary": {
                "ever_born": lineage["ever_born"],
                "max_generation_ever": lineage["max_generation_ever"],
                **evaluate_improvement(lineage)},
            "shared_world": shared}

def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline digital organism laboratory")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--energy", type=int, default=40)
    parser.add_argument("--materials", type=int, default=12)
    parser.add_argument("--resources", type=int, default=10)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--csv", type=Path, help="Export evolution time series as CSV")
    args = parser.parse_args(argv)
    result = report(seed=args.seed, steps=args.steps, energy=args.energy,
                    materials=args.materials, resources=args.resources)
    payload = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        # csv.DictWriter emits CRLF. Disable pathlib's Windows newline
        # translation so exported rows are not written as CRCRLF.
        args.csv.write_text(to_csv(result["evolution"]), encoding="utf-8", newline="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())



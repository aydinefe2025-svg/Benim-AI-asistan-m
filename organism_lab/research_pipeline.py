"""Reproducible offline research pipeline using the existing digital colony.

Invoke explicitly: python -m organism_lab.research_pipeline [output-directory]
No external requests, model training, physical robot actions, or paid services.
"""
import json
import sys
from pathlib import Path
from .supervisor import Supervisor
from .shared_world import run_shared_world
from .core import grid_route
from .audit_store import read_audit


def run_pipeline(output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = output_dir / "tasks.jsonl"
    tasks = [("robotics", "simulate shared-world resources"),
             ("code", "verify grid path"),
             ("research", "summarize deterministic experiment")]

    def world(_):
        return json.dumps(run_shared_world(steps=20, energy=40, materials=12), sort_keys=True)

    def path(_):
        return json.dumps(grid_route(4, 4, (0, 0), (3, 3), obstacles=((1, 1),)))

    def summary(_):
        result = run_shared_world(steps=20, energy=40, materials=12)
        return json.dumps({"steps": len(result["history"]), "robots": result["robots"],
                           "organisms": result["organisms"]}, sort_keys=True)

    def verify_world(task, output):
        result = json.loads(output)
        if len(result["history"]) != 20 or result["energy_left"] < 0 or result["materials_left"] < 0:
            raise ValueError("World invariant failed")
        return "world-budget-and-length-checked"

    def verify_path(task, output):
        route = json.loads(output)
        if not route or route[0] != [0, 0] or route[-1] != [3, 3] or [1, 1] in route:
            raise ValueError("Path invariant failed")
        return "route-endpoints-and-obstacle-checked"

    def verify_summary(task, output):
        result = json.loads(output)
        expected_world = run_shared_world(steps=20, energy=40, materials=12)
        expected = {"steps": len(expected_world["history"]), "robots": expected_world["robots"],
                    "organisms": expected_world["organisms"]}
        if result != expected:
            raise ValueError("Summary mismatch")
        return "summary-recomputed"

    result = Supervisor().run(tasks,
                              {"robotics": world, "code": path, "research": summary},
                              {"robotics": verify_world, "code": verify_path,
                               "research": verify_summary}, audit_path=audit)
    if result["failed"]:
        raise RuntimeError("Pipeline has tasks that failed their injected checks")
    report = {"pipeline": "offline-research-v1", "tasks": result,
              "audit_records": len(read_audit(audit))}
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run_pipeline(sys.argv[1] if len(sys.argv) > 1 else "organism_lab_output"), ensure_ascii=False))

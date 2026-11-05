"""Generate and verify reproducible virtual-organism experiment evidence.

Offline, deterministic; models digital agents, not living organisms.
Run: python -m organism_lab.experiment_report [output_dir]
Verify: python -m organism_lab.experiment_report --verify [output_dir]
"""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from .evolution_experiments import compare_experiments


def _json_bytes(document):
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _hash(blob):
    return hashlib.sha256(blob).hexdigest()


def _atomic_write(destination, blob):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".experiment-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_documents():
    comparison = compare_experiments(seeds=tuple(range(1, 13)),
                                     steps=120, capacity=48, resources=16)
    rows = [
        {"seed": result["seed"], "population": result["final"]["population"],
         "births": result["final"]["births"], "deaths": result["final"]["deaths"],
         "max_generation": result["final"]["max_generation"],
         "mean_efficiency": result["final"]["mean_efficiency"],
         "result_sha256": result["sha256"]}
        for result in comparison["results"]
    ]
    summary = {
        "model": "digital-organism-comparison-v1",
        "description": "Synthetic deterministic evolution; not physical or biological experimentation",
        "runs": comparison["runs"],
        "steps_per_run": 120,
        "capacity": 48,
        "resources_per_tick": 16,
        "mean_final_population": comparison["mean_final_population"],
        "mean_births": comparison["mean_births"],
        "experiments": rows,
    }
    return {"experiment_results.json": comparison, "experiment_summary.json": summary}


def generate_report(output_dir):
    root = Path(output_dir)
    documents = build_documents()
    blobs = {name: _json_bytes(doc) for name, doc in documents.items()}
    manifest = {
        "schema": "digital-organism-evidence-v1",
        "checksums": {name: _hash(data) for name, data in sorted(blobs.items())},
        "verification": "recompute-all-experiments-and-compare",
    }
    for name, data in blobs.items():
        _atomic_write(root / name, data)
    _atomic_write(root / "experiment_manifest.json", _json_bytes(manifest))
    verify_report(root)
    return documents["experiment_summary.json"]


def verify_report(output_dir):
    root = Path(output_dir)
    manifest = json.loads((root / "experiment_manifest.json").read_text(encoding="utf-8"))
    expected = build_documents()
    if manifest.get("schema") != "digital-organism-evidence-v1":
        raise ValueError("Incorrect experiment schema")
    if set(manifest.get("checksums", {})) != set(expected):
        raise ValueError("Incomplete manifest")
    for name, document in expected.items():
        actual_bytes = (root / name).read_bytes()
        if _hash(actual_bytes) != manifest["checksums"][name]:
            raise ValueError("Checksum mismatch: " + name)
        if actual_bytes != _json_bytes(document):
            raise ValueError("Non-reproducible experiment: " + name)
    return {"verified": True, "runs": expected["experiment_summary.json"]["runs"],
            "files": len(expected) + 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Verify previously saved experiments")
    parser.add_argument("output_dir", nargs="?", default="organism_evolution_output")
    args = parser.parse_args()
    result = verify_report(args.output_dir) if args.verify else generate_report(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

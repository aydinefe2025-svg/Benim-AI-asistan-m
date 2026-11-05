"""Run a reproducible, paired resource-sweep study of the digital organism model.

This is an actual computation over the simulator, not evidence about biological
organisms. Every resource level uses the same seeds for replication and control.
Raw per-seed outcomes are retained so summaries can be recomputed independently.
"""
import argparse
import csv
import json
import sqlite3
import statistics
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .digital_vm import GenomeWorld
from .providers import ProviderError, generate


DEFAULT_RESOURCES = (0, 2, 5, 10, 20)


def _validate(seeds, steps, resource_levels):
    if not isinstance(seeds, (tuple, list)) or not 2 <= len(seeds) <= 100:
        raise ValueError("Use between 2 and 100 paired seeds")
    if any(type(seed) is not int or seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("Seeds must be distinct non-negative integers")
    if type(steps) is not int or not 1 <= steps <= 1000:
        raise ValueError("Steps must be between 1 and 1000")
    if not isinstance(resource_levels, (tuple, list)) or not 2 <= len(resource_levels) <= 12:
        raise ValueError("Use between 2 and 12 resource levels")
    if any(type(level) is not int or not 0 <= level <= 1000 for level in resource_levels):
        raise ValueError("Resource levels must be integers from 0 to 1000")
    if len(set(resource_levels)) != len(resource_levels):
        raise ValueError("Resource levels must be distinct")


def _run_world(seed, steps, resources, capacity, mutation_rate, allow_replication):
    world = GenomeWorld(seed=seed, capacity=capacity,
                        resources_per_tick=resources, mutation_rate=mutation_rate,
                        allow_replication=allow_replication)
    for _ in range(steps):
        world.step()
    return world.metrics()


def _mean_ci(values):
    mean_value = statistics.mean(values)
    if len(values) < 2:
        return {"mean": mean_value, "ci95_low": None, "ci95_high": None}
    margin = 1.96 * statistics.stdev(values) / (len(values) ** 0.5)
    return {"mean": mean_value, "ci95_low": mean_value - margin,
            "ci95_high": mean_value + margin}


def run_study(*, seeds=tuple(range(30)), steps=100,
              resource_levels=DEFAULT_RESOURCES, capacity=64, mutation_rate=0.02):
    """Compare an executing self-copying genome with a division-disabled control."""
    _validate(seeds, steps, resource_levels)
    if type(capacity) is not int or not 2 <= capacity <= 256:
        raise ValueError("Capacity must be between 2 and 256")
    if not isinstance(mutation_rate, (int, float)) or isinstance(mutation_rate, bool) or not 0 <= mutation_rate <= 1:
        raise ValueError("Mutation rate must be between 0 and 1")
    rows = []
    summaries = []
    for resources in resource_levels:
        differences = []
        populations = []
        births = []
        generations = []
        survival = []
        control_populations = []
        unique_genomes = []
        for seed in seeds:
            experiment = _run_world(seed, steps, resources, capacity, mutation_rate, True)
            control = _run_world(seed, steps, resources, capacity, mutation_rate, False)
            difference = experiment["population"] - control["population"]
            differences.append(difference)
            populations.append(experiment["population"])
            births.append(experiment["births"])
            generations.append(experiment["max_generation"])
            survival.append(experiment["population"] > 0)
            control_populations.append(control["population"])
            unique_genomes.append(experiment["unique_genomes"])
            rows.append({"resource_per_tick": resources, "seed": seed,
                         "replication_population": experiment["population"],
                         "control_population": control["population"],
                         "paired_population_difference": difference,
                         "births": experiment["births"],
                         "deaths": experiment["deaths"],
                         "max_generation": experiment["max_generation"],
                         "unique_genomes": experiment["unique_genomes"],
                         "replicators": experiment["replicators"]})
        difference_stats = _mean_ci(differences)
        summaries.append({
            "resource_per_tick": resources,
            "paired_seeds": len(seeds),
            "replication_final_population_mean": statistics.mean(populations),
            "control_final_population_mean": statistics.mean(control_populations),
            "replication_survival_rate": sum(survival) / len(survival),
            "mean_births": statistics.mean(births),
            "mean_max_generation": statistics.mean(generations),
            "mean_unique_genomes": statistics.mean(unique_genomes),
            "paired_population_difference": difference_stats,
        })
    return {
        "schema": "organism-lab-genome-replication-study-v1",
        "design": {"steps": steps, "capacity": capacity, "seeds": list(seeds),
                   "resource_levels_per_tick": list(resource_levels),
                   "mutation_rate": mutation_rate,
                   "genome": "COPY_REST then DIVIDE; children inherit the instruction sequence with bounded point mutation",
                   "control": "same genome/resources/capacity/steps/seeds; division disabled",
                   "primary_metric": "paired final population difference (executing replication minus control)"},
        "results": summaries,
        "observations": rows,
        "interpretation_limits": [
            "All outcomes are generated by this deterministic toy simulator, not living organisms.",
            "Confidence intervals describe variation across the selected simulator seeds only.",
            "This study does not establish real-world biological or robot behavior.",
            "The local model commentary is unverified and kept separate from computed measurements."
        ]
    }


def summarize_with_local_model(report):
    """Ask the local model to restate metric checks, then compare them in code."""
    compact = {"design": report["design"], "results": report["results"]}
    prompt = (
        "Return JSON only with exactly this shape: {\"checks\":[{\"resource_per_tick\": integer, "
        "\"interval_contains_zero\": boolean, \"mean_difference_positive\": boolean}]}. "
        "Include one item for each resource level in input order. Copy no prose. "
        "These are simulator metrics, not biological evidence.\n"
        + json.dumps(compact, ensure_ascii=False, sort_keys=True)
    )
    try:
        response = generate(prompt, "ollama")
        raw = response["text"].strip()
        if raw.startswith("```json") and raw.endswith("```"):
            raw = raw[7:-3].strip()
        candidate = json.loads(raw)
        expected = [{
            "resource_per_tick": result["resource_per_tick"],
            "interval_contains_zero": (
                result["paired_population_difference"]["ci95_low"] <= 0
                <= result["paired_population_difference"]["ci95_high"]
            ),
            "mean_difference_positive": result["paired_population_difference"]["mean"] > 0,
        } for result in report["results"]]
        if candidate != {"checks": expected}:
            return {"status": "rejected_inconsistent", "provider": response["provider"],
                    "text": "The local model's metric checklist did not match computed values."}
        return {"status": "metric_consistent", "provider": response["provider"],
                "checks": expected,
                "text": "The local model's structured checklist matched the computed metrics."}
    except (ProviderError, OSError, ValueError) as exc:
        return {"status": "unavailable", "provider": "ollama",
                "reason": type(exc).__name__, "text": ""}


def save_study(report, output_dir, *, model_commentary=None):
    """Persist JSON, per-seed CSV, and a local SQLite run record."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    study_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    document = {**report, "study_id": study_id, "created_at": created_at,
                "model_commentary": model_commentary or {"status": "not_requested", "text": ""}}
    json_path = output_dir / f"{study_id}.json"
    csv_path = output_dir / f"{study_id}.csv"
    db_path = output_dir / "research_studies.sqlite3"
    json_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(report["observations"][0]))
        writer.writeheader()
        writer.writerows(report["observations"])
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS studies (
                study_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                report_json TEXT NOT NULL, commentary_json TEXT NOT NULL)""")
            connection.execute("INSERT INTO studies VALUES (?, ?, ?, ?)",
                               (study_id, created_at,
                                json.dumps(report, ensure_ascii=False, sort_keys=True),
                                json.dumps(document["model_commentary"], ensure_ascii=False, sort_keys=True)))
    finally:
        connection.close()
    return {"study_id": study_id, "json_path": str(json_path),
            "csv_path": str(csv_path), "database_path": str(db_path),
            "created_at": created_at}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Paired digital-genome replication resource study")
    parser.add_argument("--output", type=Path, default=Path("organism_lab_output"))
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--resources", type=int, nargs="+", default=list(DEFAULT_RESOURCES))
    parser.add_argument("--model-commentary", action="store_true",
                        help="ask configured local Ollama model for unverified commentary")
    args = parser.parse_args(argv)
    report = run_study(seeds=tuple(range(args.seeds)), steps=args.steps,
                       resource_levels=tuple(args.resources))
    commentary = summarize_with_local_model(report) if args.model_commentary else None
    saved = save_study(report, args.output, model_commentary=commentary)
    # Import after module initialization to avoid a cycle with run_study.
    from .study_verifier import verify_saved_study
    receipt = verify_saved_study(saved)
    print(json.dumps({"study_id": saved["study_id"], "files": saved,
                      "verification_receipt": receipt,
                      "results": report["results"], "model_commentary": commentary},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

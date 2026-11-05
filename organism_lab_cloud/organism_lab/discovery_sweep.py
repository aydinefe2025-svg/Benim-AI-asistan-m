"""Bounded, reproducible search for simulation-only adaptation candidates.

The screening seeds select a candidate; disjoint confirmation seeds test it.
Every label is limited to this toy simulator and is not biological evidence.
"""
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .digital_vm import COPY_REST, DIVIDE, GenomeWorld, TASK_A, TASK_B


DEFAULT_MUTATION_RATES = (0.0, 0.01, 0.02, 0.08, 0.2)


def _validate(*, screening_seeds, confirmation_seeds, mutation_rates, steps, shift_tick):
    for name, seeds in (("screening_seeds", screening_seeds),
                         ("confirmation_seeds", confirmation_seeds)):
        if not isinstance(seeds, (tuple, list)) or not 3 <= len(seeds) <= 100:
            raise ValueError(f"{name} must contain 3 to 100 seeds")
        if any(type(seed) is not int or seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
            raise ValueError(f"{name} must contain distinct nonnegative integers")
    if set(screening_seeds) & set(confirmation_seeds):
        raise ValueError("Screening and confirmation seeds must be disjoint")
    if not isinstance(mutation_rates, (tuple, list)) or not 2 <= len(mutation_rates) <= 8:
        raise ValueError("Use 2 to 8 mutation rates")
    if (any(isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 <= rate <= 1
            for rate in mutation_rates) or len(set(mutation_rates)) != len(mutation_rates)
            or 0.0 not in mutation_rates):
        raise ValueError("Mutation rates must be distinct values from 0 to 1 and include 0")
    if type(steps) is not int or not 10 <= steps <= 500:
        raise ValueError("Steps must be from 10 to 500")
    if type(shift_tick) is not int or not 1 <= shift_tick < steps:
        raise ValueError("The environment shift must occur before the final step")


def _final_task_b_share(*, seed, mutation_rate, steps, shift_tick, capacity, resources_per_tick):
    world = GenomeWorld(
        seed=seed, capacity=capacity, resources_per_tick=resources_per_tick,
        mutation_rate=mutation_rate, initial_genome=(COPY_REST, TASK_A, DIVIDE),
        environment=TASK_A, task_reward=2,
    )
    for tick in range(1, steps + 1):
        if tick == shift_tick + 1:
            world.set_environment(TASK_B)
        world.step()
    population = len(world.organisms)
    return (sum(TASK_B in organism.genome for organism in world.organisms) / population
            if population else 0.0)


def _summarize_differences(differences):
    mean = statistics.mean(differences)
    if len(differences) < 2:
        low = high = None
    else:
        margin = 1.96 * statistics.stdev(differences) / (len(differences) ** 0.5)
        low, high = mean - margin, mean + margin
    return {"paired_seeds": len(differences), "mean_difference": mean,
            "approx_ci95_low": low, "approx_ci95_high": high}


def _compare_rates(rate, seeds, *, steps, shift_tick, capacity, resources_per_tick):
    differences = []
    for seed in seeds:
        treatment = _final_task_b_share(
            seed=seed, mutation_rate=rate, steps=steps, shift_tick=shift_tick,
            capacity=capacity, resources_per_tick=resources_per_tick)
        control = _final_task_b_share(
            seed=seed, mutation_rate=0.0, steps=steps, shift_tick=shift_tick,
            capacity=capacity, resources_per_tick=resources_per_tick)
        differences.append(treatment - control)
    return _summarize_differences(differences)


def run_discovery_sweep(*, screening_seeds=tuple(range(10)),
                        confirmation_seeds=tuple(range(100, 130)),
                        mutation_rates=DEFAULT_MUTATION_RATES, steps=120,
                        shift_tick=40, capacity=64, resources_per_tick=1):
    """Screen mutation rates, then evaluate the top positive screen on held-out seeds."""
    _validate(screening_seeds=screening_seeds, confirmation_seeds=confirmation_seeds,
              mutation_rates=mutation_rates, steps=steps, shift_tick=shift_tick)
    if type(capacity) is not int or not 2 <= capacity <= 256:
        raise ValueError("Capacity must be between 2 and 256")
    if type(resources_per_tick) is not int or not 0 <= resources_per_tick <= 100:
        raise ValueError("Resources per tick must be between 0 and 100")

    screening = [{"mutation_rate": float(rate), **_compare_rates(
        rate, screening_seeds, steps=steps, shift_tick=shift_tick,
        capacity=capacity, resources_per_tick=resources_per_tick)}
        for rate in mutation_rates]
    nonzero = [row for row in screening if row["mutation_rate"] > 0]
    selected = max(nonzero, key=lambda row: row["mean_difference"])
    provisional = selected["mean_difference"] > 0
    confirmation = None
    robustness = []
    status = "no_positive_screening_candidate"
    if provisional:
        confirmation = {"mutation_rate": selected["mutation_rate"], **_compare_rates(
            selected["mutation_rate"], confirmation_seeds, steps=steps,
            shift_tick=shift_tick, capacity=capacity,
            resources_per_tick=resources_per_tick)}
        low, high = confirmation["approx_ci95_low"], confirmation["approx_ci95_high"]
        status = "replicated_simulation_candidate" if low is not None and low > 0 else "not_reproduced_on_confirmation_seeds"
        alternative_shifts = sorted({max(1, steps // 4), steps // 2,
                                     min(steps - 1, (3 * steps) // 4)} - {shift_tick})
        robustness = [{"shift_tick": alternative_shift, **_compare_rates(
            selected["mutation_rate"], confirmation_seeds, steps=steps,
            shift_tick=alternative_shift, capacity=capacity,
            resources_per_tick=resources_per_tick)}
            for alternative_shift in alternative_shifts]
    supported_shift_count = sum(
        row["approx_ci95_low"] is not None and row["approx_ci95_low"] > 0
        for row in robustness
    )
    robustness_assessment = {
        "tested_shift_count": len(robustness),
        "positive_shift_count": supported_shift_count,
        "summary": ("Aday, sınanan alternatif zamanlamaların tümünde olumlu kaldı."
                    if robustness and supported_shift_count == len(robustness)
                    else "Aday, sınanan alternatif zamanlamaların bazılarında olumlu kalmadı."
                    if robustness else "Alternatif zamanlama koşulu hesaplanamadı."),
    }

    return {
        "schema": "organism-lab-bounded-discovery-sweep-v1",
        "status": status,
        "design": {"steps": steps, "shift_tick": shift_tick, "capacity": capacity,
                   "resources_per_tick": resources_per_tick,
                   "screening_seeds": list(screening_seeds),
                   "confirmation_seeds": list(confirmation_seeds),
                   "mutation_rates": [float(rate) for rate in mutation_rates],
                   "primary_metric": "paired difference in final TASK_B genome share vs zero-mutation control"},
        "screening": screening,
        "selected_candidate": selected if provisional else None,
        "confirmation": confirmation,
        "robustness": robustness,
        "interpretation": {
            "summary": ("A candidate repeated on separate simulation seeds." if status == "replicated_simulation_candidate"
                        else "A screening candidate did not clear the confirmation threshold on held-out seeds." if provisional
                        else "No positive candidate was found in this bounded screening run."),
            "evidence_level": "replicated_within_toy_simulator" if status == "replicated_simulation_candidate" else "exploratory_simulation_only",
            "robustness": robustness_assessment,
            "interval_method": "approximate normal 95% interval over paired seed differences; exploratory, not adjusted for model misspecification",
            "limits": ["This is a bounded digital toy simulation, not a physical or biological experiment.",
                       "A repeated candidate is not a verified scientific discovery or a real-world causal claim.",
                       "Confirmation seeds are kept separate from screening seeds to reduce selection bias."],
        },
    }


def save_discovery_sweep(report, path):
    """Save an immutable run and atomically refresh the convenience latest file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex
    document = {**report, "generated_at": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id}
    payload = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\\n"

    history_dir = target.parent / "discovery-sweeps"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / f"discovery-sweep-{run_id}.json"

    def write_atomic(destination):
        temporary = destination.with_name(destination.name + f".{uuid4().hex}.tmp")
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    write_atomic(history_path)
    if json.loads(history_path.read_text(encoding="utf-8")) != document:
        raise OSError("Versioned discovery report failed read-back verification")
    write_atomic(target)
    if json.loads(target.read_text(encoding="utf-8")) != document:
        raise OSError("Latest discovery report failed read-back verification")
    return document


def validate_discovery_sweep(document):
    """Recompute the bounded sweep and reject edited or inconsistent metrics."""
    if not isinstance(document, dict) or document.get("schema") != "organism-lab-bounded-discovery-sweep-v1":
        raise ValueError("Unsupported discovery report")
    design = document.get("design")
    if not isinstance(design, dict):
        raise ValueError("Missing experiment design")
    expected = run_discovery_sweep(
        screening_seeds=tuple(design.get("screening_seeds", ())),
        confirmation_seeds=tuple(design.get("confirmation_seeds", ())),
        mutation_rates=tuple(design.get("mutation_rates", ())),
        steps=design.get("steps"), shift_tick=design.get("shift_tick"),
        capacity=design.get("capacity"), resources_per_tick=design.get("resources_per_tick"),
    )
    for field in ("status", "design", "screening", "selected_candidate", "confirmation",
                  "robustness", "interpretation"):
        if document.get(field) != expected[field]:
            raise ValueError("Discovery report does not match deterministic recomputation")
    return True


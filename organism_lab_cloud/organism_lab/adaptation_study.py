"""Paired, reproducible environment-shift experiment for digital genomes.

This tests evolutionary adaptation in a small simulator, not learning by an AI
model or behavior of biological organisms.
"""
import json
import statistics
from pathlib import Path

from .digital_vm import COPY_REST, DIVIDE, GenomeWorld, TASK_A, TASK_B


def _mean_ci(values, *, bounds=None):
    mean = statistics.mean(values)
    if len(values) < 2:
        return {"mean": mean, "ci95_low": None, "ci95_high": None}
    margin = 1.96 * statistics.stdev(values) / (len(values) ** 0.5)
    low, high = mean - margin, mean + margin
    if bounds is not None:
        low, high = max(bounds[0], low), min(bounds[1], high)
    return {"mean": mean, "ci95_low": low, "ci95_high": high}


def run_adaptation_study(*, seeds=tuple(range(30)), steps=120, shift_tick=40,
                         capacity=64, resources_per_tick=1, mutation_rate=0.08):
    if not isinstance(seeds, (tuple, list)) or not 2 <= len(seeds) <= 100:
        raise ValueError("Use between 2 and 100 paired seeds")
    if any(type(seed) is not int or seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("Seeds must be distinct non-negative integers")
    if type(steps) is not int or not 10 <= steps <= 1000:
        raise ValueError("Steps must be between 10 and 1000")
    if type(shift_tick) is not int or not 1 <= shift_tick < steps:
        raise ValueError("shift_tick must be before the final step")
    if type(capacity) is not int or not 2 <= capacity <= 256:
        raise ValueError("Capacity must be between 2 and 256")
    if type(resources_per_tick) is not int or not 0 <= resources_per_tick <= 1000:
        raise ValueError("Invalid resource budget")
    if isinstance(mutation_rate, bool) or not isinstance(mutation_rate, (int, float)) or not 0 <= mutation_rate <= 1:
        raise ValueError("Mutation rate must be between 0 and 1")

    observations = []
    for seed in seeds:
        for arm, rate, allow_replication in (
                ("mutation", float(mutation_rate), True),
                ("no_mutation", 0.0, True),
                ("no_reproduction", 0.0, False),
            ):
            world = GenomeWorld(seed=seed, capacity=capacity,
                                resources_per_tick=resources_per_tick,
                                mutation_rate=rate,
                                allow_replication=allow_replication,
                                initial_genome=(COPY_REST, TASK_A, DIVIDE),
                                environment=TASK_A, task_reward=2)
            lag = None
            for tick in range(1, steps + 1):
                if tick == shift_tick + 1:
                    world.set_environment(TASK_B)
                births_before, deaths_before = world.births, world.deaths
                metrics = world.step()
                if tick > shift_tick and metrics["population"]:
                    share_b = sum(TASK_B in item.genome for item in world.organisms) / metrics["population"]
                    if lag is None and share_b >= 0.5:
                        lag = tick - shift_tick
                else:
                    share_b = 0.0
                row = {"seed": seed, "arm": arm, "tick": tick,
                       "environment": "B" if tick > shift_tick else "A",
                       "population": metrics["population"],
                       "task_b_share": share_b,
                       "unique_genomes": metrics["unique_genomes"],
                       "births": metrics["births"],
                       "births_this_tick": metrics["births"] - births_before,
                       "deaths": metrics["deaths"],
                       "deaths_this_tick": metrics["deaths"] - deaths_before,
                       "max_generation": metrics["max_generation"]}
                if tick == steps:
                    generation_fitness = {}
                    for organism in world.organisms:
                        group = generation_fitness.setdefault(organism.generation, [])
                        group.append(int((TASK_B if tick > shift_tick else TASK_A) in organism.genome))
                    row["fitness_distribution_by_generation"] = [
                        {"generation": generation, "organisms": len(scores),
                         "fitness_counts": {"0": scores.count(0), "1": scores.count(1)},
                         "mean_environment_fitness": statistics.mean(scores)}
                        for generation, scores in sorted(generation_fitness.items())
                    ]
                observations.append(row)
            observations[-1]["adaptation_lag_ticks"] = lag

    final = [row for row in observations if row["tick"] == steps]
    rows_by_seed_arm = {(row["seed"], row["arm"]): row for row in final}
    summaries = []
    for arm in ("mutation", "no_mutation", "no_reproduction"):
        rows = [row for row in final if row["arm"] == arm]
        lags = [row["adaptation_lag_ticks"] for row in rows if row["adaptation_lag_ticks"] is not None]
        task_b_shares = [row["task_b_share"] for row in rows]
        summaries.append({"arm": arm, "paired_seeds": len(rows),
                          "final_population_mean": statistics.mean(row["population"] for row in rows),
                          "final_task_b_share_mean": statistics.mean(task_b_shares),
                          "final_task_b_share_ci95": _mean_ci(task_b_shares, bounds=(0.0, 1.0)),
                          "adapted_seed_rate": len(lags) / len(rows),
                          "adaptation_lag_mean_ticks": statistics.mean(lags) if lags else None,
                          "mean_unique_genomes": statistics.mean(row["unique_genomes"] for row in rows)})
    paired_differences = {}
    for control in ("no_mutation", "no_reproduction"):
        differences = [
            rows_by_seed_arm[(seed, "mutation")]["task_b_share"]
            - rows_by_seed_arm[(seed, control)]["task_b_share"]
            for seed in seeds
        ]
        paired_differences[control] = _mean_ci(differences, bounds=(-1.0, 1.0))
    return {"schema": "organism-lab-environment-shift-v1",
            "design": {"steps": steps, "shift_tick": shift_tick,
                       "capacity": capacity, "resources_per_tick": resources_per_tick,
                       "mutation_rate": float(mutation_rate), "seeds": list(seeds),
                       "founder_genome": [COPY_REST, TASK_A, DIVIDE],
                       "environment": "TASK_A switches to TASK_B; matching task instruction earns energy",
                       "arms": ["mutation", "no_mutation", "no_reproduction"],
                       "primary_metric": "final share of surviving population carrying TASK_B",
                       "paired_holdout_metric": "paired per-seed difference in final TASK_B share; 95% normal-approximation CI",
                       "adaptation_acceptance_criterion": "The mutation arm's paired 95% CI lower bound must exceed zero against both controls; otherwise report no demonstrated adaptation.",
                       "holdout_warning": "TASK_B is the shifted environment under test; the toy model has no external validation data"},
            "paired_task_b_share_differences_mutation_minus_controls": paired_differences,
            "adaptation_criterion": {
                "description": "Evidence requires the paired 95% CI lower bound for mutation-minus-control TASK_B share to exceed zero against both controls.",
                "met": all(result["ci95_low"] is not None and result["ci95_low"] > 0
                           for result in paired_differences.values()),
            },
            "results": summaries, "observations": observations,
            "interpretation_limits": [
                "This is simulated evolutionary selection, not an AI model updating its weights.",
                "The task and reward are engineered toy rules, not biological evidence.",
                "Seed variation estimates simulator variability only; external validity is not established."]}


def save_adaptation_study(report, output_path):
    """Create an immutable report atomically; never overwrite a different run."""
    import os
    import tempfile

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    def same_existing_report():
        if path.is_symlink() or not path.is_file():
            return False
        try:
            return json.loads(path.read_text(encoding="utf-8")) == report
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False

    if path.is_symlink():
        raise FileExistsError("Refusing to overwrite a report symlink")
    if path.exists():
        if same_existing_report():
            return path
        raise FileExistsError("Different adaptation report already saved")

    fd, temporary_name = tempfile.mkstemp(prefix=".adaptation-", suffix=".tmp",
                                         dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            # os.replace() silently destroyed prior data. This is create-if-absent.
            os.link(temporary_name, path)
        except FileExistsError:
            if path.is_symlink() or not same_existing_report():
                raise FileExistsError("Different adaptation report already saved")
    finally:
        os.unlink(temporary_name)
    return path

"""Paired, reproducible environment-shift experiment for digital genomes.

This tests evolutionary adaptation in a small simulator, not learning by an AI
model or behavior of biological organisms.
"""
import json
import statistics
from pathlib import Path

from .digital_vm import COPY_REST, DIVIDE, GenomeWorld, TASK_A, TASK_B


# Two-sided 95% Student-t critical values; df=30 is a conservative
# approximation for larger samples.
_T95 = (None, 12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365,
        2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131,
        2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069,
        2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042)


def _paired_effect(candidate, control):
    if len(candidate) != len(control) or len(candidate) < 2:
        raise ValueError("A paired interval needs at least two matching seeds")
    differences = [left - right for left, right in zip(candidate, control)]
    mean = statistics.mean(differences)
    standard_error = statistics.stdev(differences) / len(differences) ** 0.5
    df = len(differences) - 1
    critical = _T95[df] if df < len(_T95) else _T95[-1]
    margin = critical * standard_error
    return {"paired_seeds": len(differences), "mean_difference": mean,
            "approx_ci95_low": mean - margin,
            "approx_ci95_high": mean + margin,
            "positive_evidence": mean - margin > 0}


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
                ("reproduction_disabled", float(mutation_rate), False)):
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
                metrics = world.step()
                if tick > shift_tick and metrics["population"]:
                    share_b = sum(TASK_B in item.genome for item in world.organisms) / metrics["population"]
                    if lag is None and share_b >= 0.5:
                        lag = tick - shift_tick
                else:
                    share_b = 0.0
                observations.append({"seed": seed, "arm": arm, "tick": tick,
                                     "environment": "B" if tick > shift_tick else "A",
                                     "population": metrics["population"],
                                     "task_b_share": share_b,
                                     "unique_genomes": metrics["unique_genomes"],
                                     "births": metrics["births"],
                                     "max_generation": metrics["max_generation"]})
            observations[-1]["adaptation_lag_ticks"] = lag

    final = [row for row in observations if row["tick"] == steps]
    summaries = []
    for arm in ("mutation", "no_mutation", "reproduction_disabled"):
        rows = [row for row in final if row["arm"] == arm]
        lags = [row["adaptation_lag_ticks"] for row in rows if row["adaptation_lag_ticks"] is not None]
        summaries.append({"arm": arm, "paired_seeds": len(rows),
                          "final_population_mean": statistics.mean(row["population"] for row in rows),
                          "final_task_b_share_mean": statistics.mean(row["task_b_share"] for row in rows),
                          "adapted_seed_rate": len(lags) / len(rows),
                          "adaptation_lag_mean_ticks": statistics.mean(lags) if lags else None,
                          "mean_unique_genomes": statistics.mean(row["unique_genomes"] for row in rows)})
    by_arm_seed = {(row["arm"], row["seed"]): row["task_b_share"] for row in final}
    comparisons = []
    for index, (candidate_arm, control_arm) in enumerate((
            ("mutation", "no_mutation"),
            ("mutation", "reproduction_disabled"),
            ("no_mutation", "reproduction_disabled"))):
        comparisons.append({
            "candidate_arm": candidate_arm,
            "control_arm": control_arm,
            "comparison_role": "primary" if index == 0 else "exploratory",
            **_paired_effect(
                [by_arm_seed[(candidate_arm, seed)] for seed in seeds],
                [by_arm_seed[(control_arm, seed)] for seed in seeds]),
        })

    return {"schema": "organism-lab-environment-shift-v2",
            "design": {"steps": steps, "shift_tick": shift_tick,
                       "capacity": capacity, "resources_per_tick": resources_per_tick,
                       "mutation_rate": float(mutation_rate), "seeds": list(seeds),
                       "founder_genome": [COPY_REST, TASK_A, DIVIDE],
                       "environment": "TASK_A switches to TASK_B; matching task instruction earns energy",
                       "arms": ["mutation", "no_mutation", "reproduction_disabled"],
                       "primary_metric": "final share of surviving population carrying TASK_B",
                       "primary_comparison": "mutation vs no_mutation",
                       "secondary_comparisons": "exploratory; no multiplicity adjustment",
                       "interval_method": "paired Student-t 95% interval; conservative df=30 critical value above 30 pairs"},
            "results": summaries, "paired_comparisons": comparisons,
            "observations": observations,
            "interpretation_limits": [
                "This is simulated evolutionary selection, not an AI model updating its weights.",
                "The task and reward are engineered toy rules, not biological evidence.",
                "Seed variation estimates simulator variability only; external validity is not established."]}


def save_adaptation_study(report, output_path):
    """Write one complete JSON report atomically, without replacing another run."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    return path


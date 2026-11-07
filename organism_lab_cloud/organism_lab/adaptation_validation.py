"""Exploratory, bounded paired validation of simulated heritable adaptation.

Uses existing Organism Lab cloud digital_vm; no new organism engine, network,
external agents, or biological/robotic claims. Training environment changes A→B.
Holdout weakens B reward and freezes mutation; this tests robustness to a
*reward perturbation*, NOT generalization to a previously unseen task.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from math import comb
import hashlib
import json
from pathlib import Path
import statistics

from .digital_vm import COPY_REST, DIVIDE, TASK_A, TASK_B, GenomeWorld, execute_genome

SCHEMA = "cano-adaptation-validation-v1"
ARMS = ("mutation", "no_mutation", "no_division")
FOUNDER = (COPY_REST, TASK_A, DIVIDE)


def _valid(seeds, steps, shift_tick, holdout_steps, capacity, resources, mutation_rate):
    if not isinstance(seeds, (list, tuple)) or not 20 <= len(seeds) <= 100:
        raise ValueError("Must use 20-100 paired seeds")
    if any(type(s) is not int or s < 0 for s in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("Seeds must be distinct, non-negative integers")
    if type(steps) is not int or not 20 <= steps <= 300:
        raise ValueError("Invalid step budget")
    if type(shift_tick) is not int or not 1 <= shift_tick < steps:
        raise ValueError("Invalid shift tick")
    if type(holdout_steps) is not int or not 1 <= holdout_steps <= 50:
        raise ValueError("Invalid holdout budget")
    if type(capacity) is not int or not 2 <= capacity <= 64:
        raise ValueError("Invalid bounded population")
    if type(resources) is not int or not 0 <= resources <= 100:
        raise ValueError("Invalid resources")
    if type(mutation_rate) not in (int, float) or not 0 <= mutation_rate <= 1:
        raise ValueError("Invalid mutation rate")


def _functional_b(world):
    # A task marker is not sufficient: mutated dead programs can also contain TASK_B.
    return sum(TASK_B in i.genome and execute_genome(i.genome) is not None
               for i in world.organisms)


def _cohorts(world):
    grouped = {}
    for i in world.organisms:
        entry = grouped.setdefault(i.generation, {"population": 0, "unique_genomes": set(), "functional_task_b": 0})
        entry["population"] += 1
        entry["unique_genomes"].add(i.genome)
        entry["functional_task_b"] += int(TASK_B in i.genome and execute_genome(i.genome) is not None)
    return {str(k): {"population": v["population"], "unique_genomes": len(v["unique_genomes"]),
                     "functional_task_b": v["functional_task_b"]}
            for k, v in sorted(grouped.items())}


def _trial(seed, arm, steps, shift_tick, holdout_steps, capacity, resources, mutation_rate):
    world = GenomeWorld(seed=seed, capacity=capacity, resources_per_tick=resources,
                        mutation_rate=mutation_rate if arm == "mutation" else 0.0,
                        initial_genome=FOUNDER, allow_replication=arm != "no_division",
                        environment=TASK_A, task_reward=2)
    early = None
    for tick in range(1, steps + 1):
        if tick == shift_tick + 1:
            world.set_environment(TASK_B)
        world.step()
        if tick == shift_tick:
            early = world.metrics()
    final = world.metrics()
    fb = _functional_b(world)
    # Pre-registered performance: functional B genotype share; extinct = zero.
    score = fb / final["population"] if final["population"] else 0.0
    holdout = deepcopy(world)
    holdout.task_reward = 1  # independent weaker reward; not new genotype evolution
    holdout.mutation_rate = 0.0
    for _ in range(holdout_steps):
        holdout.step()
    after = holdout.metrics()
    return {"seed": seed, "arm": arm, "pre_shift": early, "final": final,
            "functional_task_b": fb, "functional_b_share": score,
            "cohorts": _cohorts(world), "holdout_population": after["population"],
            "holdout_functional_b_share": (_functional_b(holdout) / after["population"]
                                           if after["population"] else 0.0),
            "holdout_births_added": after["births"] - final["births"]}


def _mean_ci(values):
    avg = statistics.mean(values)
    margin = 1.96 * statistics.stdev(values) / len(values) ** .5 if len(values) > 1 else 0
    return {"mean": avg, "ci95_low": avg - margin, "ci95_high": avg + margin,
            "n": len(values), "method": "normal_approximation_paired_seeds"}


def run_validation(*, seeds=tuple(range(30)), steps=120, shift_tick=40,
                   holdout_steps=15, capacity=48, resources=1, mutation_rate=.08):
    """Three-arm seed-paired A→B model study with frozen-mutation reward holdout."""
    _valid(seeds, steps, shift_tick, holdout_steps, capacity, resources, mutation_rate)
    trials = [_trial(seed, arm, steps, shift_tick, holdout_steps, capacity, resources, mutation_rate)
              for seed in seeds for arm in ARMS]
    by_arm = {arm: [t for t in trials if t["arm"] == arm] for arm in ARMS}
    def values(arm, key):
        return [t[key] for t in by_arm[arm]]
    outcomes = []
    for arm in ARMS:
        items = by_arm[arm]
        outcomes.append({"arm": arm,
                         "mean_final_population": statistics.mean(t["final"]["population"] for t in items),
                         "mean_unique_genomes": statistics.mean(t["final"]["unique_genomes"] for t in items),
                         "mean_births": statistics.mean(t["final"]["births"] for t in items),
                         "mean_deaths": statistics.mean(t["final"]["deaths"] for t in items),
                         "mean_max_generation": statistics.mean(t["final"]["max_generation"] for t in items),
                         "extinction_fraction": sum(t["final"]["population"] == 0 for t in items)/len(items),
                         "functional_b_share": _mean_ci(values(arm, "functional_b_share")),
                         "holdout_population": _mean_ci(values(arm, "holdout_population")),
                         "holdout_functional_b_share": _mean_ci(values(arm, "holdout_functional_b_share"))})
    difference_b = _mean_ci([a - b for a, b in zip(values("mutation", "functional_b_share"),
                                                    values("no_mutation", "functional_b_share"))])
    difference_holdout = _mean_ci([a - b for a, b in zip(values("mutation", "holdout_population"),
                                                          values("no_mutation", "holdout_population"))])
    per_seed_b = [a - b for a, b in zip(values("mutation", "functional_b_share"),
                                           values("no_mutation", "functional_b_share"))]
    positive_seeds = sum(delta > 0 for delta in per_seed_b)
    negative_seeds = sum(delta < 0 for delta in per_seed_b)
    n_nonzero = positive_seeds + negative_seeds
    # Ties excluded. This exact one-sided sign test exposes sparse lucky seeds.
    sign_test_p = (sum(comb(n_nonzero, k) for k in range(positive_seeds, n_nonzero + 1))
                   / 2**n_nonzero) if n_nonzero else 1.0
    positive_seed_fraction = positive_seeds / len(seeds)
    diversity_gain = statistics.mean(t["final"]["unique_genomes"] for t in by_arm["mutation"]) - statistics.mean(t["final"]["unique_genomes"] for t in by_arm["no_mutation"])
    negative_control_pass = all(t["final"]["births"] == 0 for t in by_arm["no_division"])
    # Strict gate, deliberately allowed to FAIL; do not silently lower thresholds.
    gate = (difference_b["ci95_low"] > 0 and difference_holdout["ci95_low"] > 0
            and diversity_gain > 0 and negative_control_pass
            and positive_seed_fraction >= 0.5 and sign_test_p < 0.05)
    return {"schema": SCHEMA, "design": {"seeds": list(seeds), "steps": steps,
            "shift_tick": shift_tick, "holdout_steps": holdout_steps, "capacity": capacity,
            "resources_per_tick": resources, "mutation_rate": mutation_rate,
            "founder_genome": list(FOUNDER), "training": "TASK_A then TASK_B; matching instruction earns 2 energy",
            "holdout": f"Continue a copy for {holdout_steps} ticks with TASK_B reward 1, mutation frozen at 0; stress test, not unseen-task generalization",
            "arms": list(ARMS),
            "primary_metric": "paired final viable TASK_B program carrier share, extinct=0",
            "secondary_metric": "paired final population under lower-reward mutation-frozen holdout",
            "acceptance": "exploratory strict gate: both paired normal-approx 95% lower bounds >0, mean unique-genome gain >0, no-division zero births, >=50% paired seeds with positive functional B gain, one-sided exact sign p<0.05; otherwise not demonstrated"},
            "outcomes": outcomes, "paired_functional_b_gain": difference_b,
            "paired_holdout_population_gain": difference_holdout,
            "mean_unique_genomes_gain": diversity_gain,
            "positive_functional_b_seeds": positive_seeds,
            "negative_functional_b_seeds": negative_seeds,
            "tied_functional_b_seeds": len(seeds) - n_nonzero,
            "positive_functional_b_seed_fraction": positive_seed_fraction,
            "exact_one_sided_sign_p": sign_test_p,
            "negative_control_births_zero": negative_control_pass,
            "adaptation_demonstrated": gate, "trials": trials,
            "limits": ["Engineered deterministic digital VM; no biological organisms or LLM self-training.",
                       "Confidence intervals describe selected seeds, not general ecosystem uncertainty.",
                       "Holdout is a reduced TASK_B reward, not a previously unseen task.",
                       "The exploratory acceptance threshold was strengthened after inspecting a 30-seed pilot; this is not preregistered confirmation.",
                       "A positive gate would show adaptation only within these rules and seeds."]}


def _serialize(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def save_and_verify(report, path):
    """Atomically write a reproducible signed-by-digest report (not a signature)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"report": report, "sha256": hashlib.sha256(_serialize(report)).hexdigest()}
    if path.exists():
        verify_report(path)
        if json.loads(path.read_text(encoding="utf-8")) != body:
            raise FileExistsError("Conflicting report at same destination")
        return body
    scratch = path.with_name("." + path.name + ".tmp")
    try:
        with scratch.open("xb") as out:
            out.write(_serialize(body))
            out.flush()
            import os
            os.fsync(out.fileno())
        scratch.replace(path)
    finally:
        scratch.unlink(missing_ok=True)
    verify_report(path)
    return body


def verify_report(path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or set(doc) != {"report", "sha256"}:
        raise ValueError("Invalid report schema")
    r = doc["report"]
    if hashlib.sha256(_serialize(r)).hexdigest() != doc["sha256"]:
        raise ValueError("Report digest mismatch")
    p = r["design"]
    expected = run_validation(seeds=p["seeds"], steps=p["steps"],
                              shift_tick=p["shift_tick"], holdout_steps=p["holdout_steps"],
                              capacity=p["capacity"], resources=p["resources_per_tick"],
                              mutation_rate=p["mutation_rate"])
    if expected != r:
        raise ValueError("Independent deterministic recomputation mismatch")
    return doc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run_validation()
    doc = save_and_verify(report, args.output)
    print(json.dumps({"verified": True, "sha256": doc["sha256"],
                      "adaptation_demonstrated": report["adaptation_demonstrated"],
                      "paired_functional_b_gain": report["paired_functional_b_gain"],
                      "paired_holdout_population_gain": report["paired_holdout_population_gain"],
                      "negative_control_births_zero": report["negative_control_births_zero"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
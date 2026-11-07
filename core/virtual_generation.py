"""Bounded virtual-organism generation with an independent confirmation gate.

This evolves only genomes inside the repository's toy digital VM. A candidate
mutation rate is inherited by the next cycle only when its paired score beats
the parent rate on both development and held-out seeds with a positive 95% CI.
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


_RATES = (0.02, 0.05, 0.08, 0.12, 0.18)
_TRAIN_SEEDS = tuple(range(12))
_CONFIRM_SEEDS = tuple(range(100, 112))
_STEPS = 80
_SHIFT_TICK = 30
_CAPACITY = 32


def _vm_types():
    try:
        from organism_lab.digital_vm import COPY_REST, DIVIDE, GenomeWorld
        try:
            from organism_lab.digital_vm import TASK_A, TASK_B
        except ImportError:
            TASK_A = TASK_B = None
        return COPY_REST, DIVIDE, TASK_A, TASK_B, GenomeWorld
    except ImportError:
        vm_root = Path(__file__).resolve().parents[1] / "organism_lab_cloud"
        if str(vm_root) not in sys.path:
            sys.path.insert(0, str(vm_root))
        from organism_lab.digital_vm import COPY_REST, DIVIDE, TASK_A, TASK_B, GenomeWorld
        return COPY_REST, DIVIDE, TASK_A, TASK_B, GenomeWorld


def _scores(rate: float, seeds: tuple[int, ...]) -> list[float]:
    copy_rest, divide, task_a, task_b, world_type = _vm_types()
    values = []
    for seed in seeds:
        options = {"seed": seed, "capacity": _CAPACITY, "resources_per_tick": 1,
                   "mutation_rate": rate, "initial_genome":
                   (copy_rest, task_a, divide) if task_a is not None else (copy_rest, divide)}
        if task_a is not None:
            options.update(environment=task_a, task_reward=2)
        world = world_type(**options)
        for tick in range(1, _STEPS + 1):
            if task_a is not None and tick == _SHIFT_TICK + 1:
                world.set_environment(task_b)
            metrics = world.step()
        population = world.organisms
        if task_a is not None:
            values.append(sum(task_b in organism.genome for organism in population) / len(population)
                          if population else 0.0)
        else:
            # Main-branch VM measures diversity only; no engineered task/reward
            # behavior is assumed. Births and generation counts remain simulator
            # outputs, not claims about biological learning.
            values.append(float(metrics["unique_genomes"]))
    return values


def _paired_summary(candidate: list[float], parent: list[float]) -> dict:
    if len(candidate) != len(parent) or len(candidate) < 2:
        raise ValueError("Paired evaluation requires at least two matching seeds")
    differences = [left - right for left, right in zip(candidate, parent)]
    mean = sum(differences) / len(differences)
    variance = sum((value - mean) ** 2 for value in differences) / (len(differences) - 1)
    margin = 1.96 * math.sqrt(variance / len(differences))
    return {
        "paired_seeds": len(differences),
        "candidate_mean_score": sum(candidate) / len(candidate),
        "parent_mean_score": sum(parent) / len(parent),
        "mean_paired_difference": mean,
        "ci95_low": mean - margin,
        "ci95_high": mean + margin,
        "positive_evidence": mean - margin > 0,
    }


def run_virtual_generation(database_path: str | Path, tick_id: int) -> dict:
    """Run one reproducible generation and persist it with restart-safe idempotency."""
    if type(tick_id) is not int or tick_id < 1:
        raise ValueError("tick_id must be a positive integer")
    database_path = str(database_path)
    with closing(sqlite3.connect(database_path, timeout=10)) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS virtual_generation (
            tick_id INTEGER PRIMARY KEY,
            parent_tick_id INTEGER,
            parent_mutation_rate REAL NOT NULL,
            candidate_mutation_rate REAL NOT NULL,
            training_json TEXT NOT NULL,
            confirmation_json TEXT NOT NULL,
            lesson_status TEXT NOT NULL CHECK(lesson_status IN ('transferred','rejected')),
            next_mutation_rate REAL NOT NULL,
            created_at TEXT NOT NULL
        )""")
        existing = db.execute(
            "SELECT parent_tick_id,parent_mutation_rate,candidate_mutation_rate,training_json,"
            "confirmation_json,lesson_status,next_mutation_rate,created_at "
            "FROM virtual_generation WHERE tick_id=?", (tick_id,)
        ).fetchone()
        if existing:
            return _record(tick_id, existing)
        previous = db.execute(
            "SELECT tick_id,next_mutation_rate FROM virtual_generation ORDER BY tick_id DESC LIMIT 1"
        ).fetchone()
        parent_tick_id, parent_rate = (previous[0], previous[1]) if previous else (None, 0.0)
        candidate_rate = _RATES[(tick_id - 1) % len(_RATES)]
        training = _paired_summary(_scores(candidate_rate, _TRAIN_SEEDS),
                                   _scores(parent_rate, _TRAIN_SEEDS))
        confirmation = _paired_summary(_scores(candidate_rate, _CONFIRM_SEEDS),
                                       _scores(parent_rate, _CONFIRM_SEEDS))
        transferred = training["positive_evidence"] and confirmation["positive_evidence"]
        next_rate = candidate_rate if transferred else parent_rate
        created_at = datetime.now(timezone.utc).isoformat()
        training_json = json.dumps(training, sort_keys=True)
        confirmation_json = json.dumps(confirmation, sort_keys=True)
        db.execute("""INSERT INTO virtual_generation VALUES (?,?,?,?,?,?,?,?,?)""",
                   (tick_id, parent_tick_id, parent_rate, candidate_rate,
                    training_json, confirmation_json,
                    "transferred" if transferred else "rejected", next_rate, created_at))
        db.commit()
        row = db.execute(
            "SELECT parent_tick_id,parent_mutation_rate,candidate_mutation_rate,training_json,"
            "confirmation_json,lesson_status,next_mutation_rate,created_at "
            "FROM virtual_generation WHERE tick_id=?", (tick_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("Virtual generation persistence readback failed")
        return _record(tick_id, row)


def _record(tick_id: int, row: tuple) -> dict:
    return {
        "generation_id": tick_id,
        "parent_generation_id": row[0],
        "parent_mutation_rate": row[1],
        "candidate_mutation_rate": row[2],
        "training": json.loads(row[3]),
        "held_out_confirmation": json.loads(row[4]),
        "lesson_status": row[5],
        "next_generation_mutation_rate": row[6],
        "primary_metric": "held-out task-B genome share" if _vm_types()[2] is not None
                          else "final surviving unique genome count",
        "created_at": row[7],
        "offspring_scope": "bounded toy digital VM only",
        "model_weights_updated": False,
    }

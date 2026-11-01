"""Repeatable multi-seed trials and population diversity measurements."""
from statistics import mean
from .evolution import World

def trial(*, seeds=(0, 1, 2, 3, 4), steps=30, capacity=64, resources=10):
    if not isinstance(steps, int) or not 0 <= steps <= 10000:
        raise ValueError("steps must be between 0 and 10000")
    if not seeds:
        raise ValueError("At least one seed required")
    rows = []
    for seed in seeds:
        world = World(seed=seed, capacity=capacity, resources=resources)
        for _ in range(steps):
            world.step()
        metric = world.metrics()
        metric["seed"] = seed
        metric["diversity"] = len({o.efficiency for o in world.organisms})
        rows.append(metric)
    return {"trials": rows,
            "mean_population": mean(r["population"] for r in rows),
            "mean_births": mean(r["births"] for r in rows),
            "mean_diversity": mean(r["diversity"] for r in rows)}

def resource_sweep(*, resource_levels=(0, 5, 10, 20), seeds=(0, 1, 2), steps=30):
    if not resource_levels:
        raise ValueError("At least one resource level required")
    return [{"resources": resources, **trial(seeds=seeds, steps=steps, resources=resources)}
            for resources in resource_levels]

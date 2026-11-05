"""Reproducible multi-seed digital evolution experiments, with no external side effects."""
import hashlib
import json
from .evolution import World


def run_experiment(*, seed=0, steps=100, capacity=64, resources=10):
    if type(seed) is not int or type(steps) is not int or not 0 <= steps <= 10000:
        raise ValueError("Invalid seed or steps")
    if type(capacity) is not int or not 1 <= capacity <= 10000:
        raise ValueError("Invalid capacity")
    if type(resources) is not int or not 0 <= resources <= 100000:
        raise ValueError("Invalid resources")
    world = World(seed=seed, capacity=capacity, resources=resources)
    history = [world.step() for _ in range(steps)]
    if any(not 0 <= item["population"] <= capacity for item in history):
        raise AssertionError("Population escaped capacity")
    if history and history[-1]["births"] + 1 - history[-1]["deaths"] != history[-1]["population"]:
        raise AssertionError("Population accounting failed")
    result = {"model": "digital-evolution-experiment-v1", "seed": seed, "steps": steps,
              "capacity": capacity, "resources": resources, "history": history,
              "final": world.metrics()}
    result["sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def compare_experiments(seeds=(1, 2, 3, 4, 5), **parameters):
    seeds = tuple(seeds)
    if not 1 <= len(seeds) <= 1000 or any(type(seed) is not int for seed in seeds):
        raise ValueError("Invalid seed series")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Seeds must be distinct")
    results = [run_experiment(seed=seed, **parameters) for seed in seeds]
    return {"runs": len(results), "mean_final_population":
            sum(x["final"]["population"] for x in results) / len(results),
            "mean_births": sum(x["final"]["births"] for x in results) / len(results),
            "results": results}

"""Population lineage and experimental measurements without external services."""
from .evolution import World

def run_lineage(*, seed=0, steps=30, capacity=64, resources=10):
    if not isinstance(steps, int) or not 0 <= steps <= 10000:
        raise ValueError("steps must be between 0 and 10000")
    world = World(seed=seed, capacity=capacity, resources=resources)
    genealogy = {0: {"parent": None, "generation": 0, "efficiency": 2}}
    snapshots = [world.metrics()]
    for _ in range(steps):
        snapshots.append(world.step())
        for organism in world.organisms:
            if organism.id not in genealogy:
                genealogy[organism.id] = {
                    "parent": organism.parent,
                    "generation": organism.generation,
                    "efficiency": organism.efficiency,
                }
    founders = [entry for entry in genealogy.values() if entry["parent"] is None]
    if len(founders) != 1:
        raise AssertionError("Expected one founder")
    return {"history": snapshots, "genealogy": genealogy,
            "final_population": len(world.organisms),
            "ever_born": len(genealogy),
            "max_generation_ever": max(entry["generation"] for entry in genealogy.values()),
            "founder_efficiency": genealogy[0]["efficiency"],
            "final_mean_efficiency": snapshots[-1]["mean_efficiency"]}

def evaluate_improvement(result):
    """Compare mean efficiency to founder; a measurement, not proof of evolution."""
    delta = result["final_mean_efficiency"] - result["founder_efficiency"]
    return {"efficiency_delta": delta, "direction": "up" if delta > 0 else "down" if delta < 0 else "unchanged",
            "note": "Descriptive only; no statistical significance or fitness claim"}

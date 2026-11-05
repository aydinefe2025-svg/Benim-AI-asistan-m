"""Reproducible experiments and CSV export for the digital organism model."""
import csv
import io
from .evolution import World

def run_experiment(*, seed=0, steps=30, capacity=64, resources=10):
    if not isinstance(steps, int) or not 0 <= steps <= 10000:
        raise ValueError("steps must be between 0 and 10000")
    world = World(seed=seed, capacity=capacity, resources=resources)
    history = [world.metrics()]
    for _ in range(steps):
        history.append(world.step())
    return {"config": {"seed": seed, "steps": steps, "capacity": capacity, "resources": resources},
            "history": history, "final": history[-1]}

def compare_control(*, seed=0, steps=30, capacity=64, resources=10):
    """Compare replicating world to a no-replication baseline (capacity=1)."""
    experimental = run_experiment(seed=seed, steps=steps, capacity=capacity, resources=resources)
    control = run_experiment(seed=seed, steps=steps, capacity=1, resources=resources)
    return {"experimental": experimental, "control": control,
            "population_difference": experimental["final"]["population"] - control["final"]["population"]}

def to_csv(experiment):
    output = io.StringIO()
    history = experiment["history"]
    writer = csv.DictWriter(output, fieldnames=("tick", "population", "births", "deaths", "max_generation", "mean_efficiency"))
    writer.writeheader()
    writer.writerows(history)
    return output.getvalue()

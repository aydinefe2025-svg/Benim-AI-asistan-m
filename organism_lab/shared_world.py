"""Shared-budget virtual environment for robot tasks and digital organisms.

This is a deterministic resource accounting experiment, not physical robotics.
"""
from dataclasses import dataclass
from .core import grid_route

@dataclass
class Budget:
    energy: int
    materials: int
    def __post_init__(self):
        if type(self.energy) is not int or type(self.materials) is not int or min(self.energy, self.materials) < 0:
            raise ValueError("Budget must contain nonnegative integer resources")
    def spend(self, *, energy=0, materials=0):
        if any(type(x) is not int or x < 0 for x in (energy, materials)):
            raise ValueError("Costs must be nonnegative integers")
        if energy > self.energy or materials > self.materials:
            return False
        self.energy -= energy
        self.materials -= materials
        return True

def run_shared_world(*, steps=10, energy=40, materials=12, width=5, height=5):
    if type(steps) is not int or not 0 <= steps <= 10000:
        raise ValueError("Invalid step count")
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise ValueError("Invalid grid")
    budget = Budget(energy=energy, materials=materials)
    robots = 0
    organisms = 1
    successful_routes = 0
    births = 0
    log = []
    for tick in range(steps):
        # One assembly attempt per tick, four materials per robot.
        robot_built = budget.spend(energy=2, materials=4)
        if robot_built:
            robots += 1
        # One digital birth attempt, consuming shared energy.
        organism_born = budget.spend(energy=3) if organisms < 32 else False
        if organism_born:
            organisms += 1
            births += 1
        route = grid_route(width, height, (0, 0), (width - 1, height - 1))
        route_ok = robots > 0 and route is not None and budget.spend(energy=len(route) - 1)
        if route_ok:
            successful_routes += 1
        log.append({"tick": tick + 1, "robots": robots, "organisms": organisms,
                    "robot_built": robot_built, "organism_born": organism_born,
                    "route_success": route_ok, "energy_left": budget.energy,
                    "materials_left": budget.materials})
    return {"history": log, "robots": robots, "organisms": organisms,
            "births": births, "successful_routes": successful_routes,
            "energy_left": budget.energy, "materials_left": budget.materials}

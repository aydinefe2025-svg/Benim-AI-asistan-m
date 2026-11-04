"""Bounded, local, conceptual digital-organism population.

This is a pure in-memory simulation. It does not make network calls, access
other machines, spawn AI agents, reproduce code, or create biological matter.
Every growth step requires an explicit approval flag and available resources.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Organism:
    id: int
    zone: str
    generation: int
    parent_id: int | None = None


@dataclass
class DigitalHabitat:
    allowed_zones: set[str]
    capacity: int
    energy: int
    max_generation: int = 4
    running: bool = True
    population: dict[int, Organism] = field(default_factory=dict, init=False)
    audit_log: list[dict[str, object]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if not self.allowed_zones or any(
            not isinstance(zone, str) or not zone.strip()
            for zone in self.allowed_zones
        ):
            raise ValueError("At least one valid authorized simulation zone is required")
        for name, value in (
            ("capacity", self.capacity), ("energy", self.energy),
            ("max_generation", self.max_generation)
        ):
            if type(value) is not int or value < (1 if name == "capacity" else 0):
                raise ValueError(f"Invalid bounded {name}")

    def _check_running(self) -> None:
        if not self.running:
            raise RuntimeError("Simulation is stopped")

    def seed(self, zone: str) -> Organism:
        self._check_running()
        if zone not in self.allowed_zones:
            raise PermissionError("Zone not authorized")
        if self.population:
            raise RuntimeError("Founding organism already created")
        organism = Organism(id=1, zone=zone, generation=0)
        self.population[organism.id] = organism
        self.audit_log.append({"event": "seed", "id": organism.id, "zone": zone})
        return organism

    def spawn(self, parent_id: int, *, zone: str, approved: bool = False) -> Organism:
        self._check_running()
        if not approved:
            raise PermissionError("Explicit approval required for each simulated child")
        if zone not in self.allowed_zones:
            raise PermissionError("Zone not authorized")
        parent = self.population.get(parent_id)
        if parent is None:
            raise ValueError("Parent does not exist")
        if len(self.population) >= self.capacity:
            raise RuntimeError("Population quota exhausted")
        if self.energy < 2:
            raise RuntimeError("Energy budget exhausted")
        if parent.generation >= self.max_generation:
            raise RuntimeError("Generation quota exhausted")
        child = Organism(
            id=len(self.population) + 1,
            zone=zone,
            generation=parent.generation + 1,
            parent_id=parent.id,
        )
        self.population[child.id] = child
        self.energy -= 2
        self.audit_log.append({
            "event": "spawn", "id": child.id,
            "parent_id": parent.id, "zone": zone,
            "remaining_energy": self.energy,
        })
        return child

    def stop(self) -> None:
        self.running = False
        self.audit_log.append({"event": "stop", "population": len(self.population)})

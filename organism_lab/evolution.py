"""Resource-limited digital organism evolution simulation (not biology)."""
from dataclasses import dataclass
from random import Random

@dataclass(frozen=True)
class Organism:
    id: int
    parent: int | None
    generation: int
    energy: int
    efficiency: int

class World:
    def __init__(self, seed=0, capacity=64, resources=10):
        if capacity < 1 or resources < 0:
            raise ValueError("Invalid world configuration")
        self.random = Random(seed)
        self.capacity = capacity
        self.resources = resources
        self.tick = 0
        self.next_id = 1
        self.organisms = [Organism(0, None, 0, 6, 2)]
        self.births = 0
        self.deaths = 0

    def step(self):
        """One time step: maintenance, limited feeding, then energy-funded reproduction."""
        self.tick += 1
        available = self.resources
        survivors = []
        for organism in self.organisms:
            energy = organism.energy - 1
            if available:
                gain = min(organism.efficiency, available)
                available -= gain
                energy += gain
            if energy > 0:
                survivors.append(Organism(organism.id, organism.parent, organism.generation, energy, organism.efficiency))
            else:
                self.deaths += 1
        children = []
        parents = []
        for organism in survivors:
            if organism.energy >= 8 and len(survivors) + len(children) < self.capacity:
                child_efficiency = max(1, min(4, organism.efficiency + self.random.choice((-1, 0, 0, 1))))
                children.append(Organism(self.next_id, organism.id, organism.generation + 1, 3, child_efficiency))
                self.next_id += 1
                self.births += 1
                organism = Organism(organism.id, organism.parent, organism.generation, organism.energy - 4, organism.efficiency)
            parents.append(organism)
        self.organisms = parents + children
        return self.metrics()

    def metrics(self):
        return {
            "tick": self.tick,
            "population": len(self.organisms),
            "births": self.births,
            "deaths": self.deaths,
            "max_generation": max((o.generation for o in self.organisms), default=0),
            "mean_efficiency": (sum(o.efficiency for o in self.organisms) / len(self.organisms)) if self.organisms else 0,
        }

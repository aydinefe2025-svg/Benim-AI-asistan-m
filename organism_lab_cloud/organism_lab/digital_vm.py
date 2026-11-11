"""Bounded instruction-level digital replication model (not biological life)."""
from dataclasses import dataclass
from hashlib import sha256
from random import Random

NOP = 0
COPY_REST = 1
DIVIDE = 2
TASK_A = 3
TASK_B = 4
INSTRUCTION_SET = (NOP, COPY_REST, DIVIDE, TASK_A, TASK_B)
MAX_GENOME_LENGTH = 64
MAX_INSTRUCTIONS_PER_LIFETIME = 128


def execute_genome(genome):
    """Execute a tiny genome; return its copied genome only on valid division."""
    if not isinstance(genome, (tuple, list)) or not 1 <= len(genome) <= MAX_GENOME_LENGTH:
        return None
    if any(type(op) is not int or op not in INSTRUCTION_SET for op in genome):
        return None
    copied = []
    for instruction in genome[:MAX_INSTRUCTIONS_PER_LIFETIME]:
        if instruction == COPY_REST:
            copied.extend(genome)
        elif instruction == DIVIDE and len(copied) == len(genome):
            return tuple(copied)
    return None


def genome_fingerprint(genome):
    """Return a stable SHA-256 digest for a validated instruction sequence."""
    if not isinstance(genome, (tuple, list)) or not 1 <= len(genome) <= MAX_GENOME_LENGTH:
        raise ValueError("Invalid genome")
    if any(type(op) is not int or op not in INSTRUCTION_SET for op in genome):
        raise ValueError("Invalid genome")
    return sha256(b"genome-v1:" + bytes(genome)).hexdigest()


@dataclass(frozen=True)
class DigitalOrganism:
    identifier: int
    parent: int | None
    generation: int
    energy: int
    genome: tuple[int, ...]
    parent_genome_sha256: str | None = None
    mutation_count: int = 0


class GenomeWorld:
    """A deterministic, resource-limited virtual machine with a hard population cap."""
    def __init__(self, *, seed=0, capacity=64, resources_per_tick=10,
                 mutation_rate=0.02, initial_genome=(COPY_REST, DIVIDE),
                 allow_replication=True, environment=TASK_A, task_reward=2):
        if type(seed) is not int or seed < 0:
            raise ValueError("Invalid seed")
        if type(capacity) is not int or not 1 <= capacity <= 256:
            raise ValueError("Invalid population capacity")
        if type(resources_per_tick) is not int or resources_per_tick < 0:
            raise ValueError("Invalid resource budget")
        if not isinstance(mutation_rate, (int, float)) or isinstance(mutation_rate, bool) or not 0 <= mutation_rate <= 1:
            raise ValueError("Invalid mutation rate")
        if execute_genome(initial_genome) is None:
            raise ValueError("Initial genome must self-copy and divide")
        if type(allow_replication) is not bool:
            raise ValueError("allow_replication must be boolean")
        if type(environment) is not int or environment not in (TASK_A, TASK_B):
            raise ValueError("Environment must be TASK_A or TASK_B")
        if type(task_reward) is not int or not 0 <= task_reward <= 20:
            raise ValueError("Task reward must be an integer from 0 to 20")
        self.random = Random(seed)
        self.capacity = capacity
        self.resources_per_tick = resources_per_tick
        self.mutation_rate = float(mutation_rate)
        self.allow_replication = allow_replication
        self.environment = environment
        self.task_reward = task_reward
        self.tick = 0
        self.next_id = 1
        self.births = 0
        self.deaths = 0
        self.organisms = [DigitalOrganism(0, None, 0, 6, tuple(initial_genome))]

    def _mutate(self, genome):
        child = list(genome)
        for index, opcode in enumerate(child):
            if self.random.random() < self.mutation_rate:
                choices = tuple(op for op in INSTRUCTION_SET if op != opcode)
                child[index] = self.random.choice(choices)
        return tuple(child)

    def step(self):
        self.tick += 1
        available = self.resources_per_tick
        survivors = []
        for organism in sorted(self.organisms, key=lambda item: item.identifier):
            energy = organism.energy - 1
            if self.environment in organism.genome:
                # A matching inherited task instruction earns energy. This creates
                # explicit selection pressure; it is not model/biological learning.
                energy += self.task_reward
            gain = min(2, available)
            available -= gain
            energy += gain
            if energy > 0:
                survivors.append(DigitalOrganism(
                    organism.identifier, organism.parent, organism.generation, energy,
                    organism.genome, organism.parent_genome_sha256, organism.mutation_count
                ))
            else:
                self.deaths += 1
        children = []
        parents = []
        for organism in survivors:
            child_genome = execute_genome(organism.genome) if self.allow_replication else None
            if (child_genome is not None and organism.energy >= 8
                    and len(survivors) + len(children) < self.capacity):
                inherited_genome = tuple(child_genome)
                mutated_genome = self._mutate(inherited_genome)
                mutation_count = sum(
                    inherited != mutated
                    for inherited, mutated in zip(inherited_genome, mutated_genome)
                )
                children.append(DigitalOrganism(
                    self.next_id, organism.identifier, organism.generation + 1, 3,
                    mutated_genome, genome_fingerprint(organism.genome), mutation_count
                ))
                self.next_id += 1
                self.births += 1
                organism = DigitalOrganism(
                    organism.identifier, organism.parent, organism.generation,
                    organism.energy - 4, organism.genome,
                    organism.parent_genome_sha256, organism.mutation_count
                )
            parents.append(organism)
        self.organisms = parents + children
        return self.metrics()

    def set_environment(self, environment):
        """Switch the active task; organisms retain their genomes and lineages."""
        if type(environment) is not int or environment not in (TASK_A, TASK_B):
            raise ValueError("Environment must be TASK_A or TASK_B")
        self.environment = environment

    def lineage_snapshot(self):
        """Return an auditable snapshot of the living colony's genotype provenance."""
        return [
            {
                "organism_id": item.identifier,
                "parent_id": item.parent,
                "generation": item.generation,
                "genome": list(item.genome),
                "genome_sha256": genome_fingerprint(item.genome),
                "parent_genome_sha256": item.parent_genome_sha256,
                "mutation_count": item.mutation_count,
            }
            for item in sorted(self.organisms, key=lambda organism: organism.identifier)
        ]

    def metrics(self):
        return {"tick": self.tick, "population": len(self.organisms),
                "births": self.births, "deaths": self.deaths,
                "max_generation": max((item.generation for item in self.organisms), default=0),
                "unique_genomes": len({item.genome for item in self.organisms}),
                "replicators": sum(execute_genome(item.genome) is not None
                                   for item in self.organisms)}

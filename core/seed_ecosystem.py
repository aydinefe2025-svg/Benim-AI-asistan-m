"""Finite-energy CANO seed ecosystem: a deterministic in-memory *simulation*.

No network, code replication, autonomous deployment, devices or real harvesting.
Each step and injected failure requires explicit simulation authorization.
Energy units are hypothetical credits, NOT measured watts or joules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json


ENERGY_SOURCES = frozenset({"solar", "wind", "water", "thermal", "vibration", "rf", "grid"})


@dataclass(frozen=True)
class SeedNode:
    id: int
    generation: int
    parent_id: int | None


class SeedEcosystem:
    """One copyable design seed, with energy-aware bounded virtual descendants."""

    def __init__(self, *, capacity: int = 12, max_generation: int = 6,
                 energy_cap: int = 24) -> None:
        if (type(capacity) is not int or not 1 <= capacity <= 100
                or type(max_generation) is not int or not 1 <= max_generation <= 32
                or type(energy_cap) is not int or not 1 <= energy_cap <= 10000):
            raise ValueError("Invalid finite habitat bounds")
        self.capacity = capacity
        self.max_generation = max_generation
        self.energy_cap = energy_cap
        self.nodes: dict[int, SeedNode] = {1: SeedNode(1, 0, None)}
        self.next_id = 2
        self.energy = 0
        self.tick = 0
        self.discarded_energy = 0
        self.total_harvested = 0
        self.total_births = 0
        self.dormant_ticks = 0
        self.audit: list[dict] = []

    @property
    def population_size(self) -> int:
        return len(self.nodes)

    def step(self, harvested: dict[str, int], *, authorized: bool = False) -> dict:
        """Advance one bounded virtual time step; one birth at most per step."""
        if not authorized:
            raise PermissionError("Simulation step requires explicit authorization")
        if (not isinstance(harvested, dict)
                or any(source not in ENERGY_SOURCES or type(amount) is not int
                       or not 0 <= amount <= 100 for source, amount in harvested.items())
                or sum(harvested.values()) > 500):
            raise ValueError("Invalid simulated energy sources/yields")
        self.tick += 1
        gain = sum(harvested.values())
        self.total_harvested += gain
        available = self.energy + gain
        self.discarded_energy += max(0, available - self.energy_cap)
        self.energy = min(self.energy_cap, available)

        maintenance = len(self.nodes)  # 1 simulated unit per node, per active step
        born = None
        if not self.nodes:
            mode = "extinct"
        elif self.energy < maintenance:
            # Virtual seed records remain stored but cannot execute while unpowered.
            mode = "dormant"
            self.dormant_ticks += 1
        else:
            mode = "active"
            self.energy -= maintenance
            eligible = [node for node in self.nodes.values()
                        if node.generation < self.max_generation]
            if self.energy >= 2 and len(self.nodes) < self.capacity and eligible:
                parent = max(eligible, key=lambda node: (node.generation, -node.id))
                born = SeedNode(self.next_id, parent.generation + 1, parent.id)
                self.nodes[born.id] = born
                self.next_id += 1
                self.energy -= 2
                self.total_births += 1

        record = {
            "tick": self.tick,
            "sources": dict(sorted(harvested.items())),
            "harvested": gain,
            "maintenance": maintenance if mode == "active" else 0,
            "mode": mode,
            "born_id": born.id if born else None,
            "generation": born.generation if born else None,
            "population": len(self.nodes),
            "energy_after": self.energy,
        }
        self.audit.append(record)
        return record.copy()

    def fail_nodes(self, ids: tuple[int, ...], *, authorized: bool = False) -> tuple[int, ...]:
        """Inject a simulated failure. No OS process or real device is touched."""
        if not authorized:
            raise PermissionError("Failure injection requires explicit authorization")
        if (not isinstance(ids, tuple) or len(set(ids)) != len(ids)
                or any(type(node_id) is not int or node_id not in self.nodes for node_id in ids)):
            raise ValueError("Invalid simulated failure targets")
        for node_id in ids:
            del self.nodes[node_id]
        self.audit.append({"tick": self.tick, "event": "synthetic_failure", "ids": list(ids)})
        return ids

    @staticmethod
    def _canonical(payload: dict) -> bytes:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")

    def checkpoint(self) -> dict:
        """SHA-256 accidental-corruption checksum, NOT a signature or trusted backup."""
        payload = {
            "schema": 1, "capacity": self.capacity, "max_generation": self.max_generation,
            "energy_cap": self.energy_cap, "energy": self.energy,
            "tick": self.tick, "next_id": self.next_id,
            "discarded_energy": self.discarded_energy,
            "total_harvested": self.total_harvested,
            "total_births": self.total_births, "dormant_ticks": self.dormant_ticks,
            "nodes": [asdict(node) for node in sorted(self.nodes.values(), key=lambda n: n.id)],
            "audit": self.audit,
        }
        return {"payload": payload, "sha256": sha256(self._canonical(payload)).hexdigest()}

    @classmethod
    def from_checkpoint(cls, checkpoint: dict) -> "SeedEcosystem":
        if not isinstance(checkpoint, dict) or set(checkpoint) != {"payload", "sha256"}:
            raise ValueError("Invalid checkpoint structure")
        payload = checkpoint["payload"]
        if not isinstance(payload, dict) or not isinstance(checkpoint["sha256"], str):
            raise ValueError("Invalid checkpoint")
        if sha256(cls._canonical(payload)).hexdigest() != checkpoint["sha256"]:
            raise ValueError("Checkpoint checksum mismatch")
        expected = {"schema", "capacity", "max_generation", "energy_cap", "energy",
                    "tick", "next_id", "discarded_energy", "total_harvested",
                    "total_births", "dormant_ticks", "nodes", "audit"}
        if set(payload) != expected or payload["schema"] != 1:
            raise ValueError("Unsupported checkpoint schema")
        lab = cls(capacity=payload["capacity"], max_generation=payload["max_generation"],
                  energy_cap=payload["energy_cap"])
        for key in ("energy", "tick", "next_id", "discarded_energy",
                    "total_harvested", "total_births", "dormant_ticks"):
            value = payload[key]
            if type(value) is not int or value < 0:
                raise ValueError("Invalid checkpoint numeric field")
            setattr(lab, key, value)
        if lab.energy > lab.energy_cap or lab.next_id < 2:
            raise ValueError("Invalid checkpoint energy or identity")
        if not isinstance(payload["nodes"], list) or len(payload["nodes"]) > lab.capacity:
            raise ValueError("Invalid checkpoint population")
        lab.nodes = {}
        for value in payload["nodes"]:
            if not isinstance(value, dict) or set(value) != {"id", "generation", "parent_id"}:
                raise ValueError("Invalid seed node")
            node = SeedNode(**value)
            if (type(node.id) is not int or node.id < 1
                    or type(node.generation) is not int or not 0 <= node.generation <= lab.max_generation
                    or (node.parent_id is not None and
                        (type(node.parent_id) is not int or node.parent_id >= node.id))
                    or node.id in lab.nodes):
                raise ValueError("Invalid node lineage")
            lab.nodes[node.id] = node
        if lab.nodes and lab.next_id <= max(lab.nodes):
            raise ValueError("Checkpoint would reuse an identity")
        if not isinstance(payload["audit"], list) or len(payload["audit"]) > lab.tick * 2 + 100:
            raise ValueError("Invalid checkpoint audit")
        lab.audit = payload["audit"]
        return lab

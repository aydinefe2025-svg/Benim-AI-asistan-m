"""Deterministic, dependency-free digital agent colony and grid robot simulator."""
from dataclasses import dataclass, field
from collections import deque
from typing import Dict, List

ROLES = ("research", "code", "robotics", "energy", "security", "history", "archive", "review")

@dataclass
class Agent:
    identifier: str
    role: str
    generation: int = 0
    completed: int = 0

@dataclass
class Colony:
    agents: Dict[str, Agent] = field(default_factory=dict)
    audit: List[dict] = field(default_factory=list)
    maximum_agents: int = 32

    @classmethod
    def initialize(cls):
        return cls({f"{role}-0": Agent(f"{role}-0", role) for role in ROLES})

    def spawn(self, parent_id: str) -> Agent:
        if parent_id not in self.agents:
            raise KeyError("Unknown parent")
        if len(self.agents) >= self.maximum_agents:
            raise RuntimeError("Population limit reached")
        parent = self.agents[parent_id]
        sibling_count = sum(a.role == parent.role for a in self.agents.values())
        identifier = f"{parent.role}-{sibling_count}"
        child = Agent(identifier, parent.role, parent.generation + 1)
        self.agents[identifier] = child
        self.audit.append({"event": "spawn", "parent": parent_id, "child": identifier})
        return child

    def assign(self, role: str, task: str) -> dict:
        if role not in ROLES or not task.strip():
            raise ValueError("Valid role and nonempty task required")
        candidates = [a for a in self.agents.values() if a.role == role]
        agent = min(candidates, key=lambda a: (a.completed, a.identifier))
        agent.completed += 1
        record = {"event": "assign", "agent": agent.identifier, "task": task, "status": "queued"}
        self.audit.append(record)
        return record

def grid_route(width: int, height: int, start: tuple, goal: tuple, obstacles=()):
    """Breadth-first shortest route. No physical robot actuation."""
    if width < 1 or height < 1:
        raise ValueError("Invalid grid")
    blocked = set(obstacles)
    def valid(p):
        return 0 <= p[0] < width and 0 <= p[1] < height and p not in blocked
    if not valid(start) or not valid(goal):
        raise ValueError("Start or goal blocked/outside grid")
    queue = deque([(start, [start])])
    visited = {start}
    while queue:
        pos, path = queue.popleft()
        if pos == goal:
            return path
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (pos[0] + dx, pos[1] + dy)
            if valid(nxt) and nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, path + [nxt]))
    return None


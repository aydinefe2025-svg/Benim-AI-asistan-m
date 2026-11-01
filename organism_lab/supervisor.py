"""Explicitly invoked, bounded supervisor for offline digital-agent tasks.

No networking, subprocesses, external actions or autonomous background work.
"""
from dataclasses import dataclass, field
from .core import Colony, ROLES
from .coordination import execute_task, grow_on_demand

@dataclass
class Supervisor:
    colony: Colony = field(default_factory=Colony.initialize)
    max_tasks: int = 100
    max_retries: int = 1

    def run(self, tasks, handlers, verifiers, *, allow_growth=False):
        if type(self.max_tasks) is not int or not 1 <= self.max_tasks <= 1000:
            raise ValueError("Invalid task limit")
        if type(self.max_retries) is not int or not 0 <= self.max_retries <= 3:
            raise ValueError("Invalid retry limit")
        if type(allow_growth) is not bool:
            raise ValueError("Invalid growth permission")
        if not isinstance(tasks, (tuple, list)) or len(tasks) > self.max_tasks:
            raise ValueError("Task queue exceeds limit")
        if not isinstance(handlers, dict) or not isinstance(verifiers, dict):
            raise TypeError("Handlers and verifiers must be mappings")
        for role, task in tasks:
            if role not in ROLES or not isinstance(task, str) or not task.strip():
                raise ValueError("Invalid task")
            if not callable(handlers.get(role)) or not callable(verifiers.get(role)):
                raise ValueError("Approved handler and verifier required")
        results = []
        for role, task in tasks:
            if allow_growth:
                grow_on_demand(self.colony, role, queued_tasks=sum(r == role for r, _ in tasks))
            for attempt in range(self.max_retries + 1):
                result = execute_task(self.colony, role, task, handlers[role], verifiers[role])
                if result.status == "verified":
                    break
            results.append({"role": role, "task": task, "status": result.status,
                            "agent": result.agent, "evidence": result.evidence,
                            "attempts": attempt + 1})
        return {"results": results, "verified": sum(x["status"] == "verified" for x in results),
                "failed": sum(x["status"] == "failed" for x in results),
                "agents": len(self.colony.agents)}

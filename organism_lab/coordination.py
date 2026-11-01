"""Verified task execution layer for bounded digital agent colonies.

The colony assigns work, while an injected executor performs it. Nothing runs in
the background and external actions are never marked complete without evidence.
"""
from dataclasses import dataclass
from .core import Colony, ROLES

@dataclass(frozen=True)
class TaskResult:
    agent: str
    task: str
    status: str
    output: str
    evidence: str

def execute_task(colony: Colony, role: str, task: str, executor, verifier):
    """Run a task and verify it; errors are logged without falsely claiming success."""
    if not callable(executor) or not callable(verifier):
        raise TypeError("Executor and verifier must be callable")
    assignment = colony.assign(role, task)
    agent = assignment["agent"]
    try:
        output = executor(task)
        if not isinstance(output, str) or not output.strip():
            raise ValueError("Empty task output")
        evidence = verifier(task, output)
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("Verification evidence required")
        result = TaskResult(agent, task, "verified", output, evidence)
    except Exception as exc:
        result = TaskResult(agent, task, "failed", "", type(exc).__name__)
    colony.audit.append({"event": "result", "agent": agent, "task": task,
                         "status": result.status, "evidence": result.evidence})
    return result

def grow_on_demand(colony: Colony, role: str, *, queued_tasks: int, threshold: int = 3):
    """Spawn one same-role agent only when queued workload exceeds capacity."""
    if role not in ROLES or queued_tasks < 0 or threshold < 1:
        raise ValueError("Invalid growth parameters")
    candidates = [a for a in colony.agents.values() if a.role == role]
    if queued_tasks <= len(candidates) * threshold:
        return None
    if len(colony.agents) >= colony.maximum_agents:
        return None
    parent = min(candidates, key=lambda a: (a.generation, a.identifier))
    return colony.spawn(parent.identifier)

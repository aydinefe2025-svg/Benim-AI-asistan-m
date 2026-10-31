"""Safe, bounded, role-separated LLM mission runner.

Invokes configured model calls synchronously. No autonomous browsing,
real laboratory operations, robotics hardware control or automatic approval.
"""
from __future__ import annotations

from typing import Protocol


class MissionChatClient(Protocol):
    def chat(self, model: str, system: str, prompt: str, *,
             temperature: float = 0.2) -> str: ...


ROLES = (
    ("planner", "Decompose the mission into falsifiable questions and dependencies."),
    ("discovery", "Specify primary literature, datasets and provenance to look up; do not invent fetched sources."),
    ("engineer", "Design a safe computational prototype or simulation plan; never claim hardware was built."),
    ("skeptic", "Identify contrary evidence, assumptions, confounders, uncertainties, and failure modes."),
    ("replicator", "Design reproducible tests, controls, metrics, and explicit pass/fail gates."),
    ("archivist", "Assemble the task outputs and outstanding work into a provenance-aware draft archive."),
)
DOMAINS = ("research", "robotics_simulation", "computational_cell_model")


class SpecialistMission:
    def __init__(self, client: MissionChatClient):
        self.client = client

    def run(self, question: str, *, model: str, domain: str = "research") -> dict:
        if domain not in DOMAINS:
            raise ValueError("Unsupported specialist mission domain")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Mission question cannot be empty")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Model name cannot be empty")
        question = question.strip()
        rules = (
            "You are one role in a bounded research workflow. "
            "Use evidence levels and uncertainty. Do not assert a source was read "
            "unless its full content was actually provided. Do not perform laboratory experiments, "
            "do not create or manipulate real biological cells, do not control physical robots, "
            "do not start external agents and do not claim that simulations or experiments "
            "ran unless confirmed by separate execution evidence. "
            "Keep outputs as draft unverified research."
        )
        if domain == "computational_cell_model":
            rules += " Work only with conceptual models of cells and non-living biomimetic materials."
        elif domain == "robotics_simulation":
            rules += " Use digital robot simulation designs only; physical actuation needs separate approval."
        steps = []
        for role, assignment in ROLES:
            earlier = "\n\n".join(
                f"{item['role']}: {item['output']}" for item in steps
            )
            prompt = (
                f"Domain: {domain}\nMission: {question}\n"
                f"Assignment: {assignment}\n"
                f"Prior role outputs (unverified):\n{earlier or '(none)'}\n"
                "Provide a bounded, auditable Turkish draft with unknowns."
            )
            output = self.client.chat(
                model, f"Role: {role}. {rules}", prompt
            )
            if not isinstance(output, str) or not output.strip():
                raise RuntimeError(f"{role} produced no usable output")
            steps.append({"role": role, "model": model, "output": output})
        return {
            "domain": domain,
            "question": question,
            "status": "draft_unverified",
            "execution_environment": "llm_only",
            "independent_verification": False,
            "real_robots_created": False,
            "real_cells_created": False,
            "steps": steps,
        }

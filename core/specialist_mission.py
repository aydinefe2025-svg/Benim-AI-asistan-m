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
    ("planner", "Return exactly 3 ordered next steps and one dependency for this mission."),
    ("discovery", "List only missing primary sources or data needed; mark them NOT FETCHED. Never invent sources."),
    ("engineer", "Give one bounded, reversible software or simulation experiment; do not claim it was implemented."),
    ("skeptic", "Name the 3 most important failure modes and one uncertainty. Do not repeat the plan."),
    ("replicator", "Give a compact reproducible test matrix with input, expected result, and pass/fail rule."),
    ("archivist", "Summarize known facts, unverified claims, and next action in 3 separate short sections."),
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
        blocked_topics = ("neutron star", "neutron-star", "nötron yıldız", "nötron-yıldız")
        if any(topic in question.casefold() for topic in blocked_topics):
            raise ValueError("Neutron-star research is outside this workflow")
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
                f"{item['role']}: {item['output'][:500]}" for item in steps
            )
            prompt = (
                f"Domain: {domain}\nMission: {question}\nRole assignment: {assignment}\n"
                f"Earlier role notes (unverified; use only if relevant):\n{earlier or '(none)'}\n"
                "Respond only with the deliverable requested for your role in Turkish. "
                "Use at most 8 concise bullets. Do not repeat other roles' deliverables. "
                "Do not repeat the whole mission or earlier notes. Do not claim sources, "
                "measurements, tests, or actions that were not supplied. Mark unknowns."
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

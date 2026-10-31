"""Local evidence-gated evaluation of candidate agent versions.

Pure Python policy mechanism. It neither trains models nor deploys software.
Candidates are proposed after score/evidence checks, but require explicit
approval for activation. Preserve the last version for local rollback.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateResult:
    name: str
    passed: int
    total: int
    source_refs: tuple[str, ...]
    reproducible: bool
    safety_pass: bool

    def __post_init__(self) -> None:
        if (not isinstance(self.name, str) or not self.name.strip()
                or type(self.passed) is not int
                or type(self.total) is not int
                or self.total <= 0
                or not 0 <= self.passed <= self.total
                or not isinstance(self.source_refs, tuple)
                or any(not isinstance(x, str) or not x.strip() for x in self.source_refs)
                or type(self.reproducible) is not bool
                or type(self.safety_pass) is not bool):
            raise ValueError("Invalid candidate test or evidence record")

    @property
    def score(self) -> float:
        return self.passed / self.total


class AgentEvaluator:
    """Inspect bounded test evidence, then activate only with approval."""

    def __init__(self, *, baseline: CandidateResult, min_tests: int = 10) -> None:
        if type(min_tests) is not int or min_tests <= 0:
            raise ValueError("min_tests must be positive")
        self.active = baseline
        self.min_tests = min_tests
        self._pending: dict[str, CandidateResult] = {}
        self._previous: CandidateResult | None = None
        self.audit_log: list[dict[str, object]] = []

    def evaluate(self, candidate: CandidateResult) -> dict:
        baseline = self.active
        delta = round(candidate.score - baseline.score, 10)
        passed = (
            candidate.total >= self.min_tests
            and candidate.reproducible
            and candidate.safety_pass
            and bool(candidate.source_refs)
            and delta > 0
        )
        proposal_id: str | None = None
        if passed:
            proposal_id = f"proposal-{len(self.audit_log) + 1}"
            self._pending[proposal_id] = candidate
        status = "proposal" if passed else "rejected"
        self.audit_log.append({
            "action": "evaluate",
            "candidate": candidate.name,
            "baseline": baseline.name,
            "status": status,
            "delta": delta,
        })
        return {
            "status": status,
            "candidate": candidate.name,
            "active": baseline.name,
            "delta": delta,
            "proposal_id": proposal_id,
        }

    def approve(self, proposal_id: str, *, approved: bool = False) -> dict:
        if not approved:
            raise PermissionError("Explicit activation approval required")
        candidate = self._pending.pop(proposal_id)
        self._previous = self.active
        self.active = candidate
        self._pending.clear()
        self.audit_log.append({
            "action": "approve",
            "proposal_id": proposal_id,
            "active": candidate.name,
        })
        return {"active": candidate.name, "previous": self._previous.name}

    def rollback(self, *, approved: bool = False) -> dict:
        if not approved:
            raise PermissionError("Explicit rollback approval required")
        if self._previous is None:
            raise RuntimeError("No previous candidate to restore")
        prior = self.active
        self.active = self._previous
        self._previous = prior
        self._pending.clear()
        self.audit_log.append({"action": "rollback", "active": self.active.name})
        return {"active": self.active.name}

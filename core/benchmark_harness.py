"""Small deterministic, local benchmark harness for agent candidate proposals.

This module does not download tasks, run commands, call network services or
deploy agents. A caller explicitly provides a responder callable. Two equal
local passes are a repeatability check, not independent scientific replication.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Sequence

from core.agent_evolution import CandidateResult


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    prompt: str
    expected: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip()
               for value in (self.case_id, self.prompt, self.expected)):
            raise ValueError("Benchmark case fields must be nonempty strings")


def _canonical_cases(cases: Sequence[BenchmarkCase]) -> list[dict[str, str]]:
    if not cases or len(cases) > 50:
        raise ValueError("Benchmark must include 1 to 50 cases")
    if not all(isinstance(case, BenchmarkCase) for case in cases):
        raise ValueError("Benchmark contains an invalid case")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Duplicate benchmark case identifiers")
    return [
        {"id": case.case_id, "prompt": case.prompt, "expected": case.expected}
        for case in sorted(cases, key=lambda item: item.case_id)
    ]


def benchmark_sha256(cases: Sequence[BenchmarkCase]) -> str:
    """Hash canonical test input/expected answer content (not model claims)."""
    canonical = _canonical_cases(cases)
    encoded = json.dumps(
        canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_benchmark(
    name: str,
    cases: Sequence[BenchmarkCase],
    responder: Callable[[str], str],
    *,
    source_refs: tuple[str, ...],
    safety_pass: bool,
) -> CandidateResult:
    """Execute each case twice, record strict score and local repeatability.

    Failing calls are treated as wrong; the caller has to opt into the
    responder and controls any external costs or side effects it might cause.
    """
    canonical = _canonical_cases(cases)
    digest = benchmark_sha256(cases)
    outputs: list[list[str | None]] = []
    for _ in range(2):
        single_pass: list[str | None] = []
        for case in canonical:
            try:
                answer = responder(case["prompt"])
                single_pass.append(answer if isinstance(answer, str) else None)
            except Exception:
                single_pass.append(None)
        outputs.append(single_pass)
    passed = sum(
        actual == case["expected"]
        for actual, case in zip(outputs[0], canonical)
    )
    reproducible = (
        outputs[0] == outputs[1]
        and all(answer is not None for answer in outputs[0])
    )
    return CandidateResult(
        name=name,
        passed=passed,
        total=len(canonical),
        source_refs=source_refs,
        reproducible=reproducible,
        safety_pass=safety_pass,
        benchmark_sha256=digest,
    )

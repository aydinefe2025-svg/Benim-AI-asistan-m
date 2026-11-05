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


def run_paired_benchmark(
    baseline_name: str,
    candidate_name: str,
    cases: Sequence[BenchmarkCase],
    baseline_responder: Callable[[str], str],
    candidate_responder: Callable[[str], str],
    *,
    source_refs: tuple[str, ...],
    safety_pass: bool,
) -> dict:
    """Compare a no-memory baseline and a candidate on identical bounded cases.

    Each responder runs twice per case. The result records exact-match deltas
    and per-case improvements/regressions, but never returns prompt/output text.
    A caller explicitly supplies both responders; this function does not access
    memory stores, call providers, or approve a candidate.
    """
    if (not isinstance(baseline_name, str) or not baseline_name.strip()
            or not isinstance(candidate_name, str) or not candidate_name.strip()
            or baseline_name == candidate_name):
        raise ValueError("Distinct nonempty baseline and candidate names are required")
    if not callable(baseline_responder) or not callable(candidate_responder):
        raise ValueError("Both benchmark responders must be callable")
    if type(safety_pass) is not bool:
        raise ValueError("safety_pass must be boolean")
    if (not isinstance(source_refs, tuple) or not source_refs
            or any(not isinstance(item, str) or not item.strip() for item in source_refs)):
        raise ValueError("At least one benchmark source reference is required")

    canonical = _canonical_cases(cases)
    digest = benchmark_sha256(cases)
    responders = {
        "baseline": baseline_responder,
        "candidate": candidate_responder,
    }
    observed: dict[str, list[list[str | None]]] = {
        "baseline": [[], []],
        "candidate": [[], []],
    }
    for pass_index in range(2):
        for case in canonical:
            for label, responder in responders.items():
                try:
                    output = responder(case["prompt"])
                    observed[label][pass_index].append(
                        output if isinstance(output, str) else None
                    )
                except Exception:
                    # No error content is returned; provider exceptions may contain secrets.
                    observed[label][pass_index].append(None)

    scores = {"baseline": 0, "candidate": 0}
    case_outcomes = []
    for index, case in enumerate(canonical):
        baseline_answer = observed["baseline"][0][index]
        candidate_answer = observed["candidate"][0][index]
        baseline_pass = baseline_answer == case["expected"]
        candidate_pass = candidate_answer == case["expected"]
        scores["baseline"] += int(baseline_pass)
        scores["candidate"] += int(candidate_pass)
        outcome = (
            "improved" if candidate_pass and not baseline_pass
            else "regressed" if baseline_pass and not candidate_pass
            else "unchanged"
        )
        case_outcomes.append({
            "case_id": case["id"],
            "baseline_pass": baseline_pass,
            "candidate_pass": candidate_pass,
            "outcome": outcome,
        })

    total = len(canonical)
    reproducibility = {
        label: (
            observed[label][0] == observed[label][1]
            and all(answer is not None for answer in observed[label][0])
        )
        for label in responders
    }
    baseline = CandidateResult(
        name=baseline_name, passed=scores["baseline"], total=total,
        source_refs=source_refs, reproducible=reproducibility["baseline"],
        safety_pass=safety_pass, benchmark_sha256=digest,
    )
    candidate = CandidateResult(
        name=candidate_name, passed=scores["candidate"], total=total,
        source_refs=source_refs, reproducible=reproducibility["candidate"],
        safety_pass=safety_pass, benchmark_sha256=digest,
    )
    return {
        "baseline": baseline,
        "candidate": candidate,
        "delta": round(candidate.score - baseline.score, 10),
        "benchmark_sha256": digest,
        "reproducible": reproducibility,
        "case_results": case_outcomes,
        "improved_case_ids": [item["case_id"] for item in case_outcomes
                              if item["outcome"] == "improved"],
        "regressed_case_ids": [item["case_id"] for item in case_outcomes
                               if item["outcome"] == "regressed"],
    }

def run_colony_memory_benchmark(
    colony,
    agent_id: str,
    cases: Sequence[BenchmarkCase],
    *,
    client,
    model: str,
    source_refs: tuple[str, ...],
    safety_pass: bool = False,
) -> dict:
    """Measure one colony agent with accepted lessons off vs on.

    Each condition runs twice on the same cases (four responder calls per case).
    This helper performs no calls itself beyond the explicitly supplied
    client.chat responder. Keep suites to at most 10 cases (40 model calls)
    and use a local/mock client for free validation before any paid provider.
    Raw prompts and model outputs are never included in the returned report.
    """
    from core.agent_colony import AgentColony

    if not isinstance(colony, AgentColony):
        raise ValueError("colony must be an AgentColony")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("agent_id is required")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model is required")
    if not callable(getattr(client, "chat", None)):
        raise ValueError("client must provide a callable chat method")
    canonical = _canonical_cases(cases)
    if len(canonical) > 10:
        raise ValueError("Colony benchmark is limited to 10 cases (40 model calls)")
    # Fail before invoking the responder if the agent does not exist.
    colony.get(agent_id)
    lesson_count = len(colony.lessons(agent_id))

    def respond(prompt: str, *, include_lessons: bool) -> str:
        result = colony.run(
            agent_id, prompt, client=client, model=model,
            include_lessons=include_lessons,
        )
        return result["output"]

    result = run_paired_benchmark(
        "no-approved-lessons",
        "accepted-lessons-enabled",
        cases,
        lambda prompt: respond(prompt, include_lessons=False),
        lambda prompt: respond(prompt, include_lessons=True),
        source_refs=source_refs,
        safety_pass=safety_pass,
    )
    return {
        **result,
        "memory_lessons_available": lesson_count,
        "comparison": "accepted_feedback_retrieval_only",
        "model_weights_updated": False,
    }

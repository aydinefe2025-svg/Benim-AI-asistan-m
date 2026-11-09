"""Bounded autonomous candidate generation and evaluation for CANO.

The cycle generates one reusable lesson, tests it beside current approved memory
on a fixed human-labeled suite, and records only a pending proposal when it
improves every measured case set. It never changes model weights or activates
the candidate automatically.
"""
from __future__ import annotations

import re

from core.agent_review_loop import AgentReviewLoop
from core.provider_failure import failure_category
from core.benchmark_harness import (
    BenchmarkCase,
    parse_memory_benchmark_cases,
    run_paired_benchmark,
)


_SENSITIVE_TOKEN = re.compile(
    r"(?i)(AIza[0-9A-Za-z_-]{20,}|gsk_[0-9A-Za-z_-]{20,}|"
    r"gh[pousr]_[0-9A-Za-z]{20,}|sk-[0-9A-Za-z_-]{20,}|"
    r"postgres(?:ql)?://|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})"
)


def _reject_obvious_sensitive_text(value: str) -> None:
    if _SENSITIVE_TOKEN.search(value):
        raise ValueError("Secret-like or personal text is not allowed in the improvement cycle")


def generate_lesson_candidate(review, *, client, model):
    """Generate one small behavior rule from the review cycle, not a model update."""
    if not isinstance(review, dict):
        raise ValueError("Review record required")
    critique = review.get("critique")
    revision = review.get("revision")
    if (not isinstance(critique, str) or not critique.strip()
            or not isinstance(revision, str) or not revision.strip()
            or len(critique) > 12_000 or len(revision) > 12_000):
        raise ValueError("Review evidence is invalid")
    system = (
        "CANO improvement candidate. Return exactly one short, reusable behavior "
        "rule in Turkish, maximum 500 characters. Do not repeat names, credentials, "
        "private details, research conclusions, or task-specific facts. Use only a "
        "general process lesson supported by both the critique and revision. "
        "The result is an untrusted proposal and will not be activated automatically."
    )
    prompt = (
        "Critique:\n" + critique[:6000] + "\n\nRevised draft:\n"
        + revision[:6000] + "\n\nReturn only the proposed rule."
    )
    _reject_obvious_sensitive_text(critique + "\n" + revision)
    candidate = client.chat(model, system, prompt)
    if not isinstance(candidate, str):
        raise ValueError("Candidate lesson was not text")
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if not 20 <= len(candidate) <= 500:
        raise ValueError("Candidate lesson length is outside the allowed range")
    _reject_obvious_sensitive_text(candidate)
    return candidate


def evaluate_lesson_candidate(
    colony,
    agent_id: str,
    lesson: str,
    cases: tuple[BenchmarkCase, ...],
    *,
    client,
    model: str,
    dataset_ref: str,
) -> dict:
    """Compare approved memory with approved memory plus one isolated candidate.

    Five labeled cases maximum; two repetitions per case and condition (up to 20
    provider calls). Outputs/prompts are not returned or persisted.
    """
    if not isinstance(lesson, str) or not 20 <= len(lesson.strip()) <= 500:
        raise ValueError("Candidate lesson must be 20 to 500 characters")
    _reject_obvious_sensitive_text(lesson)
    if not isinstance(dataset_ref, str) or not dataset_ref.strip() or len(dataset_ref) > 120:
        raise ValueError("A short benchmark label/version is required")
    if not isinstance(cases, tuple) or not 5 <= len(cases) <= 5:
        raise ValueError("Exactly five human-labeled cases are required")
    if any(not isinstance(case, BenchmarkCase) for case in cases):
        raise ValueError("Invalid benchmark case")
    for case in cases:
        _reject_obvious_sensitive_text(case.prompt + "\n" + case.expected)
    baseline_responder = lambda prompt: colony.run(
        agent_id, prompt, client=client, model=model,
        include_lessons=True,
    )["output"]
    candidate_responder = lambda prompt: colony.run(
        agent_id, prompt, client=client, model=model,
        include_lessons=True, additional_lessons=(lesson,),
    )["output"]
    measured = run_paired_benchmark(
        "approved-memory", "candidate-memory", cases,
        baseline_responder, candidate_responder,
        source_refs=(dataset_ref.strip(),), safety_pass=False,
    )
    # An exact-match score is deliberately only a proposal gate. A human must
    # inspect the lesson and benchmark before it enters future task context.
    eligible = (
        measured["reproducible"]["baseline"]
        and measured["reproducible"]["candidate"]
        and measured["delta"] > 0
        and not measured["regressed_case_ids"]
    )
    return {
        **measured,
        "eligible": eligible,
        "model_weights_updated": False,
        "candidate_activated": False,
    }


def run_bounded_improvement_cycle(
    colony,
    author_id: str,
    reviewer_id: str,
    task: str,
    cases_json: str,
    dataset_ref: str,
    *,
    client,
    model: str,
) -> dict:
    """Run one reviewed task, derive one lesson, compare it, and save a pending candidate.

    Max provider calls: 4 review/candidate calls plus 20 benchmark calls.
    """
    cases = parse_memory_benchmark_cases(cases_json, max_cases=5)
    if len(cases) != 5:
        raise ValueError("Five human-labeled cases are required")
    if not isinstance(task, str) or not task.strip() or len(task) > 1200:
        raise ValueError("Task must contain 1 to 1,200 characters")
    _reject_obvious_sensitive_text(task)
    if not isinstance(dataset_ref, str) or not dataset_ref.strip() or len(dataset_ref) > 120:
        raise ValueError("Benchmark label/version is required")
    review = AgentReviewLoop(colony).execute(
        author_id, reviewer_id, task, client=client, model=model)
    try:
        lesson = generate_lesson_candidate(review, client=client, model=model)
        measured = evaluate_lesson_candidate(
            colony, author_id, lesson, cases, client=client, model=model,
            dataset_ref=dataset_ref,
        )
    except Exception as exc:
        # Keep the completed review durable, but never expose provider exception
        # text or save an untested candidate lesson.
        return {
            "status": "blocked",
            "review_id": review["id"],
            "lesson": None,
            "feedback_id": None,
            "benchmark": None,
            "provider_calls_max": 24,
            "model_weights_updated": False,
            "candidate_activated": False,
            "failure_category": failure_category(exc),
        }
    feedback_id = None
    if measured["eligible"]:
        evidence = (
            f"benchmark_sha256={measured['benchmark_sha256']}; "
            f"candidate={measured['candidate'].passed}/{measured['candidate'].total}; "
            f"baseline={measured['baseline'].passed}/{measured['baseline'].total}; "
            f"regressions=0; model={model}; review={review['id']}"
        )
        try:
            feedback_id = colony.feedback(
                author_id, "CANO bounded improvement proposal " + dataset_ref.strip(),
                lesson, evidence, accepted=False,
            )
        except Exception:
            return {
                "status": "blocked",
                "review_id": review["id"],
                "lesson": None,
                "feedback_id": None,
                "benchmark": None,
                "provider_calls_max": 24,
                "model_weights_updated": False,
                "candidate_activated": False,
            }
    safe_result = {
        "status": "review_pending" if feedback_id else "not_improved",
        "review_id": review["id"],
        "lesson": lesson,
        "feedback_id": feedback_id,
        "benchmark": {
            "dataset_ref": dataset_ref.strip(),
            "baseline_passed": measured["baseline"].passed,
            "candidate_passed": measured["candidate"].passed,
            "total_cases": measured["baseline"].total,
            "delta": measured["delta"],
            "improved_case_ids": measured["improved_case_ids"],
            "regressed_case_ids": measured["regressed_case_ids"],
            "reproducible": measured["reproducible"],
            "sha256": measured["benchmark_sha256"],
        },
        "provider_calls_max": 24,
        "model_weights_updated": False,
        "candidate_activated": False,
    }
    return safe_result

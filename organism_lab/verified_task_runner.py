"""Bounded offline task runner with an explicit evidence boundary.

A deterministic primitive may compute a useful result, but without an
independently supplied oracle it is not labeled scientifically verified.
The optional local Ollama candidate cannot override a deterministic result.
"""
import hashlib
import json
from .bounded_task_execution import execute, gate_result
from .local_candidate_evaluation import evaluate_candidate


def run_job(job, *, expected=None, prefer_local_model=False, transport=None):
    """Run a supported job once; no shell, arbitrary Python execution, or worker creation."""
    result = execute(job)
    encoded = json.dumps(job, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    task_sha256 = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    status = ("computed_unverified" if expected is None
              else gate_result(result, expected=expected)["status"])
    outcome = {
        "task_sha256": task_sha256,
        "task_type": job["type"],
        "result": result,
        "status": status,
        "model_invoked": bool(prefer_local_model),
    }
    if prefer_local_model:
        proposal = evaluate_candidate(job, expected=result, transport=transport)
        outcome["model_status"] = proposal["status"]
        if "reason" in proposal:
            outcome["model_reason"] = proposal["reason"]
    return outcome

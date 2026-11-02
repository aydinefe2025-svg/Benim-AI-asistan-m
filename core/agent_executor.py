"""Bounded, user-triggered research execution with auditable task states.

This runner never edits code, deploys, spends money intentionally, or claims
independent verification. Provider errors leave the task blocked with context.
"""
from __future__ import annotations

import os
from typing import Callable

from core.task_store import TaskStore
from core.retry_policy import retry_transient

MAX_GOAL_CHARS = 1200


def run_research_task(store: TaskStore, task_id: str, answer: Callable[[str], str], *, sleep=None) -> dict:
    task = store.get(task_id)
    if task["status"] not in {"planned", "blocked"}:
        raise ValueError("Only planned or blocked tasks can be run")
    goal = (task["goal"] or task["title"]).strip()[:MAX_GOAL_CHARS]
    store.transition(task_id, "running", note="User-triggered bounded research started")
    try:
        kwargs = {} if sleep is None else {"sleep": sleep}
        result = retry_transient(lambda: answer(goal), **kwargs)
        if not isinstance(result, str) or not result.strip():
            raise ValueError("Empty provider response")
        result = result.strip()[:12000]
        # Model output is an unverified draft, never independent evidence.
        store.finish_draft(task_id, result)
        return {"status": "review_pending", "draft": result, "verified": False}
    except Exception:
        store.transition(task_id, "blocked", note="Research provider failed; retry is allowed",
                         blockers=["Provider request failed; check connection or limits"])
        return {"status": "blocked", "draft": "", "verified": False}

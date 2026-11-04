"""Portable, bounded JSON export for research tasks and drafts.

Export only: importing arbitrary JSON into the task ledger is intentionally
not supported until conflict handling and validation are implemented.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from core.research_drafts import load_draft
from core.task_store import TaskStore
from core.archive_integrity import archive_digest

MAX_TASKS = 200
MAX_EXPORT_BYTES = 3_000_000


def export_research_archive(store: TaskStore) -> bytes:
    tasks = store.list()
    if len(tasks) > MAX_TASKS:
        raise ValueError("Too many tasks for one export")
    items = []
    for task in tasks:
        item = dict(task)
        item["draft"] = (store.load_draft(task["id"]) if hasattr(store, "load_draft")
                         else load_draft(store.db_path, task["id"]))
        item["history"] = store.history(task["id"])
        items.append(item)
    payload = {
        "schema": "research-task-export-v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "warning": "Drafts are unverified; this file is a backup, not independent evidence.",
        "tasks": items,
    }
    payload["integrity"] = {"algorithm": "sha256", "digest": archive_digest(payload)}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_EXPORT_BYTES:
        raise ValueError("Export exceeds size limit")
    return encoded

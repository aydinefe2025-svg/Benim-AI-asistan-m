"""Exercise task persistence and owner isolation against PostgreSQL with synthetic rows."""
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.postgres_task_store import PostgresTaskStore


def run(database_url):
    run_id = uuid.uuid4().hex
    owner = "synthetic-task-owner-" + run_id
    other_owner = "synthetic-task-other-" + run_id
    store = PostgresTaskStore(database_url, owner)
    store.initialize()
    task = store.create("Synthetic persistence check", "Verify isolated records")
    store.transition(task["id"], "running", note="Synthetic run")
    store.finish_draft(task["id"], "Synthetic unverified draft")
    reopened = PostgresTaskStore(database_url, owner)
    actual = reopened.get(task["id"])
    assert actual["status"] == "review_pending"
    assert reopened.load_draft(task["id"]) == "Synthetic unverified draft"
    assert len(reopened.history(task["id"])) == 3
    assert reopened.list() == [actual]
    other = PostgresTaskStore(database_url, other_owner)
    assert other.list() == []
    try:
        other.get(task["id"])
    except KeyError:
        pass
    else:
        raise AssertionError("Cross-owner task read succeeded")
    other.create("Other synthetic task", "No cross-owner visibility")
    assert len(reopened.list()) == 1
    return {"status": "verified", "owner_isolation": True,
            "fresh_connection_read": True, "draft_and_history": True,
            "existing_records_deleted": False, "production_data_migrated": False}


if __name__ == "__main__":
    url = os.environ.get("TEST_TASK_DATABASE_URL")
    if not url:
        print(json.dumps({"status": "not_configured"}))
        raise SystemExit(2)
    try:
        print(json.dumps(run(url), sort_keys=True))
    except Exception as exc:
        # Avoid printing exception text because drivers may include connection details.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1)

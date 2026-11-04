"""Real PostgreSQL CANO colony snapshot validation with synthetic owners.

No production user records, externally triggered agents, or paid providers.
Never print a database URL or credentials.
"""
from __future__ import annotations

import os
import uuid
import tempfile
from pathlib import Path

from core.agent_colony import AgentColony
from core.colony_restore import restore_owner_backup

from core.colony_postgres import ColonySnapshotStore



def check_postgres_to_sqlite_recovery(url, suffix):
    """Prove an owner-specific PostgreSQL backup restores into fresh local SQLite."""
    with tempfile.TemporaryDirectory() as folder:
        original = AgentColony(Path(folder) / "original.sqlite3")
        founder = original.create_founder("research", "Research with sources")
        reviewer = original.spawn(founder, "evidence-reviewer", "Review", approved=True)
        original.feedback(founder, "synthetic task", "Keep receipts",
                          "ci-synthetic-evidence", accepted=True)
        with original._db() as db:
            snapshot = {
                "agents": [dict(row) for row in db.execute(
                    "SELECT * FROM colony_agents ORDER BY id")],
                "feedback": [dict(row) for row in db.execute(
                    "SELECT * FROM colony_feedback ORDER BY id")],
                "reviews": [],
                "missions": [],
            }
        owner = "ci-colony-recover-" + suffix
        store = ColonySnapshotStore(url)
        assert store.save_verified(owner, snapshot) is True
        recovered = AgentColony(Path(folder) / "recovered.sqlite3")
        try:
            restore_owner_backup(recovered, store, owner, approved=False)
        except PermissionError:
            pass
        else:
            raise AssertionError("Restore without approval was accepted")
        assert restore_owner_backup(
            recovered, ColonySnapshotStore(url), owner, approved=True) == 2
        assert recovered.get(reviewer)["parent_id"] == founder
        assert recovered.lessons(founder)[0]["lesson"] == "Keep receipts"
        with recovered._db() as db:
            restored_agents = [dict(row) for row in db.execute(
                "SELECT * FROM colony_agents ORDER BY id")]
            restored_feedback = [dict(row) for row in db.execute(
                "SELECT * FROM colony_feedback ORDER BY id")]
        assert restored_agents == snapshot["agents"]
        assert restored_feedback == snapshot["feedback"]
        try:
            restore_owner_backup(recovered, store, owner, approved=True)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Restore overwrote an existing colony")
        unrelated = AgentColony(Path(folder) / "unrelated.sqlite3")
        try:
            restore_owner_backup(
                unrelated, store, "ci-other-" + suffix, approved=True)
        except LookupError:
            pass
        else:
            raise AssertionError("Unrelated owner received a backup")
        with unrelated._db() as db:
            assert db.execute("SELECT count(*) FROM colony_agents").fetchone()[0] == 0

def main():
    url = os.environ["TEST_DATABASE_URL"]
    suffix = uuid.uuid4().hex
    owner, other = "ci-colony-" + suffix, "ci-other-" + suffix
    store = ColonySnapshotStore(url)
    store.initialize()
    original = {
        "agents": [{"id": "synthetic-founder", "role": "research"}],
        "feedback": [{"id": "synthetic-lesson", "accepted": 0}],
        "reviews": [],
        "missions": [{"id": "synthetic-mission", "status": "blocked"}],
    }
    assert store.save_verified(owner, original) is True
    reopened = ColonySnapshotStore(url)
    assert reopened.load(owner) == original, "Reopened connection lost backup"
    assert reopened.load(other) is None, "Another owner accessed a snapshot"
    updated = {**original, "missions": original["missions"] + [
        {"id": "synthetic-recovered", "status": "review_pending"}]}
    assert reopened.save_verified(owner, updated) is True
    assert ColonySnapshotStore(url).load(owner) == updated, "Update readback failed"
    assert ColonySnapshotStore(url).load(other) is None, "Owner isolation broken"
    try:
        store.save_verified("", original)
    except ValueError:
        pass
    else:
        raise AssertionError("Unauthenticated owner accepted")
    assert reopened.load(owner) == updated, "Failed write damaged existing data"
    check_postgres_to_sqlite_recovery(url, suffix)
    print("CANO colony PostgreSQL: verified readback, fresh connection, "
          "owner isolation, update and invalid-owner protection OK")


if __name__ == "__main__":
    main()

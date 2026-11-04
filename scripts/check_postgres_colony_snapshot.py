"""Real PostgreSQL CANO colony snapshot validation with synthetic owners.

No production user records, externally triggered agents, or paid providers.
Never print a database URL or credentials.
"""
from __future__ import annotations

import os
import uuid

from core.colony_postgres import ColonySnapshotStore


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
    print("CANO colony PostgreSQL: verified readback, fresh connection, "
          "owner isolation, update and invalid-owner protection OK")


if __name__ == "__main__":
    main()

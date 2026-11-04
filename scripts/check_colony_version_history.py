"""Validate that replacing a CANO backup never destroys the previous version.

Synthetic owners and rows only, against PostgreSQL 17 CI. No production data.
"""
import os
import uuid

from core.colony_postgres import ColonySnapshotStore


def main():
    url = os.environ["TEST_DATABASE_URL"]
    owner = "ci-cano-history-" + uuid.uuid4().hex
    outsider = owner + "-other"
    store = ColonySnapshotStore(url)
    store.initialize()
    initial = {"agents": [{"id": "synthetic-A"}], "feedback": [],
               "reviews": [], "missions": []}
    newer = {"agents": [{"id": "synthetic-B"}], "feedback": [],
             "reviews": [], "missions": [{"id": "mission-2", "status": "blocked"}]}
    store.save_versioned_verified(owner, initial)
    assert store.load(owner) == initial
    assert store.list_archived(owner) == []

    store.save_versioned_verified(owner, newer)
    assert store.load(owner) == newer
    prior = store.list_archived(owner)
    assert len(prior) == 1, f"Expected one recoverable older version; got {len(prior)}"
    assert store.load_archived(owner, prior[0]["revision"]) == initial
    assert store.load_archived(outsider, prior[0]["revision"]) is None
    assert store.list_archived(outsider) == []

    store.save_versioned_verified(owner, newer)
    assert len(store.list_archived(owner)) == 1, "Duplicate save generated useless history"
    reopened = ColonySnapshotStore(url)
    assert reopened.load_archived(owner, prior[0]["revision"]) == initial
    print("CANO PostgreSQL versioned backup: older snapshot recoverable, "
          "owner isolation, duplicate no-op and fresh-connection readback OK")


if __name__ == "__main__":
    main()

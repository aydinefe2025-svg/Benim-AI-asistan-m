"""Validate that replacing a CANO backup never destroys the previous version.

Synthetic owners and rows only, against PostgreSQL 17 CI. No production data.
"""
import os
import uuid
import json
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from core.agent_colony import AgentColony
from core.colony_restore import restore_empty_colony

from core.colony_postgres import (
    ColonySnapshotStore, MAX_ARCHIVED_REVISIONS_PER_OWNER,
)


def main():
    url = os.environ["TEST_DATABASE_URL"]
    owner = "ci-cano-history-" + uuid.uuid4().hex
    outsider = owner + "-other"
    store = ColonySnapshotStore(url)
    store.initialize()
    initial = {"agents": [{"id": "synthetic-A", "parent_id": None,
                           "generation": 0, "role": "research",
                           "instructions": "CANO recovery test", "state": "active",
                           "created_at": "2026-11-04"}],
               "feedback": [], "reviews": [], "missions": []}
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

    # Real restoration of an archived backup into a new, empty local SQLite
    # colony (as would happen after a Render restart).
    with tempfile.TemporaryDirectory() as folder:
        restored = AgentColony(Path(folder) / "recovered-colony.sqlite3")
        assert restore_empty_colony(
            restored, reopened.load_archived(owner, prior[0]["revision"])) == 1
        assert restored.get("synthetic-A")["role"] == "research"

    # Two simultaneous authorized tabs must not erase either snapshot.
    parallel_owner = owner + "-parallel"
    store.save_versioned_verified(parallel_owner, initial)
    variants = [
        {"agents": [{"id": "parallel-A"}], "feedback": [],
         "reviews": [], "missions": []},
        {"agents": [{"id": "parallel-B"}], "feedback": [],
         "reviews": [], "missions": []},
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda payload: store.save_versioned_verified(
            parallel_owner, payload), variants))
    assert results == [True, True]
    revisions = store.list_archived(parallel_owner)
    assert len(revisions) == 2, "Concurrent writes discarded an old snapshot"
    all_states = [store.load(parallel_owner)] + [
        store.load_archived(parallel_owner, item["revision"]) for item in revisions]
    assert {json.dumps(item, sort_keys=True) for item in all_states} == {
        json.dumps(item, sort_keys=True) for item in [initial] + variants}

    # History capacity must reject a further write instead of pruning any
    # record without the owner's explicit export/maintenance.
    bounded_owner = owner + "-bounded"
    store.save_versioned_verified(bounded_owner, initial)
    for i in range(MAX_ARCHIVED_REVISIONS_PER_OWNER):
        store.save_versioned_verified(bounded_owner, {
            "agents": [{"id": "bounded-" + str(i)}],
            "feedback": [], "reviews": [], "missions": []})
    before = store.load(bounded_owner)
    assert len(store.list_archived(bounded_owner)) == MAX_ARCHIVED_REVISIONS_PER_OWNER
    try:
        store.save_versioned_verified(bounded_owner, {
            "agents": [{"id": "overflow"}], "feedback": [],
            "reviews": [], "missions": []})
    except RuntimeError:
        pass
    else:
        raise AssertionError("Unbounded backups accepted")
    assert store.load(bounded_owner) == before
    assert len(store.list_archived(bounded_owner)) == 20

    print("CANO PostgreSQL versioned backup: older snapshot restored into "
          "fresh SQLite, owner isolation, concurrent snapshots retained, "
          "duplicate no-op and quota fail-closed OK")


if __name__ == "__main__":
    main()

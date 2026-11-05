"""Kill a real Python mission process, then restore from real disposable PostgreSQL 18.

CI ONLY. Refuses production/external database URLs. No API keys, paid providers,
actual user accounts, or model network calls. The second stage exits abruptly
with os._exit, so no Python exception/finally cleanup can save SQLite state.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

from core.agent_colony import AgentColony
from core.cano_command_center import _snapshot, prepare_cano_team
from core.collaborative_mission import CollaborativeMission
from core.colony_postgres import ColonySnapshotStore
from core.colony_restore import restore_owner_backup
from scripts.check_cano_pg_backup_roundtrip import _validate_ci_database


CRASH_EXIT_CODE = 29
STAGES = ("planner", "researcher", "reviewer", "synthesis")


def config():
    url = os.environ.get("TEST_DATABASE_URL", "")
    _validate_ci_database(url)
    if os.environ.get("CANO_CI_ALLOW_DISPOSABLE_DB") != "1":
        raise RuntimeError("Disposable localhost CI database required")
    owner = os.environ.get("CANO_TEST_SYNTHETIC_OWNER", "")
    mission_id = os.environ.get("CANO_TEST_MISSION_ID", "")
    if not owner.startswith("ci-recovery-") or len(owner) > 128:
        raise RuntimeError("Synthetic test-only owner required")
    from uuid import UUID
    try:
        if str(UUID(mission_id)) != mission_id:
            raise ValueError("Bad mission id")
    except (ValueError, AttributeError):
        raise RuntimeError("Synthetic mission id required") from None
    return url, owner, mission_id


def _checkpoint(store, owner, colony, prior):
    current = _snapshot(colony)
    store.save_versioned_verified(
        owner, current, expected_prior=prior[0], archive_prior=False
    )
    prior[0] = current


def seed_and_kill(dbpath):
    url, owner, mission_id = config()
    colony = AgentColony(dbpath)
    assert prepare_cano_team(colony, approved=True) == 7
    store = ColonySnapshotStore(url)
    prior = [None]
    _checkpoint(store, owner, colony, prior)

    class SyntheticCrashClient:
        calls = 0
        def chat(self, model, system, prompt):
            self.calls += 1
            if self.calls == 2:
                # Simulate abrupt death after the first stage was committed to
                # PostgreSQL and while the second model request was in flight.
                os._exit(CRASH_EXIT_CODE)
            return "synthetic unverified planning text"

    CollaborativeMission(colony).execute(
        "CI synthetic interruption and recovery test",
        client=SyntheticCrashClient(), model="synthetic-no-provider",
        mission_id=mission_id,
        on_checkpoint=lambda: _checkpoint(store, owner, colony, prior),
    )
    raise AssertionError("Synthetic process unexpectedly survived the crash")


def reopen_and_resume(dbpath):
    url, owner, mission_id = config()
    store = ColonySnapshotStore(url)
    colony = AgentColony(dbpath)
    assert restore_owner_backup(colony, store, owner, approved=True) == 7
    manager = CollaborativeMission(colony)
    interrupted = manager.get(mission_id)
    assert interrupted["status"] == "blocked"
    assert [x["role"] for x in interrupted["stages"]] == ["planner"]
    prior = [store.load(owner)]

    class SyntheticResumeClient:
        calls = 0
        def chat(self, model, system, prompt):
            self.calls += 1
            return f"synthetic unverified resumed stage {self.calls}"

    client = SyntheticResumeClient()
    result = manager.resume(
        mission_id, client=client, model="synthetic-no-provider",
        on_checkpoint=lambda: _checkpoint(store, owner, colony, prior),
    )
    assert client.calls == 3, "Previously saved planner stage was rerun"
    assert result["model_calls"] == 3
    assert result["status"] == "review_pending"
    assert [stage["role"] for stage in result["stages"]] == list(STAGES)
    # Persist the terminal status after the four intermediate stage checkpoints.
    _checkpoint(store, owner, colony, prior)
    assert store.load(owner) == _snapshot(colony)
    no_op = manager.resume(
        mission_id, client=client, model="synthetic-no-provider"
    )
    assert no_op["model_calls"] == 0
    assert client.calls == 3, "Completed task caused duplicate model calls"


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "orchestrate"
    if phase in ("seed", "recover"):
        _, _, _ = config()
        if len(sys.argv) != 3:
            raise RuntimeError("Synthetic database file argument required")
        if phase == "seed":
            seed_and_kill(Path(sys.argv[2]))
        else:
            reopen_and_resume(Path(sys.argv[2]))
        return
    if phase != "orchestrate":
        raise RuntimeError("Unknown CI-only phase")

    url = os.environ.get("TEST_DATABASE_URL", "")
    _validate_ci_database(url)
    if os.environ.get("CANO_CI_ALLOW_DISPOSABLE_DB") != "1":
        raise RuntimeError("Disposable localhost CI database required")
    owner = "ci-recovery-" + uuid4().hex
    other_owner = "ci-recovery-" + uuid4().hex
    mission_id = str(uuid4())
    store = ColonySnapshotStore(url)
    store.initialize()
    store.verify_schema()
    unrelated = {"agents": [], "feedback": [], "reviews": [], "missions": []}
    store.save_versioned_verified(other_owner, unrelated, expected_prior=None)

    with tempfile.TemporaryDirectory(prefix="cano-process-crash-ci-") as directory:
        root = Path(directory)
        env = os.environ.copy()
        env["CANO_TEST_SYNTHETIC_OWNER"] = owner
        env["CANO_TEST_MISSION_ID"] = mission_id
        seed = subprocess.run(
            [sys.executable, "-m", "scripts.check_cano_pg_interrupted_mission",
             "seed", str(root / "interrupted.sqlite3")],
            env=env, check=False, timeout=60, capture_output=True,
        )
        assert seed.returncode == CRASH_EXIT_CODE, (
            "Mission did not die at the configured second model call"
        )
        mid = store.load(owner)
        assert mid and len(mid["agents"]) == 7
        assert len(mid["missions"]) == 1
        assert mid["missions"][0]["id"] == mission_id
        assert mid["missions"][0]["status"] == "running"
        assert [x["role"] for x in json.loads(mid["missions"][0]["stages"])] == [
            "planner"
        ]
        assert store.load(other_owner) == unrelated

        recovered = subprocess.run(
            [sys.executable, "-m", "scripts.check_cano_pg_interrupted_mission",
             "recover", str(root / "recovered-fresh.sqlite3")],
            env=env, check=False, timeout=90, capture_output=True,
        )
        if recovered.returncode != 0:
            # Never display subprocess output: even test harness errors might
            # include database credentials or external environment details.
            raise AssertionError("Independent fresh-process recovery failed")
        final = store.load(owner)
        assert final and len(final["missions"]) == 1
        assert final["missions"][0]["status"] == "review_pending"
        assert [x["role"] for x in json.loads(final["missions"][0]["stages"])] == list(STAGES)
        assert store.load(other_owner) == unrelated
        try:
            store.save_versioned_verified(
                owner, mid, expected_prior=unrelated, archive_prior=False
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("Stale owner overwrite was accepted")
        assert store.load(owner) == final

    print("PASS: PostgreSQL 18, real Python process kill at stage 2, "
          "owner-specific stage 1 checkpoint, fresh interpreter and SQLite "
          "recovery, 3 remaining model stubs, no duplicates, terminal save, "
          "stale CAS rejection, other-owner isolation")


if __name__ == "__main__":
    main()

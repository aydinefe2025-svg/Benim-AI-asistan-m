"""CANO cockpit end-to-end durable checkpoint and cold restart on real PostgreSQL.

Run only against a disposable CI database, with synthetic owner and fake model.
No public network calls, credentials in output, or live user changes.
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_cano_command_center import FakeStreamlit, FakeModel

from core.agent_colony import AgentColony
from core.cano_command_center import render_cano_command_center
from core.colony_postgres import ColonySnapshotStore
from core.colony_restore import restore_owner_backup
from core.collaborative_mission import CollaborativeMission


def main():
    url = os.environ["TEST_DATABASE_URL"]
    owner = "ci-cockpit-" + uuid.uuid4().hex
    other = owner + "-another"
    store = ColonySnapshotStore(url)
    store.initialize()
    with tempfile.TemporaryDirectory() as folder:
        st = FakeStreamlit(clicks={"cano_prepare_team"})
        fake_model = FakeModel()
        path = str(Path(folder) / "active.sqlite3")
        with patch.dict(os.environ, {"AGENT_COLONY_DB_PATH": path}):
            render_cano_command_center(
                st, answer=fake_model, owner_key=owner, database_url=url)
            founder_snapshot = store.load(owner)
            assert founder_snapshot is not None
            assert len(founder_snapshot["agents"]) == 7
            assert founder_snapshot["missions"] == []

            st.task = "Study synthetic solar topic"
            st.submit = True
            render_cano_command_center(
                st, answer=fake_model, owner_key=owner, database_url=url)
            assert len(fake_model.calls) == 4
            latest = store.load(owner)
            assert len(latest["missions"]) == 1
            assert latest["missions"][0]["status"] == "review_pending"
            assert len(store.list_archived(owner)) >= 1
            assert store.load(other) is None

        # New process-state simulation: create an entirely new empty local DB,
        # use a fresh PostgreSQL connection, restore with explicit authorization.
        reopened = ColonySnapshotStore(url)
        cold = AgentColony(Path(folder) / "cold-restart.sqlite3")
        count = restore_owner_backup(cold, reopened, owner, approved=True)
        assert count == 7
        saved_mission = latest["missions"][0]
        recovered = CollaborativeMission(cold).get(saved_mission["id"])
        assert recovered["status"] == "review_pending"
        assert len(recovered["stages"]) == 4
        assert recovered["stages"][-1]["output"] == "CANO aşama cevabı 4"
        try:
            restore_owner_backup(cold, reopened, owner, approved=True)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Unexpected overwrite of populated colony")
        assert reopened.load(other) is None
        print("CANO PostgreSQL autosave: 7 roles and 4-stage task persisted; "
              "fresh DB restore, owner isolation and overwrite refusal verified")


if __name__ == "__main__":
    main()

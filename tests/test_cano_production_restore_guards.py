"""Production-side regression tests for owner-preserving sidebar restore actions.

All data is synthetic SQLite and a deterministic PostgreSQL CAS mock.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.agent_colony import AgentColony
from core.cano_command_center import _snapshot
from core.colony_panel import render_colony_panel


class Upload:
    def __init__(self, content):
        self.raw = content
        self.size = len(content)

    def getvalue(self):
        return self.raw


class FakeSidebar:
    def __init__(self, *, clicked=None, confirmed=False, upload=None):
        self.sidebar = self
        self.session_state = {}
        self.clicked = clicked
        self.confirmed = confirmed
        self.upload = upload
        self.messages = []

    def expander(self, *args, **kwargs): return self
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def caption(self, *args, **kwargs): return None
    def checkbox(self, *args, **kwargs): return self.confirmed
    def button(self, label, key=None, **kwargs): return key == self.clicked
    def file_uploader(self, *args, **kwargs): return self.upload
    def warning(self, message): self.messages.append(("warning", str(message)))
    def error(self, message): self.messages.append(("error", str(message)))
    def success(self, message): self.messages.append(("success", str(message)))
    def rerun(self): self.messages.append(("rerun", ""))


class SyntheticStore:
    def __init__(self, current, *, reject_writes=False):
        self.current = copy.deepcopy(current)
        self.reject_writes = reject_writes
        self.writes = []

    def verify_schema(self): pass
    def load(self, owner):
        if owner != "owner-A": raise PermissionError("unexpected owner")
        return copy.deepcopy(self.current)
    def save_versioned_verified(self, owner, payload, *,
                                expected_prior, archive_prior=True):
        if owner != "owner-A" or self.reject_writes or expected_prior != self.current:
            raise RuntimeError("PostgreSQL owner CAS rejected")
        self.current = copy.deepcopy(payload)
        self.writes.append(copy.deepcopy(payload))
        return True


def founder_snapshot():
    return {"agents": [{
        "id": "existing-founder", "parent_id": None, "generation": 0,
        "role": "research", "instructions": "Research safely", "state": "active",
        "created_at": "2026-11-05T00:00:00+00:00"}],
        "feedback": [], "reviews": [], "missions": []}


class ProductionRestoreGuards(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "owner-empty.sqlite3"
        self.colony = AgentColony(self.path)

    def show(self, ui, store, *, baseline):
        ui.session_state["_cano_backup_owner_key"] = "owner-A"
        ui.session_state["_cano_backup_expected"] = copy.deepcopy(baseline)
        with (
            patch("core.colony_panel._session_database_path", return_value=str(self.path)),
            patch("core.colony_panel.ColonySnapshotStore", return_value=store),
        ):
            render_colony_panel(
                ui, owner_key="owner-A", database_url="postgresql://synthetic")

    def test_json_import_requires_owner_backup_before_mutating_local(self):
        payload = founder_snapshot()
        ui = FakeSidebar(clicked="colony_json_backup_restore",
                         upload=Upload(json.dumps(payload).encode()))
        store = SyntheticStore(_snapshot(self.colony), reject_writes=True)
        self.show(ui, store, baseline=store.current)
        self.assertEqual(_snapshot(self.colony)["agents"], [])
        self.assertFalse(any(level == "success" for level, _ in ui.messages))

    def test_json_import_writes_and_verifies_owner_snapshot(self):
        payload = founder_snapshot()
        ui = FakeSidebar(clicked="colony_json_backup_restore",
                         upload=Upload(json.dumps(payload).encode()))
        store = SyntheticStore(_snapshot(self.colony))
        self.show(ui, store, baseline=store.current)
        self.assertEqual(len(_snapshot(self.colony)["agents"]), 1)
        self.assertGreaterEqual(len(store.writes), 1)
        self.assertEqual(store.current, _snapshot(self.colony))
        self.assertTrue(any(level == "success" for level, _ in ui.messages))

    def test_empty_local_cannot_erase_existing_owner_backup_by_creating_founder(self):
        previous = founder_snapshot()
        ui = FakeSidebar(clicked="colony_founder")
        store = SyntheticStore(previous)
        self.show(ui, store, baseline=previous)
        self.assertEqual(store.current, previous)
        self.assertEqual(_snapshot(self.colony)["agents"], [])
        self.assertFalse(store.writes)

    def test_current_owner_restore_binds_remote_snapshot_for_next_checkpoint(self):
        previous = founder_snapshot()
        ui = FakeSidebar(clicked="colony_postgres_restore", confirmed=True)
        store = SyntheticStore(previous)
        self.show(ui, store, baseline=None)
        self.assertEqual(len(_snapshot(self.colony)["agents"]), 1)
        self.assertEqual(ui.session_state["_cano_backup_expected"], previous)
        self.assertEqual(ui.session_state["_cano_backup_owner_key"], "owner-A")
        self.assertTrue(any(level == "success" for level, _ in ui.messages))


if __name__ == "__main__":
    unittest.main()

"""Fail-closed Streamlit owner-backup restore approval regression."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.colony_panel import render_colony_panel
from core.agent_colony import AgentColony


class FakeStreamlit:
    def __init__(self, *, confirmed):
        self.confirmed = confirmed
        self.sidebar = self
        self.messages = []
        self.session_state = {}

    def expander(self, *args, **kwargs): return self
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def caption(self, text): return None
    def button(self, label, *, key): return key == "colony_postgres_restore"
    def checkbox(self, label, *, key, value=False): return self.confirmed
    def file_uploader(self, label, *, key, type): return None
    def warning(self, text): self.messages.append(("warning", text))
    def error(self, text): self.messages.append(("error", text))
    def success(self, text): self.messages.append(("success", text))
    def rerun(self): self.messages.append(("rerun", ""))


class RestoreUIApprovalTests(unittest.TestCase):
    def test_unauthorized_click_must_not_read_postgres(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.sqlite3"
            st = FakeStreamlit(confirmed=False)
            with patch("core.colony_panel._session_database_path", return_value=str(path)), \
                 patch("core.colony_panel.ColonySnapshotStore") as fake_store:
                render_colony_panel(st, owner_key="authenticated-user",
                                    database_url="postgresql://test")
                fake_store.assert_not_called()
            with AgentColony(path)._db() as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM colony_agents").fetchone()[0], 0)
            self.assertTrue(any(level == "warning" for level, _ in st.messages))


    def test_confirmed_owner_restore_populates_empty_colony_and_reruns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.sqlite3"
            st = FakeStreamlit(confirmed=True)
            payload = {"agents": [{
                "id": "owner-agent", "parent_id": None, "generation": 0,
                "role": "research", "instructions": "Safe", "state": "active",
                "created_at": "2026-01-01"}],
                "feedback": [], "reviews": [], "missions": []}
            with patch("core.colony_panel._session_database_path", return_value=str(path)), \
                 patch("core.colony_panel.ColonySnapshotStore") as fake_store:
                fake_store.return_value.load.return_value = payload
                render_colony_panel(st, owner_key="authenticated-user",
                                    database_url="postgresql://test")
                self.assertEqual(fake_store.return_value.load.call_count, 2)
                fake_store.return_value.load.assert_any_call("authenticated-user")
                self.assertEqual(st.session_state["_cano_backup_owner_key"], "authenticated-user")
                self.assertEqual(st.session_state["_cano_backup_expected"], payload)
            self.assertEqual(AgentColony(path).get("owner-agent")["role"], "research")
            self.assertTrue(any(level == "success" for level, _ in st.messages))
            self.assertTrue(any(level == "rerun" for level, _ in st.messages))

    def test_archived_backup_requires_fresh_owner_confirmation(self):
        from unittest.mock import Mock
        from core.colony_restore import restore_owner_backup
        with tempfile.TemporaryDirectory() as tmp:
            target = AgentColony(Path(tmp) / "old-restore.sqlite3")
            store = Mock()
            store.load_archived.return_value = {
                "agents": [{"id": "historical-founder", "parent_id": None,
                            "generation": 0, "role": "research",
                            "instructions": "Safe past instructions",
                            "state": "active", "created_at": "2026-11-04"}],
                "feedback": [], "reviews": [], "missions": []}
            with self.assertRaises(PermissionError):
                restore_owner_backup(target, store, "authenticated-user",
                                     approved=False, revision=11)
            store.load_archived.assert_not_called()
            self.assertEqual(restore_owner_backup(
                target, store, "authenticated-user",
                approved=True, revision=11), 1)
            store.load_archived.assert_called_once_with("authenticated-user", 11)
            self.assertEqual(target.get("historical-founder")["role"], "research")
            with self.assertRaises(RuntimeError):
                restore_owner_backup(target, store, "authenticated-user",
                                     approved=True, revision=11)

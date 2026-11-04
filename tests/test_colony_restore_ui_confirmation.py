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
                fake_store.return_value.load.assert_called_once_with("authenticated-user")
            self.assertEqual(AgentColony(path).get("owner-agent")["role"], "research")
            self.assertTrue(any(level == "success" for level, _ in st.messages))
            self.assertTrue(any(level == "rerun" for level, _ in st.messages))
"""Regression: sidebar PostgreSQL backup must not bypass owner snapshot CAS.

Synthetic local SQLite + isolated mocked remote boundary only; no credentials
or account data. Tests target real Streamlit sidebar execution entry point.
"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.agent_colony import AgentColony
from core.cano_command_center import _snapshot
from core.colony_panel import render_colony_panel
from tests.test_cano_command_center import FakeStreamlit


class PanelFake(FakeStreamlit):
    def __init__(self, clicks=None):
        super().__init__(clicks=clicks or {"colony_postgres_save"})
        self.sidebar = self

    def text_input(self, label, **kwargs):
        return ""


class SidebarBackupCASTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "colony.sqlite3"
        colony = AgentColony(self.path)
        colony.create_founder("research", "Research safely")
        self.current_payload = _snapshot(colony)
        self.base_payload = copy.deepcopy(self.current_payload)
        self.base_payload["agents"][0]["instructions"] = "Earlier saved instructions"

    def _render(self, st, store):
        with patch("core.colony_panel._session_database_path",
                   return_value=str(self.path)), patch(
                     "core.colony_panel.ColonySnapshotStore",
                     return_value=store
                   ):
            render_colony_panel(st, owner_key="owner-A",
                                database_url="postgresql://synthetic")

    def test_sidebar_stale_tab_cannot_overwrite_newer_remote_backup(self):
        st = PanelFake()
        st.session_state.update({
            "_cano_backup_owner_key": "owner-A",
            "_cano_backup_expected": copy.deepcopy(self.base_payload),
        })
        newer = copy.deepcopy(self.base_payload)
        newer["agents"][0]["instructions"] = "Other tab's newer research"
        remote = {"payload": newer}

        class SimulatedRemote:
            def verify_schema(self): return None
            def save_versioned_verified(self, owner, payload, *,
                                        expected_prior=None):
                if expected_prior is not None and expected_prior != remote["payload"]:
                    raise RuntimeError("Stale writer refused")
                remote["payload"] = copy.deepcopy(payload)
                return True

        self._render(st, SimulatedRemote())
        self.assertEqual(remote["payload"], newer,
                         "Sidebar overwrote the more recent owner backup")
        self.assertEqual(
            st.session_state["_cano_backup_expected"], self.base_payload,
            "Failed save must not move expected snapshot forward")

    def test_sidebar_refuses_write_without_owner_bound_baseline(self):
        from unittest.mock import Mock
        st = PanelFake()
        store = Mock()
        self._render(st, store)
        store.save_versioned_verified.assert_not_called()

    def test_sidebar_refuses_write_after_account_switch(self):
        from unittest.mock import Mock
        st = PanelFake()
        st.session_state.update({
            "_cano_backup_owner_key": "owner-B",
            "_cano_backup_expected": copy.deepcopy(self.base_payload),
        })
        store = Mock()
        self._render(st, store)
        store.save_versioned_verified.assert_not_called()

    def test_sidebar_uses_baseline_cas_and_advances_only_after_success(self):
        from unittest.mock import Mock
        st = PanelFake()
        st.session_state.update({
            "_cano_backup_owner_key": "owner-A",
            "_cano_backup_expected": copy.deepcopy(self.base_payload),
        })
        store = Mock()
        self._render(st, store)
        store.save_versioned_verified.assert_called_once_with(
            "owner-A", self.current_payload, expected_prior=self.base_payload)
        self.assertEqual(st.session_state["_cano_backup_expected"],
                         self.current_payload)


    def test_storage_caption_matches_owner_database_configuration(self):
        from unittest.mock import Mock

        persistent = PanelFake(clicks={"no_action"})
        with patch("core.colony_panel._session_database_path",
                   return_value=str(self.path)), patch(
                     "core.colony_panel.ColonySnapshotStore", return_value=Mock()
                   ):
            render_colony_panel(
                persistent, owner_key="owner-A",
                database_url="postgresql://synthetic")
        persistent_text = " ".join(persistent.messages)
        self.assertIn("hesaba bağlı PostgreSQL yedeğine CAS doğrulamasıyla kaydedilir",
                      persistent_text)
        self.assertNotIn("Kayıtlar oturuma özel geçici SQLite", persistent_text)

        local = PanelFake(clicks={"no_action"})
        with patch("core.colony_panel._session_database_path",
                   return_value=str(self.path)):
            render_colony_panel(local)
        local_text = " ".join(local.messages)
        self.assertIn("Kayıtlar oturuma özel geçici SQLite", local_text)
        self.assertNotIn("hesaba bağlı PostgreSQL yedeğine CAS", local_text)


if __name__ == "__main__":
    unittest.main()

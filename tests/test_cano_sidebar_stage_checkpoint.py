"""Regression: sidebar four-stage missions must durably checkpoint each stage.

The remote store is a deterministic in-memory CAS boundary; no real credentials
or provider calls are used. This exercises the actual Streamlit panel wiring.
"""
import copy
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from core.agent_colony import AgentColony
from core.cano_command_center import _snapshot, prepare_cano_team
from core.collaborative_mission import CollaborativeMission
from core.colony_panel import render_colony_panel


class PanelUI:
    def __init__(self, *, goal="Test the research", submit=False, clicks=()):
        self.sidebar = self
        self.session_state = {}
        self.goal = goal
        self.submit = submit
        self.clicks = set(clicks)
        self.messages = []

    def expander(self, *args, **kwargs): return nullcontext()
    def form(self, *args, **kwargs): return nullcontext()
    def caption(self, message): self.messages.append(str(message))
    def info(self, message): self.messages.append(str(message))
    def warning(self, message): self.messages.append(str(message))
    def error(self, message): self.messages.append(str(message))
    def success(self, message): self.messages.append(str(message))
    def subheader(self, message): self.messages.append(str(message))
    def write(self, *args): return None
    def rerun(self): return None
    def selectbox(self, label, options, **kwargs): return options[0]
    def text_input(self, label, **kwargs): return ""
    def text_area(self, label, **kwargs):
        return self.goal if label == "Ortak araştırma görevi" else ""
    def checkbox(self, label, **kwargs): return False
    def file_uploader(self, *args, **kwargs): return None
    def download_button(self, *args, **kwargs): return None
    def button(self, label, key=None, **kwargs):
        token = key or label
        if token in self.clicks:
            self.clicks.remove(token)
            return True
        return False
    def form_submit_button(self, label, **kwargs):
        if "CANO ekibini birlikte çalıştır" in label and self.submit:
            self.submit = False
            return True
        return False


class SyntheticOwnerStore:
    def __init__(self, initial, *, reject_stage=None):
        self.current = copy.deepcopy(initial)
        self.saved = []
        self.reject_stage = reject_stage

    def verify_schema(self): return None

    def save_versioned_verified(self, owner, payload, *, expected_prior, archive_prior=True):
        if owner != "owner-test" or expected_prior != self.current:
            raise RuntimeError("Stale or incorrect owner snapshot")
        stage_count = len(payload["missions"][0]["stages"]) if payload["missions"] else 0
        # Persisted mission rows contain serialized stage JSON.
        if payload["missions"]:
            import json
            stage_count = len(json.loads(payload["missions"][0]["stages"]))
        if stage_count == self.reject_stage:
            raise RuntimeError("Synthetic PostgreSQL write failure")
        self.current = copy.deepcopy(payload)
        self.saved.append((stage_count, archive_prior))


class SidebarStageCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "colony.sqlite3"
        self.colony = AgentColony(self.path)
        prepare_cano_team(self.colony, approved=True)

    def _render(self, st, store, answer):
        st.session_state["_cano_backup_owner_key"] = "owner-test"
        st.session_state["_cano_backup_expected"] = copy.deepcopy(store.current)
        with patch("core.colony_panel._session_database_path", return_value=str(self.path)), \
             patch("core.colony_panel.ColonySnapshotStore", return_value=store):
            render_colony_panel(
                st, answer=answer, owner_key="owner-test",
                database_url="postgresql://synthetic",
            )

    def test_four_stages_are_saved_before_each_next_model_call(self):
        st = PanelUI(submit=True)
        store = SyntheticOwnerStore(_snapshot(self.colony))
        calls = []
        def model(prompt):
            calls.append(prompt)
            if len(calls) > 1:
                self.assertEqual(store.saved[-1][0], len(calls) - 1)
            return f"draft-{len(calls)}"
        self._render(st, store, model)
        self.assertEqual(len(calls), 4)
        self.assertEqual([stage for stage, _ in store.saved], [0, 1, 2, 3, 4, 4])
        self.assertEqual([archived for _, archived in store.saved],
                         [True, True, False, False, False, False])
        self.assertEqual(store.current, _snapshot(self.colony))
        self.assertEqual(st.session_state["_cano_backup_expected"], store.current)

    def test_pg_checkpoint_failure_stops_next_provider_call(self):
        st = PanelUI(submit=True)
        store = SyntheticOwnerStore(_snapshot(self.colony), reject_stage=2)
        calls = []
        def model(prompt):
            calls.append(prompt)
            return "draft"
        self._render(st, store, model)
        self.assertEqual(len(calls), 2, "No third model call after failed PG checkpoint")
        self.assertEqual([stage for stage, _ in store.saved], [0, 1])
        self.assertEqual(CollaborativeMission(self.colony).interrupted()[0]["status"], "blocked")

    def test_resuming_blocked_mission_checkpoints_every_remaining_stage(self):
        class Interrupting:
            def __init__(self): self.calls = 0
            def chat(self, *args):
                self.calls += 1
                if self.calls == 2:
                    raise RuntimeError("provider interruption")
                return "first draft"
        manager = CollaborativeMission(self.colony)
        with self.assertRaises(RuntimeError):
            manager.execute("Interrupted task", client=Interrupting(), model="mock")
        mission = manager.interrupted()[0]
        st = PanelUI(clicks={"resume_mission_" + mission["id"]})
        store = SyntheticOwnerStore(_snapshot(self.colony))
        resumed_calls = []
        self._render(st, store, lambda prompt: resumed_calls.append(prompt) or "next draft")
        self.assertEqual(len(resumed_calls), 3)
        self.assertEqual([stage for stage, _ in store.saved], [1, 2, 3, 4, 4])
        self.assertEqual(store.current, _snapshot(self.colony))
        self.assertEqual(manager.get(mission["id"])["status"], "review_pending")


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
import uuid
import ast
import json
import logging
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.agent_colony import AgentColony
from core.cano_chat_tasks import (
    format_task_result, parse_task_request, stage_execution_notice,
)
from core.cano_command_center import _snapshot, prepare_cano_team
from core.collaborative_mission import CollaborativeMission
from core.colony_restore import restore_empty_colony


class CountingClient:
    def __init__(self):
        self.calls = []

    def chat(self, model, system, prompt):
        self.calls.append(prompt)
        return f"Aşama yanıtı {len(self.calls)}"


class CanoChatTasksTests(unittest.TestCase):
    def test_app_chat_function_requires_new_preview_even_for_reused_saved_id(self):
        app = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(app.read_text(encoding="utf-8"))
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "asistani_calistir")
        calls = []
        state = {}
        namespace = {
            "_CANO_OWNER_KEY": None,
            "GROQ_KEY": "synthetic-key",
            "_team_answer": lambda prompt: calls.append(prompt) or f"Model yanıtı {len(calls)}",
            "st": SimpleNamespace(session_state=state),
            "os": os,
            "uuid4": uuid.uuid4,
            "logging": logging,
            "failure_category": lambda error: type(error).__name__,
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
                os.environ, {"AGENT_COLONY_DB_PATH": str(Path(tmp) / "colony.sqlite3")}):
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(app), "exec"), namespace)
            preview = namespace["asistani_calistir"]("CANO görev: küçük bir karşılaştırma yap")
            self.assertEqual(len(calls), 0)
            self.assertIn("Henüz model çağrısı", preview)
            self.assertEqual(state["_cano_chat_task_pending"]["task"],
                             "küçük bir karşılaştırma yap")
            mission_id = state["cano_chat_request_id"]["id"]

            first = namespace["asistani_calistir"](
                "CANO görev: küçük bir karşılaştırma yap", approved=True)
            self.assertEqual(len(calls), 4)
            self.assertIn("CANO görev kaydı:", first)
            self.assertIn("review_pending", first)

            state["cano_chat_request_id"] = {
                "task": "küçük bir karşılaştırma yap", "id": mission_id,
            }
            replay = namespace["asistani_calistir"](
                "CANO görev: küçük bir karşılaştırma yap", approved=True)
            self.assertIn("onay", replay.casefold())
            self.assertEqual(len(calls), 4)

    def test_approved_call_without_matching_preview_must_not_run_or_mutate(self):
        """A boolean approval alone is not consent for a new request ID."""
        app = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(app.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "asistani_calistir")
        calls, state = [], {}
        namespace = {
            "_CANO_OWNER_KEY": None,
            "GROQ_KEY": "synthetic-key",
            "_team_answer": lambda prompt: calls.append(prompt) or "provider called",
            "st": SimpleNamespace(session_state=state),
            "os": os, "uuid4": uuid.uuid4, "logging": logging,
            "failure_category": lambda error: type(error).__name__,
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                "AGENT_COLONY_DB_PATH": str(Path(tmp) / "isolated.sqlite3")}):
            exec(compile(ast.Module(body=[function], type_ignores=[]),
                         str(app), "exec"), namespace)
            run = namespace["asistani_calistir"]
            result = run("CANO görev: test onayı yok", approved=True)
            self.assertIn("onay", result.casefold())
            self.assertEqual(calls, [])
            self.assertNotIn("cano_chat_request_id", state)
            self.assertNotIn("_cano_chat_task_pending", state)

            preview = run("CANO görev: önce onay iste")
            self.assertIn("Henüz model çağrısı", preview)
            self.assertEqual(calls, [])
            # A stale form approval for a different task must never run it.
            mismatch = run("CANO görev: yanlış görev", approved=True)
            self.assertIn("onay", mismatch.casefold())
            self.assertEqual(calls, [])
            self.assertEqual(state["cano_chat_request_id"]["task"],
                             "önce onay iste")
            self.assertEqual(state["_cano_chat_task_pending"]["task"],
                             "önce onay iste")

    def test_replaying_approval_after_completion_does_not_start_new_mission(self):
        """Double submit of the same approval cannot allocate another request."""
        app = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(app.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "asistani_calistir")
        calls, state = [], {}
        namespace = {
            "_CANO_OWNER_KEY": None, "GROQ_KEY": "synthetic-key",
            "_team_answer": lambda prompt: calls.append(prompt) or "OK",
            "st": SimpleNamespace(session_state=state),
            "os": os, "uuid4": uuid.uuid4, "logging": logging,
            "failure_category": lambda error: type(error).__name__,
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                "AGENT_COLONY_DB_PATH": str(Path(tmp) / "isolated.sqlite3")}):
            exec(compile(ast.Module(body=[function], type_ignores=[]),
                         str(app), "exec"), namespace)
            run = namespace["asistani_calistir"]
            run("CANO görev: tek yürütme")
            done = run("CANO görev: tek yürütme", approved=True)
            self.assertIn("review_pending", done)
            self.assertEqual(len(calls), 4)
            replay = run("CANO görev: tek yürütme", approved=True)
            self.assertIn("onay", replay.casefold())
            self.assertEqual(len(calls), 4)
            self.assertNotIn("cano_chat_request_id", state)
            self.assertNotIn("_cano_chat_task_pending", state)

    def test_canceling_preview_clears_authorization_and_blocks_late_submit(self):
        """Cancel removes exactly the preview token, not any unrelated task."""
        from core import cano_chat_tasks
        cancel = getattr(cano_chat_tasks, "cancel_pending_task", None)
        self.assertTrue(callable(cancel), "Missing explicit task cancellation")
        state = {
            "cano_chat_request_id": {"id": "example-1", "task": "ilk görev"},
            "_cano_chat_task_pending": {"id": "example-1", "task": "ilk görev"},
        }
        self.assertTrue(cancel(state))
        self.assertNotIn("cano_chat_request_id", state)
        self.assertNotIn("_cano_chat_task_pending", state)

        # A later duplicate submit of the canceled form cannot call the model.
        app = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(app.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "asistani_calistir")
        calls = []
        namespace = {
            "_CANO_OWNER_KEY": None, "GROQ_KEY": "synthetic-key",
            "_team_answer": lambda prompt: calls.append(prompt) or "called",
            "st": SimpleNamespace(session_state=state),
            "os": os, "uuid4": uuid.uuid4, "logging": logging,
            "failure_category": lambda error: type(error).__name__,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]),
                     str(app), "exec"), namespace)
        result = namespace["asistani_calistir"](
            "CANO görev: ilk görev", approved=True)
        self.assertIn("onay", result.casefold())
        self.assertEqual(calls, [])

        page_source = app.read_text(encoding="utf-8")
        self.assertIn('st.form_submit_button("Bekleyen görevi iptal et")', page_source)
        self.assertIn("cancel_pending_task(st.session_state)", page_source)

    def test_cancel_old_preview_cannot_clear_a_newer_request(self):
        from core import cano_chat_tasks
        cancel = getattr(cano_chat_tasks, "cancel_pending_task", None)
        self.assertTrue(callable(cancel), "Missing explicit task cancellation")
        state = {
            "cano_chat_request_id": {"id": "new-id", "task": "yeni görev"},
            "_cano_chat_task_pending": {"id": "stale-id", "task": "eski görev"},
        }
        self.assertFalse(cancel(state))
        self.assertEqual(state["cano_chat_request_id"]["id"], "new-id")
        self.assertNotIn("_cano_chat_task_pending", state)

    def test_new_chat_session_restores_owner_snapshot_and_keeps_prior_mission(self):
        app = Path(__file__).resolve().parents[1] / "app.py"
        tree = ast.parse(app.read_text(encoding="utf-8"))
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "asistani_calistir")
        calls = []

        class MemorySnapshotStore:
            remote = None

            def __init__(self, database_url):
                self.database_url = database_url

            def verify_schema(self):
                return None

            def load(self, owner):
                self.assert_owner(owner)
                return type(self).remote

            def assert_owner(self, owner):
                if owner != "synthetic-owner":
                    raise AssertionError("unexpected owner")

            def save_versioned_verified(self, owner, payload, *, expected_prior,
                                        archive_prior=True):
                self.assert_owner(owner)
                if expected_prior != type(self).remote:
                    raise RuntimeError("snapshot CAS conflict")
                type(self).remote = payload

        MemorySnapshotStore.remote = None
        def app_function(state):
            namespace = {
                "_CANO_OWNER_KEY": "synthetic-owner",
                "GROQ_KEY": "synthetic-key",
                "_team_answer": lambda prompt: calls.append(prompt) or f"Model yanıtı {len(calls)}",
                "st": SimpleNamespace(session_state=state),
                "os": os,
                "uuid4": uuid.uuid4,
                "logging": logging,
                "failure_category": lambda error: type(error).__name__,
                "cano_database_url": lambda env: "synthetic-dsn",
            }
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(app), "exec"), namespace)
            return namespace["asistani_calistir"]

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                "AGENT_COLONY_DB_PATH": str(Path(tmp) / "colony.sqlite3")}):
            with patch("core.colony_postgres.ColonySnapshotStore", MemorySnapshotStore):
                first_function = app_function({})
                preview = first_function("CANO görev: ilk kayıtlı hedef")
                self.assertIn("Henüz model çağrısı", preview)
                self.assertEqual(len(calls), 0)
                first = first_function("CANO görev: ilk kayıtlı hedef", approved=True)
                self.assertIn("review_pending", first)
                self.assertEqual(len(calls), 4)
                self.assertEqual(len(MemorySnapshotStore.remote["missions"]), 1)

                # A new Streamlit state allocates a different empty SQLite file.
                second_function = app_function({})
                preview = second_function("CANO görev: ikinci hedef")
                self.assertIn("Henüz model çağrısı", preview)
                self.assertEqual(len(calls), 4)
                second = second_function("CANO görev: ikinci hedef", approved=True)
                self.assertIn("review_pending", second)
                self.assertEqual(len(calls), 8)
                saved = MemorySnapshotStore.remote["missions"]
                self.assertEqual(len(saved), 2)
                self.assertTrue(all(mission["status"] == "review_pending"
                                    and len(json.loads(mission["stages"])) == 4
                                    for mission in saved))

    def test_only_clear_bounded_task_prefix_routes_to_team(self):
        self.assertEqual(parse_task_request("CANO görev: İki seçenek karşılaştır"),
                         "İki seçenek karşılaştır")
        self.assertEqual(parse_task_request("Görev: 2+2"), "2+2")
        self.assertIsNone(parse_task_request("Kendini geliştir CANO"))
        self.assertIn("ölçülebilir gelişim önerisi",
                      parse_task_request("Kendini geliştir öğrenmeye başla"))
        self.assertIn("önerileri otomatik uygulama",
                      parse_task_request("Kendini geliştir öğrenmeye başla"))
        self.assertIsNone(parse_task_request("CANO görev:"))
        self.assertIsNone(parse_task_request("CANO görev: " + "x" * 1201))

    def test_legacy_mission_stage_warns_about_unrecorded_tools(self):
        notice = stage_execution_notice({"output": "Python ile denedim; sonuç 4."})
        self.assertIn("gerçek araç çalıştırma kaydı yok", notice)
        self.assertIn("doğrulanmış deney sonucu değildir", notice)
        self.assertIsNone(stage_execution_notice({
            "output": "Yalnızca model metni.", "execution_mode": "model_text_only",
        }))

    def test_chat_task_executes_four_stages_persists_and_replays_without_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = AgentColony(Path(tmp) / "session-a.sqlite3")
            prepare_cano_team(original, approved=True)
            manager = CollaborativeMission(original)
            founder = manager._agents()[1]
            original.feedback(
                founder, "Önceki kaynak denetimi", "Birincil kanıtı tercih et",
                "review:approved-24", accepted=True)
            client = CountingClient()
            request_id = str(uuid.uuid4())
            checkpoint_counts = []

            def checkpoint():
                mission = manager.get(request_id)
                checkpoint_counts.append(len(mission["stages"]))
                self.assertEqual(mission["status"], "running")

            result = manager.execute(
                "Birincil kaynak kanıtını gözden geçir: 2+2 sonucunu incele",
                client=client, model="fake",
                mission_id=request_id, on_checkpoint=checkpoint)
            self.assertEqual(result["status"], "review_pending")
            self.assertEqual(len(client.calls), 4)
            self.assertEqual([s["approved_lessons_used"] for s in result["stages"]],
                             [0, 1, 0, 1])
            self.assertEqual(checkpoint_counts, [1, 2, 3, 4])
            rendered = format_task_result(result)
            self.assertIn("inceleme bekleyen taslaktır", rendered)
            self.assertIn("hesap makinesi çalıştırıldığı anlamına gelmez", rendered)
            self.assertIn("Kullanılan kabul edilmiş ders: 1", rendered)

            restored = AgentColony(Path(tmp) / "session-b.sqlite3")
            restore_empty_colony(restored, _snapshot(original))
            replay = CollaborativeMission(restored).execute(
                "Birincil kaynak kanıtını gözden geçir: 2+2 sonucunu incele",
                client=client, model="fake",
                mission_id=request_id)
            self.assertEqual(replay["id"], request_id)
            self.assertEqual(replay["model_calls"], 0)
            self.assertEqual(len(client.calls), 4)
            self.assertEqual(replay["stages"], result["stages"])

    def test_request_identity_cannot_be_reused_for_different_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "colony.sqlite3")
            prepare_cano_team(colony, approved=True)
            manager, client = CollaborativeMission(colony), CountingClient()
            request_id = str(uuid.uuid4())
            manager.execute("Görev A", client=client, model="fake", mission_id=request_id)
            with self.assertRaisesRegex(ValueError, "another task"):
                manager.execute("Görev B", client=client, model="fake", mission_id=request_id)
            self.assertEqual(len(client.calls), 4)


if __name__ == "__main__":
    unittest.main()


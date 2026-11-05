import tempfile
import unittest
import uuid
import ast
import logging
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.agent_colony import AgentColony
from core.cano_chat_tasks import format_task_result, parse_task_request
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
    def test_app_chat_function_routes_task_and_reuses_saved_id_without_provider_calls(self):
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
            first = namespace["asistani_calistir"]("CANO görev: küçük bir karşılaştırma yap")
            self.assertEqual(len(calls), 4)
            self.assertIn("CANO görev kaydı:", first)
            self.assertIn("review_pending", first)
            mission_id = re.search(r"CANO görev kaydı: ([0-9a-f-]+)", first).group(1)

            state["cano_chat_request_id"] = {
                "task": "küçük bir karşılaştırma yap", "id": mission_id,
            }
            replay = namespace["asistani_calistir"]("CANO görev: küçük bir karşılaştırma yap")
            self.assertIn("yeni model çağrısı: 0", replay)
            self.assertEqual(len(calls), 4)

    def test_only_clear_bounded_task_prefix_routes_to_team(self):
        self.assertEqual(parse_task_request("CANO görev: İki seçenek karşılaştır"),
                         "İki seçenek karşılaştır")
        self.assertEqual(parse_task_request("Görev: 2+2"), "2+2")
        self.assertIsNone(parse_task_request("Kendini geliştir CANO"))
        self.assertIsNone(parse_task_request("CANO görev:"))
        self.assertIsNone(parse_task_request("CANO görev: " + "x" * 1201))

    def test_chat_task_executes_four_stages_persists_and_replays_without_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = AgentColony(Path(tmp) / "session-a.sqlite3")
            prepare_cano_team(original, approved=True)
            manager = CollaborativeMission(original)
            client = CountingClient()
            request_id = str(uuid.uuid4())
            checkpoint_counts = []

            def checkpoint():
                mission = manager.get(request_id)
                checkpoint_counts.append(len(mission["stages"]))
                self.assertEqual(mission["status"], "running")

            result = manager.execute(
                "2+2 sonucunu incele", client=client, model="fake",
                mission_id=request_id, on_checkpoint=checkpoint)
            self.assertEqual(result["status"], "review_pending")
            self.assertEqual(len(client.calls), 4)
            self.assertEqual(checkpoint_counts, [1, 2, 3, 4])
            rendered = format_task_result(result)
            self.assertIn("inceleme bekleyen taslaktır", rendered)
            self.assertIn("hesap makinesi çalıştırıldığı anlamına gelmez", rendered)

            restored = AgentColony(Path(tmp) / "session-b.sqlite3")
            restore_empty_colony(restored, _snapshot(original))
            replay = CollaborativeMission(restored).execute(
                "2+2 sonucunu incele", client=client, model="fake",
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

import tempfile
import unittest
from pathlib import Path

from core.persistent_specialist_missions import PersistentSpecialistMissions


class FakeClient:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def chat(self, model, system, prompt):
        role = system.split(".")[0].replace("Role: ", "")
        self.calls.append(role)
        if role == self.fail_at:
            self.fail_at = None
            raise RuntimeError("transient failure")
        return "draft " + role


class PersistentMissionTests(unittest.TestCase):
    def test_six_roles_persist_and_do_not_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "missions.sqlite3"
            client = FakeClient()
            runner = PersistentSpecialistMissions(path, client)
            mission = runner.create("Investigate a model", model="test-model")
            result = runner.run(mission)
            self.assertEqual(result["status"], "draft_unverified")
            self.assertFalse(result["verified"])
            self.assertEqual(len(result["steps"]), 6)
            restarted = PersistentSpecialistMissions(path, client)
            self.assertEqual(len(restarted.run(mission)["steps"]), 6)
            self.assertEqual(len(client.calls), 6)
            self.assertIn("draft_unverified", restarted.export_json(mission))

    def test_failure_resume_skips_completed_roles(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "missions.sqlite3"
            client = FakeClient(fail_at="engineer")
            runner = PersistentSpecialistMissions(path, client)
            mission = runner.create("Test recovery", model="test-model")
            with self.assertRaises(RuntimeError):
                runner.run(mission)
            self.assertEqual(runner.get(mission)["status"], "interrupted")
            self.assertEqual(len(runner.get(mission)["steps"]), 2)
            result = PersistentSpecialistMissions(path, client).run(mission)
            self.assertEqual(len(result["steps"]), 6)
            self.assertEqual(client.calls.count("planner"), 1)
            self.assertEqual(client.calls.count("discovery"), 1)
            self.assertEqual(client.calls.count("engineer"), 2)

    def test_reject_invalid_mission(self):
        with tempfile.TemporaryDirectory() as folder:
            runner = PersistentSpecialistMissions(Path(folder) / "db.sqlite3", FakeClient())
            with self.assertRaises(ValueError):
                runner.create("x", model="m", domain="physical_cells")
            with self.assertRaises(ValueError):
                runner.create("", model="m")
            with self.assertRaises(KeyError):
                runner.get("missing")


if __name__ == "__main__":
    unittest.main()

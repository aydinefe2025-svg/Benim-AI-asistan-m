"""Only a user-requested repair may replace a clipped synthesis, never prior stages."""
import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission, synthesis_needs_repair


class _ShortClient:
    def __init__(self):
        self.calls = 0

    def chat(self, model, system, prompt):
        self.calls += 1
        return "Kısa yanıt " + str(self.calls)


class _LongClient:
    def __init__(self):
        self.calls = []

    def chat(self, model, system, prompt):
        self.calls.append((model, system, prompt))
        return ("Somut bulgu: taslaklardan onaylı derslere geçiş yalnızca "
                "yetkili kabul ile yapılır. Kaynak: gerçek kod doğrulaması "
                "gerekir. Test önerisi: önce ve sonra aynı test kümesini "
                "çalıştırıp sonucu karşılaştırın. " * 8
                + "Bağımsız doğrulama yapılmadı; öneri otomatik uygulanmadı.")


class SynthesisRepairTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.colony = AgentColony(Path(folder.name) / "colony.sqlite3")
        self.colony.create_founder("research", "Do not invent evidence")
        self.colony.grow_specialists(approved=True)
        self.manager = CollaborativeMission(self.colony)
        self.initial = self.manager.execute(
            "Review CANO intent mismatch and code evidence", client=_ShortClient(),
            model="offline")
        self.mission_id = self.initial["id"]
        self.assertTrue(synthesis_needs_repair(self.manager.get(self.mission_id)))

    def test_one_call_replaces_only_truncated_synthesis_and_archives_prior_output(self):
        old = self.manager.get(self.mission_id)
        client = _LongClient()
        checkpoint_records = []

        def checkpoint():
            checkpoint_records.append(self.manager.get(self.mission_id))

        repaired = self.manager.repair_truncated_synthesis(
            self.mission_id, client=client, model="offline", on_checkpoint=checkpoint)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(checkpoint_records), 1)
        self.assertEqual(repaired["model_calls"], 1)
        self.assertEqual(repaired["status"], "review_pending")
        self.assertEqual(repaired["stages"][:3], old["stages"][:3])
        self.assertEqual(repaired["stages"][3]["previous_truncated_output"], old["stages"][3]["output"])
        self.assertEqual(repaired["stages"][3]["repair_method"], "owner_approved_single_stage")
        self.assertGreater(len(repaired["stages"][3]["output"]), 500)
        self.assertEqual(self.manager.get(self.mission_id)["stages"], repaired["stages"])
        self.assertFalse(synthesis_needs_repair(repaired))
        with self.assertRaisesRegex(RuntimeError, "not eligible"):
            self.manager.repair_truncated_synthesis(
                self.mission_id, client=client, model="offline")
        self.assertEqual(len(client.calls), 1, "Never rerun an already repaired result")

    def test_short_replacement_is_rejected_without_change(self):
        before = self.manager.get(self.mission_id)
        client = _ShortClient()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.manager.repair_truncated_synthesis(
                self.mission_id, client=client, model="offline")
        self.assertEqual(client.calls, 1)
        self.assertEqual(self.manager.get(self.mission_id), before)

    def test_provider_failure_leaves_existing_four_stage_result_untouched(self):
        before = self.manager.get(self.mission_id)
        class FailClient:
            def chat(self, model, system, prompt):
                raise RuntimeError("simulated provider quota")
        with self.assertRaises(RuntimeError):
            self.manager.repair_truncated_synthesis(
                self.mission_id, client=FailClient(), model="offline")
        self.assertEqual(self.manager.get(self.mission_id), before)

    def test_failed_pg_checkpoint_rolls_back_local_replacement(self):
        before = self.manager.get(self.mission_id)
        calls = []

        def fail_checkpoint():
            calls.append(self.manager.get(self.mission_id)["stages"][3]["output"])
            raise RuntimeError("CAS stale snapshot")

        with self.assertRaisesRegex(RuntimeError, "CAS stale snapshot"):
            self.manager.repair_truncated_synthesis(
                self.mission_id, client=_LongClient(), model="offline",
                on_checkpoint=fail_checkpoint)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.manager.get(self.mission_id), before)

    def test_mobile_view_offers_explicit_one_stage_repair_without_auto_call(self):
        source = (Path(__file__).resolve().parents[1]
                  / "core" / "cano_command_center.py").read_text(encoding="utf-8")
        self.assertIn("synthesis_needs_repair(inspected)", source)
        self.assertIn("manager.repair_truncated_synthesis(", source)
        self.assertIn("on_checkpoint=", source)


if __name__ == "__main__":
    unittest.main()

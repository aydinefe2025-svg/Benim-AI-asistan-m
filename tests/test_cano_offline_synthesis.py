"""Owner-authenticated offline synthesis correction without another billable call."""
import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission, synthesis_needs_repair


class FakeShortClient:
    def __init__(self):
        self.calls = 0

    def chat(self, model, system, prompt):
        self.calls += 1
        return "Interrupted text " + str(self.calls)


DRAFT = (
    "Gerçek kod kanıtı: CANO, inceleme bekleyen görevleri kabul edilmiş "
    "derslerden ayrı tutar. Kabul edilmiş dersler yalnızca kabul onayıyla "
    "ilişkili sonraki bağlama girer. Test edilmemiş varsayım gerçekte "
    "bulunmayan dosya yolu gibi sunulmamalıdır. "
    "Öneri: 20 gerçek ve kimliksiz görevle niyet karşılama testi oluştur; "
    "her iddiayı kod veya CI makbuzuyla eşleştir, aksi halde doğrulanmadı "
    "olarak işaretle. Son sentezin hem tam cümleyle bitmesini hem PostgreSQL "
    "geri okumasını ölç. İddialar bağımsız olarak doğrulanmış değildir."
)


class OwnerOfflineSynthesisTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.colony = AgentColony(Path(tmp.name) / "data.sqlite3")
        self.colony.create_founder("research", "Evidence first")
        self.colony.grow_specialists(approved=True)
        self.mgr = CollaborativeMission(self.colony)
        self.fake = FakeShortClient()
        self.created = self.mgr.execute(
            "Audit claims about CANO against real source files",
            client=self.fake, model="fake")
        self.mid = self.created["id"]
        self.assertTrue(synthesis_needs_repair(self.created))

    def test_only_last_stage_changes_and_previous_text_and_provenance_are_kept(self):
        before = self.mgr.get(self.mid)
        checkpointed = []
        def checkpoint():
            checkpointed.append(self.mgr.get(self.mid))
        result = self.mgr.replace_truncated_synthesis_with_owner_text(
            self.mid, DRAFT, on_checkpoint=checkpoint)
        self.assertEqual(len(checkpointed), 1)
        self.assertEqual(result["status"], "review_pending")
        self.assertEqual(result["stages"][:3], before["stages"][:3])
        last = result["stages"][3]
        self.assertEqual(last["output"], DRAFT)
        self.assertEqual(last["previous_truncated_output"],
                         before["stages"][3]["output"])
        self.assertEqual(last["execution_mode"], "owner_supplied_external_text")
        self.assertEqual(last["repair_method"], "owner_supplied_local_offline")
        self.assertEqual(self.fake.calls, 4, "No new provider calls")
        self.assertFalse(synthesis_needs_repair(result))
        self.assertEqual(result["stages"], self.mgr.get(self.mid)["stages"])
        with self.assertRaisesRegex(RuntimeError, "eligible"):
            self.mgr.replace_truncated_synthesis_with_owner_text(
                self.mid, DRAFT, on_checkpoint=lambda: None)

    def test_invalid_draft_or_missing_durable_checkpoint_never_writes(self):
        before = self.mgr.get(self.mid)
        for draft in ("Too short.", DRAFT[:-1], "", "a" * 4001 + "."):
            with self.assertRaises(ValueError):
                self.mgr.replace_truncated_synthesis_with_owner_text(
                    self.mid, draft, on_checkpoint=lambda: None)
        with self.assertRaises(ValueError):
            self.mgr.replace_truncated_synthesis_with_owner_text(
                self.mid, DRAFT, on_checkpoint=None)
        self.assertEqual(self.mgr.get(self.mid), before)

    def test_remote_checkpoint_error_rolls_back_local_change(self):
        before = self.mgr.get(self.mid)
        def fail_checkpoint():
            self.assertEqual(self.mgr.get(self.mid)["stages"][3]["output"], DRAFT)
            raise RuntimeError("CAS mismatch")
        with self.assertRaisesRegex(RuntimeError, "CAS mismatch"):
            self.mgr.replace_truncated_synthesis_with_owner_text(
                self.mid, DRAFT, on_checkpoint=fail_checkpoint)
        self.assertEqual(self.mgr.get(self.mid), before)

    def test_ui_offers_owner_only_offline_paste_with_provenance(self):
        src = (Path(__file__).resolve().parents[1] /
               "core" / "cano_command_center.py").read_text(encoding="utf-8")
        self.assertIn("manager.replace_truncated_synthesis_with_owner_text(", src)
        self.assertIn("owner_key is not None and backup_store is not None", src)
        self.assertIn("owner_supplied_local_offline", src)


if __name__ == "__main__":
    unittest.main()

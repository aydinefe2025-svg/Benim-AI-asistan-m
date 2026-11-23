"""Regression for the real 204-character CANO clipped synthesis incident.

A clipped model result must not create a false fourth-stage completion,
and retries must preserve the independently checkpointed first three stages.
"""
import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission


CLIPPED_FINAL = (
    "CANO sisteminin ölçülebilir gelişimini sağlamak amacıyla inceleme "
    "bekleyen taslaklar ile onaylı derslerin ayrıştırılması, kullanıcı niyetiyle "
    "uyumsuz yanıtların ve ürün özelliklerine dair iddiaların denet"
)


class _SequenceClient:
    def __init__(self, final):
        self.calls = 0
        self.final = final

    def chat(self, model, system, prompt):
        self.calls += 1
        if self.calls == 4:
            return self.final
        return "Onaylanmamış örnek aşama " + str(self.calls)


class FinalSynthesisQualityGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        colony = AgentColony(Path(temporary.name) / "agent.sqlite3")
        colony.create_founder("research", "No invented source evidence")
        colony.grow_specialists(approved=True)
        self.missions = CollaborativeMission(colony)

    def test_real_clipped_final_is_blocked_at_three_preserved_stages(self):
        self.assertEqual(len(CLIPPED_FINAL), 204)
        client = _SequenceClient(CLIPPED_FINAL)
        checkpoints = []

        def checkpoint():
            saved = self.missions.interrupted(limit=10)
            self.assertEqual(len(saved), 1)
            record = self.missions.get(saved[0]["id"])
            checkpoints.append((record["status"], len(record["stages"])))

        with self.assertRaisesRegex(RuntimeError, "incomplete final synthesis"):
            self.missions.execute(
                "Denetlenen CANO geliştirme sonucunu kanıtlarıyla özetle",
                client=client, model="fake", on_checkpoint=checkpoint)

        self.assertEqual(client.calls, 4)
        self.assertEqual(
            checkpoints,
            [("running", 1), ("running", 2), ("running", 3), ("blocked", 3)])
        blocked = self.missions.interrupted(limit=10)
        self.assertEqual(len(blocked), 1)
        saved = self.missions.get(blocked[0]["id"])
        self.assertEqual(saved["status"], "blocked")
        self.assertEqual([x["role"] for x in saved["stages"]],
                         ["planner", "researcher", "reviewer"])
        self.assertNotIn(CLIPPED_FINAL, str(saved["stages"]))
        self.assertEqual(self.missions.last_failure["role"], "synthesis")

        class FinalOnly:
            def __init__(self):
                self.calls = 0

            def chat(self, model, system, prompt):
                self.calls += 1
                return ("Sonuç: Kullanıcı niyetini doğru sınıflandıran ve "
                        "iddialarını mevcut kodla eşleştiren denetim önerildi. "
                        "Bağımsız doğrulama henüz yapılmadı.")

        retry = FinalOnly()
        completed = self.missions.resume(saved["id"], client=retry, model="fake",
                                         on_checkpoint=checkpoint)
        self.assertEqual(retry.calls, 1)
        self.assertEqual(completed["status"], "review_pending")
        self.assertEqual(len(completed["stages"]), 4)
        self.assertEqual(completed["stages"][:3], saved["stages"])

    def test_short_but_finished_sentence_remains_eligible(self):
        final = ("Sahip onayı olmadan ders etkinleşmez; tamamlanan görev "
                 "bağımsız doğrulama değildir. " * 3).strip()
        self.assertTrue(120 <= len(final) < 500)
        client = _SequenceClient(final)
        finished = self.missions.execute("CANO kanıt sınırlarını açıkla",
                                         client=client, model="fake")
        self.assertEqual(finished["status"], "review_pending")
        self.assertEqual(finished["stages"][3]["output"], final)

    def test_legacy_tiny_model_stubs_still_work(self):
        client = _SequenceClient("Result 4")
        finished = self.missions.execute("Kısa yanıt", client=client, model="fake")
        self.assertEqual(finished["status"], "review_pending")
        self.assertEqual(finished["model_calls"], 4)


if __name__ == "__main__":
    unittest.main()

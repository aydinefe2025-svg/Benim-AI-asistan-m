import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony


class Client:
    def __init__(self, answer="25"):
        self.answer = answer
        self.calls = 0
    def chat(self, model, system, prompt):
        self.calls += 1
        return self.answer


class BoundedCountCalculationTests(unittest.TestCase):
    def test_explicit_remaining_count_uses_exact_arithmetic(self):
        cases = (
            ("Yirmi üç kaydın sekizi eksik. Mevcut kayıt sayısını yalnız sayı olarak yaz.", "15"),
            ("Otuz iki dosyanın on dördü eksik. Mevcut dosya sayısını yalnız sayı olarak yaz.", "18"),
            ("19 belgenin 6'sı eksik. Mevcut belge sayısını yalnız sayı olarak yaz.", "13"),
            ("Dokuz örneğin üçü eksik. Mevcut örnek sayısını yalnız sayı olarak yaz.", "6"),
            ("On ölçümün onu eksik. Mevcut ölçüm sayısını yalnız sayı olarak yaz.", "0"),
            ("On iki cihazın ikisi eksik. Mevcut cihaz sayısını yalnız sayı olarak yaz.", "10"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            c = AgentColony(Path(tmp)/"db.sqlite")
            a = c.create_founder("research", "Check evidence")
            for task, expected in cases:
                with self.subTest(task=task):
                    client = Client()
                    result = c.run(a, task, client=client, model="fixture")
                    self.assertEqual(result["output"], expected)
                    self.assertEqual(client.calls, 0)
                    self.assertEqual(result["status"], "draft_unverified")
    def test_unmatched_or_inconsistent_inputs_are_not_silently_calculated(self):
        cases = (
            "Üç kaydın sekizi eksik. Mevcut kayıt sayısını yalnız sayı olarak yaz.",
            "Yirmi üç kaydın sekizi eksik değil. Mevcut kayıt sayısını yalnız sayı olarak yaz.",
            "Yirmi üç kaydın sekizi eksik. Mevcut dosya sayısını yalnız sayı olarak yaz.",
            "Yirmi üç kaydın sekizi eksik olabilir. Mevcut kayıt sayısını yalnız sayı olarak yaz.",
            "Yirmi üç kaydın sekizi eksik. Mevcut kayıt sayısını yalnız sayı olarak yaz. Bir kayıt daha ekle.",
            "Yirmi üç kaydın sekizi eksik. Eksik kayıt sayısını yalnız sayı olarak yaz.",
            "Yirmi üç kaydın sekizi eksik. Mevcut kayıt sayısını açıkla.",
            "Bu metni çevir: Yirmi üç kaydın sekizi eksik. Mevcut kayıt sayısını yalnız sayı olarak yaz.",
        )
        with tempfile.TemporaryDirectory() as tmp:
            c = AgentColony(Path(tmp)/"db.sqlite")
            a = c.create_founder("research", "Check evidence")
            for task in cases:
                with self.subTest(task=task):
                    client = Client("fallback")
                    self.assertEqual(c.run(a, task, client=client, model="fixture")["output"], "fallback")
                    self.assertEqual(client.calls, 1)
    def test_review_steps_are_not_rerouted(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = AgentColony(Path(tmp)/"db.sqlite")
            a = c.create_founder("research", "Check evidence")
            client = Client("review")
            task = "Yirmi üç kaydın sekizi eksik. Mevcut kayıt sayısını yalnız sayı olarak yaz."
            self.assertEqual(c.run(a, task, client=client, model="fixture", internal_review=True)["output"], "review")
            self.assertEqual(client.calls, 1)

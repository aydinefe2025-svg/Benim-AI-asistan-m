"""Regression: answer CANO self-development questions from actual capabilities."""
import unittest

from core.cano_capabilities import capability_reply, is_self_development_question
from core.cano_chat_tasks import parse_task_request


class CanoSelfImprovementIntentTests(unittest.TestCase):
    def test_questions_use_capability_status_not_generic_model_or_task_preview(self):
        for query in (
            "CANO sen kendi kendini geliştirebiliyor musun?",
            "Kendini geliştirebilir misin?",
            "Kendi kendine öğrenip gelişebilir misin cano?",
            "Cano, kendi kodunu değiştirebilir misin?",
        ):
            with self.subTest(query=query):
                self.assertTrue(is_self_development_question(query))
                self.assertIsNone(parse_task_request(query))
                answer = capability_reply(query, persistent_memory=True,
                                          persistent_colony=True)
                self.assertIn("Komuta Merkezi", answer)
                self.assertIn("modelin kendi ağırlıklarını otomatik eğitmesi", answer)
                self.assertIn("doğrudan GitHub kod değişikliği", answer)

    def test_explicit_work_stays_in_task_routing(self):
        self.assertIsNotNone(parse_task_request("KENDİNİ GELİŞTİRMEYİ ÖĞREN"))
        self.assertEqual("3D baskı projesini analiz et",
                         parse_task_request("CANO görev: 3D baskı projesini analiz et"))

    def test_continued_development_commands_enter_task_preview(self):
        for query in (
            "İLERLE GELİŞTİR",
            "Geliştirmeye devam et",
            "Devam et ve geliştir",
            "İyileştirmeye devam et",
        ):
            with self.subTest(query=query):
                task = parse_task_request(query)
                self.assertIsNotNone(task)
                self.assertIn("gelişim önerisi hazırla", task)
                self.assertIn("önerileri otomatik uygulama", task)

    def test_research_or_design_requests_are_not_swallowed(self):
        self.assertIsNone(capability_reply("Kendini geliştiren bir robot tasarla"))
        self.assertIsNone(capability_reply("CANO için güneş enerjisi araştır"))
        self.assertFalse(is_self_development_question(
            "Kendini geliştir ve güneş enerjisini araştır"))

    def test_existing_capability_phrases_remain_covered(self):
        for query in (
            "Kendini geliştir cano",
            "Hafızan var mı?",
            "CANO ne yapar ve nasıl gelişir?",
            "Bilgi toplayarak kendini geliştirebilir misin?",
        ):
            self.assertIn("Komuta Merkezi", capability_reply(query))


if __name__ == "__main__":
    unittest.main()

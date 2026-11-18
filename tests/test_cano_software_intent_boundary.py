"""Guard against research requests silently becoming CANO code-executor jobs.

These are user-visible routing boundaries, not just implementation details.
"""
import unittest

from core.cano_solution_dispatch import actionable_solution, infer_code_goal


class CanoSoftwareIntentBoundaryTests(unittest.TestCase):
    def test_biology_ekosistem_research_does_not_enqueue_software_job(self):
        message = "CANO biyolojik ekosistem modelini geliştir"
        self.assertIsNone(infer_code_goal(message, []))

    def test_genetic_kodon_explanation_does_not_offer_code_apply_action(self):
        explanation = "Biyolojik kodon dizisini güncelle ve hücresel modeli araştır."
        self.assertFalse(actionable_solution(explanation))

    def test_real_software_request_with_turkish_suffixes_still_routes(self):
        message = "CANO uygulamasını güncelle"
        self.assertEqual(message, infer_code_goal(message, []))
        self.assertTrue(actionable_solution(
            "CANO uygulamasındaki yazılım hatasını düzelt ve test ekle."
        ))


if __name__ == "__main__":
    unittest.main()

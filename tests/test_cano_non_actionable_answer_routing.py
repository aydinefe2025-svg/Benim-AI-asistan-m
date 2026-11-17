"""A generic model limitation must not become an executable CANO code job."""
import unittest

from core.cano_solution_dispatch import actionable_solution, infer_code_goal


class NonActionableAnswerRoutingTests(unittest.TestCase):
    def test_model_limitation_is_not_a_concrete_code_fix(self):
        answer = (
            "Harika bir motivasyon! Ben bir yapay zeka modeli olarak kendi "
            "kodlarımı bağımsız olarak değiştiremem veya yeni özellikler ekleyemem. "
            "Bunun yerine GitHub, kod geliştirme ve test sürecini başlatabiliriz."
        )
        self.assertFalse(actionable_solution(answer))
        self.assertIsNone(infer_code_goal(
            "CANO bunu uygula", [{"role": "assistant", "content": answer}],
        ))

    def test_concrete_solution_still_routes_with_owner_instruction(self):
        answer = (
            "Çözüm: CANO uygulamasında görev kuyruğu bağlantısını düzelt, "
            "ardından otomatik test ekle ve Render'da doğrula."
        )
        self.assertTrue(actionable_solution(answer))
        self.assertIn("görev kuyruğu", infer_code_goal(
            "CANO bunu uygula", [{"role": "assistant", "content": answer}],
        ))


if __name__ == "__main__":
    unittest.main()

import unittest

from core.research_status import UNVERIFIED_RESEARCH_LABEL, label_research_answer


class ResearchStatusTests(unittest.TestCase):
    def test_research_answer_is_labeled_outside_model_control(self):
        answer = label_research_answer(
            "Bu sonuç kesin olarak doğrudur.", research_requested=True
        )
        self.assertTrue(answer.startswith(UNVERIFIED_RESEARCH_LABEL))
        self.assertIn("bağımsız doğrulama yapılmadı", answer)
        self.assertIn("Bu sonuç kesin olarak doğrudur.", answer)

    def test_regular_chat_is_not_mislabeled_as_research(self):
        self.assertEqual(
            label_research_answer("Merhaba.", research_requested=False), "Merhaba."
        )

    def test_empty_or_non_text_response_is_rejected(self):
        for response in ("", "  ", None):
            with self.subTest(response=response), self.assertRaises(ValueError):
                label_research_answer(response, research_requested=True)


if __name__ == "__main__":
    unittest.main()

import unittest

from core.research_status import (
    UNVERIFIED_RESEARCH_LABEL, label_research_answer,
    label_unverified_claim_headings,
)


class ResearchStatusTests(unittest.TestCase):
    def test_research_answer_is_labeled_outside_model_control(self):
        answer = label_research_answer(
            "Bu sonuç kesin olarak doğrudur.", research_requested=True
        )
        self.assertTrue(answer.startswith(UNVERIFIED_RESEARCH_LABEL))
        self.assertIn("bağımsız doğrulama yapılmadı", answer)
        self.assertIn("Bu sonuç kesin olarak doğrudur.", answer)

    def test_unverified_claim_headings_are_downgraded_only_for_display(self):
        original = "# Doğrulanmış Gerçekler\nİddia metni"
        displayed = label_unverified_claim_headings(original)
        self.assertEqual(displayed, "# İncelenmemiş model iddiaları\nİddia metni")
        self.assertEqual(original, "# Doğrulanmış Gerçekler\nİddia metni")

    def test_english_bold_heading_is_downgraded_and_other_text_is_preserved(self):
        original = "**Verified Facts**\nA claim.\nMethod"
        self.assertEqual(
            label_unverified_claim_headings(original),
            "**İncelenmemiş model iddiaları**\nA claim.\nMethod",
        )

    def test_bold_list_heading_with_colon_inside_markers_is_downgraded(self):
        original = "- **Doğrulanmış Gerçekler:**\n  - İddia"
        self.assertEqual(
            label_unverified_claim_headings(original),
            "- **İncelenmemiş model iddiaları:**\n  - İddia",
        )

    def test_non_heading_text_is_unchanged(self):
        text = "These are verified facts in a sentence."
        self.assertEqual(label_unverified_claim_headings(text), text)

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

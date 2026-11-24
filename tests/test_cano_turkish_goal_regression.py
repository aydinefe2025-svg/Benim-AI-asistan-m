import unittest
from core.cano_source_context import extract_cano_task, is_cano_code_task

class TurkishGoalRegression(unittest.TestCase):
    def test_real_team_prompt_extracts_turkish_goal_without_draft_or_rules(self):
        goal = "CANO için ölçülebilir gelişim önerisi hazırla; mevcut kod ve testleri denetle"
        prompt = "Hedef: " + goal + "\nDraft:\nmodel text\n\nYanıt kalitesi: rules\nExecution boundary: text only"
        self.assertEqual(extract_cano_task(prompt), goal)
        self.assertTrue(is_cano_code_task(extract_cano_task(prompt)))

    def test_repair_prompt_excludes_untrusted_previous_draft(self):
        goal = "Canoyu geliştirin ve öğrenmesini sağlayın"
        prompt = "Hedef: " + goal + "\nTaslak (doğrulanmamış):\nold text\nEleştiri (doğrulanmamış):\nold critique"
        self.assertEqual(extract_cano_task(prompt), goal)
        self.assertTrue(is_cano_code_task(extract_cano_task(prompt)))

    def test_turkish_science_goal_does_not_get_code_context(self):
        prompt = "Hedef: nötron yıldızı kodunu incele\n\nYanıt kalitesi: rules"
        self.assertFalse(is_cano_code_task(extract_cano_task(prompt)))

    def test_wrapped_planner_does_not_include_quality_rules_or_memory(self):
        goal = "CANO kodunu incele"
        prompt = "Task: Plan. Hedef: " + goal + "\n\nYanıt kalitesi: rules\nExecution boundary: text only\nAccepted past lessons (not verified facts):\n[]"
        self.assertEqual(extract_cano_task(prompt), goal)

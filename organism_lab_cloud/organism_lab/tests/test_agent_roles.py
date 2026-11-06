import unittest
from organism_lab.agent_roles import AGENT_PROFILES, profile_prompt


class AgentRoleTests(unittest.TestCase):
    def test_profiles_are_bounded_and_explicitly_non_autonomous(self):
        self.assertGreaterEqual(len(AGENT_PROFILES), 7)
        for agent_id in AGENT_PROFILES:
            prompt = profile_prompt(agent_id)
            self.assertIn("Kendi kendine dış sistemleri değiştirme", prompt)
            self.assertIn("eğitim verisi", prompt)

    def test_every_profile_has_simulator_grounding_and_no_fabricated_results(self):
        for agent_id in AGENT_PROFILES:
            prompt = profile_prompt(agent_id)
            self.assertIn("dijital simülatördür", prompt)
            self.assertIn("gerçek hücre", prompt)
            self.assertIn("Rapor yoksa sonuç uydurma", prompt)
            self.assertIn("TASK_B", prompt)
            self.assertIn("Türkçe ve sade anlat", prompt)

    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError):
            profile_prompt("admin")

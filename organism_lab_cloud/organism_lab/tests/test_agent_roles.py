import unittest
from organism_lab.agent_roles import AGENT_PROFILES, profile_prompt

class AgentRoleTests(unittest.TestCase):
    def test_profiles_are_bounded_and_explicitly_non_autonomous(self):
        self.assertGreaterEqual(len(AGENT_PROFILES), 7)
        for agent_id in AGENT_PROFILES:
            prompt = profile_prompt(agent_id)
            self.assertIn("Kendi kendine dış sistemleri değiştirme", prompt)
            self.assertIn("model ağırlıkları", prompt)

    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError):
            profile_prompt("admin")

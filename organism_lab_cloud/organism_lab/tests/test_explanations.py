import unittest

from organism_lab.explanations import (
    explain_adaptation_study,
    explain_reproduction_study,
    explain_shared_world,
)
from organism_lab.shared_world import run_shared_world
from organism_lab.reproduction_study import run_study
from organism_lab.adaptation_study import run_adaptation_study


class ExplanationTests(unittest.TestCase):
    def test_shared_world_explanation_matches_computed_metrics_and_states_limits(self):
        result = run_shared_world(steps=4, energy=40, materials=12)
        explanation = explain_shared_world(result)
        self.assertIn(f"{result['robots']} sanal robot", explanation["finding"])
        self.assertIn(f"{result['successful_routes']} rota", explanation["finding"])
        self.assertIn("Gerçek robot", explanation["limits"])

    def test_zero_step_shared_world_is_explained_without_claiming_activity(self):
        explanation = explain_shared_world(run_shared_world(steps=0))
        self.assertIn("hiçbir işlem yapılmadı", explanation["finding"])

    def test_reproduction_explanation_uses_computed_difference_and_interval(self):
        report = run_study(seeds=(1, 2, 3), steps=10, resource_levels=(0, 8))
        explanation = explain_reproduction_study(report)
        self.assertIn("aynı rastgele tohumlarla", explanation["what_was_tested"])
        self.assertIn("Adım başına 0 kaynak", explanation["finding"])
        self.assertIn("sıfırı kapsıyor", explanation["finding"])
        self.assertIn("biyolojik deney", explanation["limits"])

    def test_adaptation_explanation_compares_final_task_share(self):
        report = run_adaptation_study(seeds=(1, 2, 3), steps=30, shift_tick=10, capacity=16)
        explanation = explain_adaptation_study(report)
        self.assertIn("10. adımda", explanation["what_was_tested"])
        self.assertIn("TASK_B", explanation["finding"])
        self.assertIn("yüzde puan", explanation["finding"])
        self.assertIn("model ağırlıklarını öğrendiğini", explanation["limits"])


if __name__ == "__main__":
    unittest.main()


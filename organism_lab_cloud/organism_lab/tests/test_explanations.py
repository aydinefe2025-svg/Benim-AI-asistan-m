import unittest

from organism_lab.explanations import (
    explain_adaptation_study,
    explain_discovery_sweep,
    explain_reproduction_study,
    explain_shared_world,
)
from organism_lab.shared_world import run_shared_world
from organism_lab.reproduction_study import run_study
from organism_lab.adaptation_study import run_adaptation_study


class ExplanationTests(unittest.TestCase):
    def test_discovery_explanation_leads_with_plain_language_result(self):
        explanation = explain_discovery_sweep({
            "status": "replicated_simulation_candidate",
            "selected_candidate": {"mutation_rate": 0.2},
            "confirmation": {"mean_difference": 0.8634, "approx_ci95_low": 0.8474,
                             "approx_ci95_high": 0.8794},
            "design": {"screening_seeds": list(range(10)),
                       "confirmation_seeds": list(range(30))},
        })
        self.assertIn("20% mutasyon", explanation["finding"])
        self.assertIn("86.3 yüzde puan", explanation["finding"])
        self.assertIn("10 farklı başlangıç", explanation["finding"])
        self.assertIn("30 başlangıçla tekrar", explanation["finding"])
        self.assertIn("uyarı", explanation["warning_explanation"])

    def test_discovery_explanation_does_not_call_failed_confirmation_a_finding(self):
        explanation = explain_discovery_sweep({
            "status": "not_reproduced_on_confirmation_seeds",
            "selected_candidate": {"mutation_rate": 0.2},
            "confirmation": {"mean_difference": 0.01},
            "design": {"screening_seeds": [1], "confirmation_seeds": [2]},
        })
        self.assertIn("desteklemedi", explanation["finding"])

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
        self.assertIn("yaklaşık %95 aralık", explanation["finding"])
        self.assertIn("üremenin kapalı olduğu kontrolle", explanation["what_was_tested"])
        self.assertIn("model ağırlıklarını öğrendiğini", explanation["limits"])


if __name__ == "__main__":
    unittest.main()


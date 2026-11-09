import unittest

from organism_lab.assistant_context import summarize_lab_results


class AssistantContextTests(unittest.TestCase):
    def test_only_current_numeric_lab_summaries_are_included(self):
        context = summarize_lab_results({
            "organism_result": {
                "robots": 3,
                "organisms": 4,
                "successful_routes": 2,
                "history": [{"tick": 10, "energy_left": 0, "materials_left": 7,
                             "private_note": "must not leak"}],
                "private_note": "must not leak",
            },
            "genome_campaign_v2": {"results": [{
                "resource_per_tick": 5,
                "paired_seeds": 30,
                "paired_population_difference": {
                    "mean": 2.5, "ci95_low": 0.0, "ci95_high": 5.0,
                },
                "private_note": "must not leak",
            }]},
            "environment_shift_report": {"results": [
                {"arm": "mutation", "final_population_mean": 8,
                 "final_task_b_share_mean": .75, "adapted_seed_rate": .5,
                 "adaptation_lag_mean_ticks": 12},
                {"arm": "no_mutation", "final_population_mean": 6,
                 "final_task_b_share_mean": .25, "adapted_seed_rate": .2,
                 "adaptation_lag_mean_ticks": None},
            ]},
        })

        self.assertIn("Başarılı sanal rota: 2", context)
        self.assertIn("Son adım enerji: 0", context)
        self.assertIn("yaklaşık %95 aralık 0–5", context)
        self.assertIn("TASK_B taşıyan pay: 75%", context)
        self.assertNotIn("must not leak", context)

    def test_malformed_or_nonfinite_metrics_are_ignored(self):
        self.assertEqual(summarize_lab_results({
            "organism_result": {"robots": float("nan"), "organisms": True,
                                "successful_routes": "unknown"},
            "genome_campaign_v2": {"results": "bad"},
        }), "")

if __name__ == "__main__":
    unittest.main()


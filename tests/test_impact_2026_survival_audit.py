import importlib.util
import pathlib
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / "research" / "battery_curve_audit" / "impact_2026_survival_audit.py"
SPEC = importlib.util.spec_from_file_location("impact_2026_survival_audit", PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

class PublishedImpactSurvivalTest(unittest.TestCase):
    def setUp(self):
        self.result = AUDIT.audit()

    def test_population_is_45_not_three_groups_as_three_cells(self):
        self.assertEqual(self.result["n_impacted_total"], 45)
        self.assertEqual(len(self.result["soc_strata"]), 9)
        self.assertEqual(sum(r["n_impacted"] for r in self.result["soc_strata"]), 45)

    def test_survival_count_by_energy(self):
        expected = {3: (15, 15), 5: (9, 15), 7: (0, 15)}
        observed = {g["impact_j"]:(g["n_survived_one_week"],g["n_impacted"]) for g in self.result["group_survival"]}
        self.assertEqual(observed, expected)

    def test_five_j_counts_explain_approximate_half_discrepancy(self):
        by_soc={r["soc_percent"]:r["n_survived_one_week"] for r in self.result["soc_strata"] if r["impact_j"]==5}
        self.assertEqual(by_soc,{0:1,20:5,40:3})
        self.assertEqual(sum(by_soc.values()),9)
        self.assertIn("9 of 15",self.result["editorial_discrepancy"])

    def test_wilson_95_ranges_and_boundaries(self):
        by_j={r["impact_j"]:r for r in self.result["group_survival"]}
        self.assertAlmostEqual(by_j[3]["wilson_95_low"],.7961167,places=5)
        self.assertAlmostEqual(by_j[5]["wilson_95_low"],.3574683,places=5)
        self.assertAlmostEqual(by_j[5]["wilson_95_high"],.8017550,places=5)
        self.assertAlmostEqual(by_j[7]["wilson_95_high"],.2038833,places=5)
        for g in by_j.values():
            self.assertTrue(0<=g["wilson_95_low"]<=g["survival_fraction"]<=g["wilson_95_high"]<=1)

    def test_no_invented_longitudinal_capacity_or_raw_ids(self):
        self.assertTrue(self.result["protocol"]["one_week_survival_not_equivalent_to_post_impact_capacity"])
        for g in self.result["group_survival"]:
            self.assertIsNone(g["post_impact_200cycle_capacity_estimate"])
            self.assertFalse(g["raw_sample_ids_available_in_article"])

    def test_invalid_wilson_inputs_rejected(self):
        for k,n in [(1,0),(-1,3),(4,3),(1,2.5),(1.5,3)]:
            with self.assertRaises(ValueError):AUDIT.wilson(k,n)
        for conf in (0,1,-1,1.1):
            with self.assertRaises(ValueError):AUDIT.wilson(1,5,conf)

if __name__=="__main__":
    unittest.main()

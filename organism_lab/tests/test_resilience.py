import unittest
from organism_lab.resilience import resilience_trial

class ResilienceTests(unittest.TestCase):
    def test_no_outages_matches_baseline(self):
        r = resilience_trial(outage_ticks=())
        self.assertEqual(r["successful_routes_after_faults"], r["baseline_successful_routes"])
    def test_outage_never_improves_success(self):
        r = resilience_trial(outage_ticks=(1, 2))
        self.assertLessEqual(r["successful_routes_after_faults"], r["baseline_successful_routes"])
    def test_deterministic(self):
        self.assertEqual(resilience_trial(), resilience_trial())
    def test_invalid_outage(self):
        with self.assertRaises(ValueError):
            resilience_trial(outage_ticks=(0,))
    def test_history_length(self):
        self.assertEqual(len(resilience_trial(steps=7)["history"]), 7)
    def test_recovery_bounded(self):
        r = resilience_trial(steps=15, energy=200, materials=20, outage_ticks=(1,))
        self.assertLessEqual(r["recoveries_observed"], r["failures_injected"])

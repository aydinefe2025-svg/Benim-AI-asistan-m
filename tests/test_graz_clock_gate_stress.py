"""Full-cohort five-cell V3 simulation contract and deterministic replay."""
import unittest
from research.battery_curve_audit import graz_clock_gate_stress as st

class ClockGateStressTests(unittest.TestCase):
    def test_all_scenarios_reject_forged_evidence(self):
        d=st.run(seeds=1)
        self.assertEqual(len(d["scenarios"]),14)
        for x in d["scenarios"]:
            self.assertEqual(x["wrong_time_accepted"],0)
            if x["scenario"] in st.EXPECTED_ZERO_ACCEPT:
                self.assertEqual(x["accepted"],0)
        self.assertEqual(sum(x["synthetic_samples"] for x in d["scenarios"]),16800)
        self.assertFalse(d["physical_production_release_allowed"])
    def test_deterministic_replay(self):
        a=st.run(seed_start=24,seeds=1)
        b=st.run(seed_start=24,seeds=1)
        self.assertEqual(a,b)
    def test_forbid_unbounded_scope(self):
        for n in (0,201,True):
            with self.assertRaises(ValueError):st.run(seeds=n)

if __name__=="__main__":unittest.main()
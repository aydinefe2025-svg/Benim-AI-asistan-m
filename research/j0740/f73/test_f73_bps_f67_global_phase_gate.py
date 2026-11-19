"""F73 physical gate: adversarial unit checks and source-pinned numerical results."""
from __future__ import annotations
import copy
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import f73_bps_f67_global_phase_gate as F

class BPSPhaseGateTests(unittest.TestCase):
    def test_inward_density_requires_higher_core_energy_at_equal_mu_p(self):
        r=F.energy_jump_requirement(70.,75.,.25,940.,(75.+.25)/940.)
        self.assertFalse(r["inward_density_step_admissible_at_mu_match"])
        self.assertAlmostEqual(r["energy_deficit_e_bps_minus_e_core_MeV_fm-3"],5.)
    def test_positive_density_jump_is_admissible_if_energy_higher(self):
        r=F.energy_jump_requirement(80.,75.,.25,940.,(75.+.25)/940.)
        self.assertTrue(r["inward_density_step_admissible_at_mu_match"])
    def test_mu0_adjustment_cannot_repair_energy_ordering(self):
        for mu in (900.,930.4,952.8,1050.):
            r=F.energy_jump_requirement(70.,75.,.25,mu,(75.+.25)/mu)
            self.assertFalse(r["inward_density_step_admissible_at_mu_match"])
    def test_no_global_transition_if_upper_core_higher_mu(self):
        p=[1e-4,1e-3,.01,.1]
        d=[2.,-1.,-2.,.2]
        z=F.no_global_single_crust_to_core_transition(p,d)
        self.assertFalse(z["single_switch_to_core_compatible_with_upper_endpoint"])
        self.assertEqual(len(z["candidate_sign_change_brackets_in_scanned_range"]),2)
    def test_upper_core_lower_mu_does_not_exclude_single_switch(self):
        z=F.no_global_single_crust_to_core_transition([1e-3,.01,.1],[.7,-1.,-3.])
        self.assertTrue(z["single_switch_to_core_compatible_with_upper_endpoint"])
        self.assertEqual(z["exclusion_reason"],"UPPER_ENDPOINT_DOES_NOT_EXCLUDE_SWITCH")
    def test_nonmonotone_pressure_rejected(self):
        with self.assertRaisesRegex(ValueError,"non-monotone"):
            F.sign_brackets([.02,.01],[1,-1])
    def test_nan_sign_rejected(self):
        with self.assertRaisesRegex(ValueError,"non-monotone or nonfinite"):
            F.sign_brackets([.01,.02],[1,float('nan')])
    def test_unphysical_state_rejected(self):
        with self.assertRaisesRegex(ValueError,"non-positive"):
            F.energy_jump_requirement(0.,75.,.2,930.,.02)
    def test_real_original_jester_bps_and_f67_forced_join_not_admissible(self):
        if not (F.PHYS/'JESTER_BPS_crust_e6768650.csv').is_file():
            self.skipTest('real original source files only available in GitHub CI worktree')
        r=F.calculate(F.PHYS/'JESTER_BPS_crust_e6768650.csv',
                      F.PHYS/'F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat',
                      F.PHYS/'mpa1_jester_hybrid_crust_tov.py')
        ep=r['at_native_BPS_upper_endpoint']
        self.assertAlmostEqual(ep['e_f67_MeV_fm-3'],71.75359534449984,places=4)
        self.assertLess(ep['density_jump_core_minus_crust_fm-3'],0.0)
        self.assertLess(r['candidate_brackets_and_global_gate']['core_minus_crust_mu_at_last_native_BPS_knot_MeV'],.3)
        self.assertGreater(r['candidate_brackets_and_global_gate']['core_minus_crust_mu_at_last_native_BPS_knot_MeV'],.2)
        self.assertEqual(r['physical_original_MPA1_certification'],'NOT_ESTABLISHED')
        self.assertFalse(r['candidate_brackets_and_global_gate']['single_switch_to_core_compatible_with_upper_endpoint'])
        self.assertGreaterEqual(len(r['candidate_brackets_and_global_gate']['candidate_sign_change_brackets_in_scanned_range']),2)
    def test_source_hash_rejection_before_physical_inference(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'fake_bps.csv';p.write_text('forged')
            with self.assertRaisesRegex(ValueError,'F73_BPS_BYTES_DRIFT'):
                F.calculate(p,F.PHYS/'F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat',
                            F.PHYS/'mpa1_jester_hybrid_crust_tov.py')

if __name__=='__main__':unittest.main()

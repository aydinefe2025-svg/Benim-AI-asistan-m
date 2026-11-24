"""Adversarial tests for synthetic simulation; do not impersonate real lab tests."""
import math
import unittest
from dataclasses import replace
from research.battery_curve_audit import graz_virtual_lab as m

class TestGrazVirtualLab(unittest.TestCase):
    def make(self,cell="02",**kwargs):
        return m.generate_synthetic(cell,1234,preload_kN=m.PRELOADS_KN[cell],**kwargs)
    def test_real_reference_counts_only(self):
        x=m.REAL_SOURCE_SUMMARY
        self.assertEqual(x["time_matched_sp_rows"]+x["out_of_window_sp_rows"],x["original_sp_rows"])
        self.assertEqual(x["cell_02_original_electric_rows"]+x["cell_03_original_electric_rows"],417924)
    def test_five_real_source_counts_are_reference_not_simulated(self):
        x=m.REAL_SOURCE_SUMMARY
        self.assertEqual(x['five_source_matches_within_one_second']+x['five_source_unmatched_sp_rows'],x['five_original_sp_rows'])
        self.assertEqual(x['five_original_sp_files'],15)
        self.assertEqual(x['five_original_electrical_rows'],1091337)
    def test_distinct_synthetic_five_cell_clocks_never_alias(self):
        streams=[m.generate_synthetic(c,1,preload_kN=m.PRELOADS_KN[c]) for c in m.PRELOADS_KN]
        self.assertEqual(len(streams),5)
        clocks=[x[0][0].observed_t for x in streams]
        self.assertEqual(len(set(clocks)),5)
        combined_e=[e for e,s in streams for e in e]
        for c,(e,s) in zip(m.PRELOADS_KN,streams):
            q=m.match_synthetic(combined_e,s,clock_attested=True,phase_attested=True)
            self.assertEqual(q['wrong_time_accepted'],0)
    def test_generated_data_deterministic(self):
        self.assertEqual(self.make(),self.make())
        self.assertNotEqual(self.make()[1],m.generate_synthetic("02",1235,preload_kN=1.5)[1])
    def test_cross_cell_identity_rejected(self):
        el,sp=self.make(cell_id_valid=False)
        r=m.match_synthetic(el,sp,clock_attested=True,phase_attested=True)
        self.assertEqual(r["accepted"],0);self.assertEqual(r["rejected_cell"],len(sp))
    def test_bad_stage_rejected(self):
        el,sp=self.make(stage_id_valid=False)
        r=m.match_synthetic(el,sp,clock_attested=True,phase_attested=True)
        self.assertEqual(r["accepted"],0);self.assertEqual(r["rejected_stage"],len(sp))
    def test_missing_stage_provenance_fail_closed(self):
        el,sp=self.make()
        r=m.match_synthetic(el,sp,clock_attested=True,phase_attested=False)
        self.assertEqual(r["accepted"],0)
    def test_no_clock_attestation_fail_closed(self):
        el,sp=self.make(clock_offset_s=3)
        r=m.match_synthetic(el,sp,clock_attested=False,phase_attested=True)
        self.assertEqual(r["rejected_clock"],len(sp))
    def test_timing_misattestation_can_be_detected_only_in_sim(self):
        el,sp=self.make(clock_offset_s=3)
        r=m.match_synthetic(el,sp,clock_attested=True,phase_attested=True)
        self.assertGreater(r["wrong_time_accepted"],0)
    def test_valid_synthetic_clock_has_correct_matches(self):
        el,sp=self.make(clock_offset_s=.2)
        r=m.match_synthetic(el,sp,clock_attested=True,phase_attested=True)
        self.assertGreater(r["accepted"],200)
        self.assertEqual(r["wrong_time_accepted"],0)
    def test_missing_electrical_samples_not_imputed(self):
        el,sp=self.make(electric_drop=.60)
        r=m.match_synthetic(el,sp,clock_attested=True,phase_attested=True)
        self.assertGreater(r["rejected_time"],0)
    def test_stuck_sensor_flagged(self):
        _,sp=self.make(sensor_stuck=True)
        x=m.sensor_health(sp)
        self.assertEqual(x["sensor_stuck"],[False,False,True])
        self.assertTrue(x["not_calibrated"])
    def test_noise_is_not_misread_as_calibration(self):
        _,sp=self.make(sensor_noise_um=3)
        self.assertTrue(m.sensor_health(sp)["not_calibrated"])
    def test_model_bounds(self):
        for p in (float('nan'),-1,16):
            with self.assertRaises(ValueError):m.illustrative_displacement_um(p,25)
        with self.assertRaises(ValueError):m.simulated_capacity_fraction(1.5,100)
    def test_capacity_constant_current_known_units(self):
        self.assertAlmostEqual(m.integrate_capacity_ah([0,3600],[2,2],unit="A",phase="charge"),2)
        self.assertAlmostEqual(m.integrate_capacity_ah([0,3600],[2000,2000],unit="mA",phase="charge"),2)
        self.assertAlmostEqual(m.integrate_capacity_ah([0,3600],[-2,-2],unit="A",phase="discharge"),-2)
    def test_unsupported_units_rejected(self):
        with self.assertRaises(ValueError):m.integrate_capacity_ah([0,10],[2,2],unit="unknown",phase="charge")
    def test_bad_time_rejected(self):
        with self.assertRaises(ValueError):m.integrate_capacity_ah([0,0],[2,2],unit="A",phase="charge")
    def test_sign_convention_rejected(self):
        with self.assertRaises(ValueError):m.integrate_capacity_ah([0,10],[-2,-2],unit="A",phase="charge")
    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):m.integrate_capacity_ah([0,10],[float('nan'),2],unit="A",phase="charge")
    def test_real_capacity_comparison_blocked_without_calibration(self):
        with self.assertRaises(ValueError):m.percentage_change_same_step(1,.97,same_cell=True,same_phase=True,same_temperature=True,same_cutoffs=True,calibrated=False)
    def test_virtual_ten_percent_worsening_gate(self):
        self.assertTrue(m.virtual_worsening_reject(100,111))
        self.assertFalse(m.virtual_worsening_reject(100,110))
    def test_dropout_20_percent_false_time_stays_zero_in_bounded_seeds(self):
        for seed in range(5):
            el,sp=m.generate_synthetic("02",seed,preload_kN=1.5,electric_drop=.2)
            r=m.match_synthetic(el,sp,clock_attested=True,phase_attested=True)
            self.assertEqual(r["wrong_time_accepted"],0)
    def test_dropout_60_percent_false_time_stays_zero_in_bounded_seeds(self):
        for seed in range(5):
            el,sp=m.generate_synthetic("02",seed,preload_kN=1.5,electric_drop=.6)
            r=m.match_synthetic(el,sp,clock_attested=True,phase_attested=True)
            self.assertEqual(r["wrong_time_accepted"],0)
    def test_nonfinite_sensor_timestamp_is_rejected(self):
        el,sp=self.make()
        sp[0]=replace(sp[0],observed_t=float("nan"))
        with self.assertRaises(ValueError):m.match_synthetic(el,sp,clock_attested=True,phase_attested=True)
    def test_nonfinite_electrical_timestamp_is_rejected(self):
        el,sp=self.make()
        el[0]=replace(el[0],observed_t=float("nan"))
        with self.assertRaises(ValueError):m.match_synthetic(el,sp,clock_attested=True,phase_attested=True)
    def test_bad_identity_preload_refused(self):
        with self.assertRaises(ValueError):m.generate_synthetic("03",2026,preload_kN=1.5)
    def test_main_seeds_reproducible(self):
        self.assertEqual(m.simulate(seeds=2),m.simulate(seeds=2))
    def test_no_real_impact_or_production_claim(self):
        d=m.simulate(seeds=2)
        self.assertTrue(d["simulation_only"])
        self.assertFalse(d["real_source_raw_data_included"])
        self.assertFalse(d["release_gates"]["physical_production_release_allowed"])
        self.assertFalse(d["release_gates"]["real_fea_mesh_convergence_verified"])
        self.assertEqual(len(d["scenarios"]),10)
        self.assertEqual(len(d["virtual_parameter_grid"]),30)
        self.assertEqual(d["physical_cells_per_scenario"],5)
    def test_wrong_cell_data_not_joined_when_time_same(self):
        el,sp=self.make()
        other,_=self.make("03")
        r=m.match_synthetic(el+other,sp,clock_attested=True,phase_attested=True)
        self.assertEqual(r["wrong_time_accepted"],0)
    def test_duplicate_electrical_timestamp_rejected(self):
        el,sp=self.make()
        with self.assertRaises(ValueError):m.match_synthetic(el+[el[0]],sp,clock_attested=True,phase_attested=True)

if __name__=="__main__": unittest.main()
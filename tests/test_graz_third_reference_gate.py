"""Red-team tests: independent third reference witness closes two-root common mode."""
import dataclasses
import unittest
from research.battery_curve_audit import graz_virtual_lab as v
from research.battery_curve_audit import graz_clock_anchor_gate as two
from research.battery_curve_audit import graz_third_reference_gate as third

class ThirdReferenceGateTests(unittest.TestCase):
    def setUp(self):
        self.cell='03'; self.session='SYNTH-SESSION-03'; self.seed=1729
        self.e,self.s=v.generate_synthetic(self.cell,self.seed,preload_kN=3.,clock_offset_s=.2)
        self.start=self.s[0].truth_t
        self.anchors,self.roots=two.mock_independent_witnesses(seed=self.seed,session_id=self.session,
            cell_id=self.cell,truth_first_t=self.start,clock_offset_s=.2)
        self.pulses,self.key=third.mock_independent_pulses(seed=self.seed,session_id=self.session,
            cell_id=self.cell,truth_first_t=self.start,clock_offset_s=.2,electric=self.e,sensors=self.s)

    def execute(self,pulses=None,key=None,anchors=None,roots=None,e=None,s=None,phase=True):
        return third.verify_and_join_three_reference(
            self.e if e is None else e,self.s if s is None else s,
            anchors=self.anchors if anchors is None else anchors,
            trust_roots=self.roots if roots is None else roots,
            pulses=self.pulses if pulses is None else pulses,
            trigger_key=self.key if key is None else key,
            session_id=self.session,expected_cell=self.cell,
            reference_bounds=(self.start,self.start+1200.),
            phase_source_authentic=phase)

    def test_positive_third_external_channel(self):
        r=self.execute();self.assertTrue(r['gate_passed']);self.assertGreater(r['accepted'],100)
        self.assertEqual(r['wrong_time_accepted'],0)
        self.assertFalse(r['physical_production_release_allowed'])
        self.assertFalse(r['real_hardware_trigger_calibration_verified'])
    def test_both_clock_roots_compromised_detected_by_third(self):
        e,s=v.generate_synthetic(self.cell,self.seed,preload_kN=3.,clock_offset_s=3.)
        a,k=two.mock_independent_witnesses(seed=self.seed,session_id=self.session,cell_id=self.cell,
            truth_first_t=self.start,clock_offset_s=3.,correlated_fake_reference=True)
        older=two.verify_and_join(e,s,anchors=a,trust_roots=k,session_id=self.session,
            expected_cell=self.cell,true_reference_bounds=(self.start,self.start+1200.),phase_source_authentic=True)
        self.assertTrue(older['gate_passed'])
        self.assertGreater(older['wrong_time_accepted'],0)
        pulses,key=third.mock_independent_pulses(seed=self.seed,session_id=self.session,
            cell_id=self.cell,truth_first_t=self.start,clock_offset_s=3.,electric=e,sensors=s)
        new=self.execute(pulses=pulses,key=key,anchors=a,roots=k,e=e,s=s)
        self.assertEqual(new['accepted'],0)
        self.assertEqual(new['wrong_time_accepted'],0)
        self.assertFalse(new['gate_passed'])
    def test_no_independent_trigger(self):self.assertFalse(self.execute(pulses=[])['gate_passed'])
    def test_wrong_trigger_key(self):self.assertFalse(self.execute(key=b'x'*32)['gate_passed'])
    def test_shared_clock_key_for_trigger(self):self.assertFalse(self.execute(key=self.roots[two.ANCHOR_ISSUERS[0]])['gate_passed'])
    def test_wrong_session(self):
        bad=[dataclasses.replace(p,session_id='old') for p in self.pulses]
        self.assertFalse(self.execute(pulses=bad)['gate_passed'])
    def test_wrong_cell(self):
        bad=[dataclasses.replace(p,cell_id='02') for p in self.pulses]
        self.assertFalse(self.execute(pulses=bad)['gate_passed'])
    def test_mutated_signed_payload(self):
        bad=[dataclasses.replace(self.pulses[0],reference_t=self.pulses[0].reference_t+1),self.pulses[1]]
        self.assertFalse(self.execute(pulses=bad)['gate_passed'])
    def test_duplicate_pulse(self):self.assertFalse(self.execute(pulses=[self.pulses[0]]*2)['gate_passed'])
    def test_stale_replay_from_other_stream(self):
        e2,s2=v.generate_synthetic(self.cell,self.seed+1,preload_kN=3.,clock_offset_s=.2)
        self.assertFalse(self.execute(e=e2,s=s2)['gate_passed'])
    def test_nonfinite_external_pulse(self):
        bad=[dataclasses.replace(self.pulses[0],sensor_observed_t=float('nan')),self.pulses[1]]
        self.assertFalse(self.execute(pulses=bad)['gate_passed'])
    def test_high_trigger_uncertainty_even_if_resigned(self):
        bad=dataclasses.replace(self.pulses[0],uncertainty_s=.3,mac_hex='')
        bad=third.sign_pulse(bad,signing_key=self.key)
        self.assertFalse(self.execute(pulses=[bad,self.pulses[1]])['gate_passed'])
    def test_missing_phase(self):self.assertEqual(self.execute(phase=False)['accepted'],0)
    def test_wrong_stage_record(self):
        changed=[dataclasses.replace(x,source_stage=('discharge' if x.stage=='charge' else 'charge')) for x in self.s]
        r=self.execute(s=changed)
        self.assertEqual(r['accepted'],0)
    def test_truthy_string_cannot_stand_in_for_phase_attestation(self):
        r=self.execute(phase='yes')
        self.assertFalse(r['gate_passed'])
        self.assertEqual(r['accepted'],0)
    def test_malformed_reference_bounds_fail_closed(self):
        r=third.verify_and_join_three_reference(self.e,self.s,anchors=self.anchors,
            trust_roots=self.roots,pulses=self.pulses,trigger_key=self.key,
            session_id=self.session,expected_cell=self.cell,
            reference_bounds=None,phase_source_authentic=True)
        self.assertEqual(r['accepted'],0)
        self.assertFalse(r['gate_passed'])
    def test_different_physical_cell(self):
        for cell,preload in v.PRELOADS_KN.items():
            with self.subTest(cell=cell):
                e,s=v.generate_synthetic(cell,self.seed+int(cell),preload_kN=preload,clock_offset_s=.2)
                sid='GRAZ-V4-'+cell
                a,k=two.mock_independent_witnesses(seed=100+int(cell),session_id=sid,
                    cell_id=cell,truth_first_t=s[0].truth_t,clock_offset_s=.2)
                ps,pk=third.mock_independent_pulses(seed=100+int(cell),session_id=sid,
                    cell_id=cell,truth_first_t=s[0].truth_t,clock_offset_s=.2,electric=e,sensors=s)
                r=third.verify_and_join_three_reference(e,s,anchors=a,trust_roots=k,pulses=ps,trigger_key=pk,
                    session_id=sid,expected_cell=cell,reference_bounds=(s[0].truth_t,s[0].truth_t+1200.),
                    phase_source_authentic=True)
                self.assertTrue(r['gate_passed']);self.assertEqual(r['wrong_time_accepted'],0)
    def test_all_three_compromised_still_undecidable(self):
        e,s=v.generate_synthetic(self.cell,self.seed,preload_kN=3.,clock_offset_s=3.)
        a,k=two.mock_independent_witnesses(seed=self.seed,session_id=self.session,cell_id=self.cell,
            truth_first_t=self.start,clock_offset_s=3.,correlated_fake_reference=True)
        # If the physical trigger reference is also spoofed +3s, no internal proof can distinguish true time.
        ps,pk=third.mock_independent_pulses(seed=self.seed,session_id=self.session,
            cell_id=self.cell,truth_first_t=self.start,clock_offset_s=3.,electric=e,sensors=s,
            correlated_fake_reference=True)
        r=self.execute(e=e,s=s,anchors=a,roots=k,pulses=ps,key=pk)
        self.assertTrue(r['gate_passed'])
        self.assertGreater(r['wrong_time_accepted'],0)
        self.assertFalse(r['physical_production_release_allowed'])

if __name__=='__main__':unittest.main()
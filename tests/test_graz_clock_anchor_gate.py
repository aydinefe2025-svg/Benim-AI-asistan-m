"""V3 adversarial, synthetic-only, independently witnessed clock-gate tests."""
import dataclasses
import unittest
from research.battery_curve_audit import graz_virtual_lab as v
from research.battery_curve_audit import graz_clock_anchor_gate as g


class ClockGateTests(unittest.TestCase):
    def setUp(self):
        self.cell="03"
        self.seed=4203
        self.session="PHYSICAL-SESSION-03-SIM"
        self.e,self.s=v.generate_synthetic(self.cell,self.seed,preload_kN=3.,clock_offset_s=.2)
        self.start=self.s[0].truth_t
        self.bounds=(self.start,self.start+1200.)
        self.a,self.keys=g.mock_independent_witnesses(seed=self.seed,session_id=self.session,
              cell_id=self.cell,truth_first_t=self.start,clock_offset_s=.2)

    def check(self,anchors=None,roots=None,**kwargs):
        return g.verify_and_join(self.e,self.s,anchors=self.a if anchors is None else anchors,
                trust_roots=self.keys if roots is None else roots,
                session_id=self.session,expected_cell=self.cell,
                true_reference_bounds=self.bounds,phase_source_authentic=True,**kwargs)

    def test_honest_two_root_three_event_passes(self):
        d=self.check()
        self.assertTrue(d["gate_passed"])
        self.assertGreater(d["accepted"],100)
        self.assertEqual(d["wrong_time_accepted"],0)
        self.assertEqual(d["anchor_count"],6)
        self.assertEqual(d["verified_issuer_count"],2)
        self.assertFalse(d["physical_production_release_allowed"])
        self.assertFalse(d["real_phase_and_sensor_calibration_verified"])

    def test_old_false_boolean_accepts_wrong_virtual_time_but_v3_blocks(self):
        e,s=v.generate_synthetic(self.cell,self.seed,preload_kN=3.,clock_offset_s=3.)
        old=v.match_synthetic(e,s,clock_attested=True,phase_attested=True)
        self.assertGreater(old["wrong_time_accepted"],100)
        anchors,keys=g.mock_independent_witnesses(seed=self.seed,session_id=self.session,cell_id=self.cell,
                       truth_first_t=self.start,clock_offset_s=3.)
        now=g.verify_and_join(e,s,anchors=anchors,trust_roots=keys,session_id=self.session,
                     expected_cell=self.cell,true_reference_bounds=self.bounds,phase_source_authentic=True)
        self.assertFalse(now["gate_passed"])
        self.assertEqual(now["wrong_time_accepted"],0)
        self.assertEqual(now["accepted"],0)

    def test_no_anchor(self):
        d=self.check(anchors=[])
        self.assertEqual(d["accepted"],0)
        self.assertFalse(d["gate_passed"])
    def test_one_issuer(self):
        d=self.check(anchors=self.a[:3])
        self.assertFalse(d["gate_passed"])
    def test_no_trust_root(self):
        d=self.check(roots={})
        self.assertFalse(d["gate_passed"])
    def test_keys_same(self):
        d=self.check(roots={key:self.keys[g.ANCHOR_ISSUERS[0]] for key in g.ANCHOR_ISSUERS})
        self.assertFalse(d["gate_passed"])
    def test_reject_unhashable_or_invalid_trust_config(self):
        roots={key:[1,2,3] for key in g.ANCHOR_ISSUERS}
        self.assertFalse(self.check(roots=roots)["gate_passed"])
    def test_disallowed_unknown_issuer(self):
        altered=[dataclasses.replace(self.a[0],issuer="untrusted-issuer"),*self.a[1:]]
        self.assertFalse(self.check(anchors=altered)["gate_passed"])
    def test_untrusted_self_signed_key(self):
        forged=[g.sign_anchor(dataclasses.replace(x,mac_hex=""),signing_key=b"X"*32) for x in self.a]
        d=self.check(anchors=forged)
        self.assertFalse(d["gate_passed"])
    def test_mac_tamper_after_sign(self):
        changed=[dataclasses.replace(self.a[0],sensor_observed_t=self.a[0].sensor_observed_t+.3),*self.a[1:]]
        self.assertFalse(self.check(anchors=changed)["gate_passed"])
    def test_wrong_session_replay(self):
        self.assertFalse(self.check(anchors=[dataclasses.replace(x,session_id="old-session") for x in self.a])["gate_passed"])
    def test_wrong_cell_replay(self):
        self.assertFalse(self.check(anchors=[dataclasses.replace(x,cell_id="02") for x in self.a])["gate_passed"])
    def test_duplicated_signed_event(self):
        self.assertFalse(self.check(anchors=self.a[:-1]+[self.a[0]])["gate_passed"])
    def test_wrong_session_bounds(self):
        d=g.verify_independent_anchors(self.a,trust_roots=self.keys,session_id=self.session,cell_id=self.cell,
                  expected_first_reference_t=self.start+1000,expected_last_reference_t=self.start+2000)
        self.assertFalse(d.passed)
    def test_nonfinite_signed(self):
        anchor=dataclasses.replace(self.a[0],reference_t=float('nan'))
        self.assertFalse(self.check(anchors=[anchor,*self.a[1:]])["gate_passed"])
    def test_clock_drift_rejected(self):
        a,keys=g.mock_independent_witnesses(seed=self.seed,session_id=self.session,cell_id=self.cell,
                    truth_first_t=self.start,clock_offset_s=.2,drift_ppm=400)
        self.assertFalse(self.check(anchors=a,roots=keys)["gate_passed"])
    def test_phase_proof_missing(self):
        d=g.verify_and_join(self.e,self.s,anchors=self.a,trust_roots=self.keys,session_id=self.session,
             expected_cell=self.cell,true_reference_bounds=self.bounds,phase_source_authentic=False)
        self.assertEqual(d["accepted"],0)
    def test_spoofed_sensor_cell(self):
        s=[dataclasses.replace(x,source_cell="02") for x in self.s]
        d=g.verify_and_join(self.e,s,anchors=self.a,trust_roots=self.keys,session_id=self.session,
             expected_cell=self.cell,true_reference_bounds=self.bounds,phase_source_authentic=True)
        self.assertEqual(d["accepted"],0)
    def test_spoofed_sensor_stage(self):
        s=[dataclasses.replace(x,source_stage="charge" if x.stage=="discharge" else "discharge") for x in self.s]
        d=g.verify_and_join(self.e,s,anchors=self.a,trust_roots=self.keys,session_id=self.session,
             expected_cell=self.cell,true_reference_bounds=self.bounds,phase_source_authentic=True)
        self.assertEqual(d["accepted"],0)
    def test_duplicate_anchor_different_order(self):
        self.assertTrue(self.check(anchors=list(reversed(self.a)))["gate_passed"])
    def test_reject_too_loose_tolerance(self):
        with self.assertRaises(ValueError):self.check(max_jitter_s=1.0)
    def test_verify_refuses_broad_clock_limit(self):
        d=g.verify_independent_anchors(self.a,trust_roots=self.keys,session_id=self.session,cell_id=self.cell,
                  expected_first_reference_t=self.start,expected_last_reference_t=self.start+1200,
                  max_offset_s=4.)
        self.assertFalse(d.passed)
    def test_reject_short_session(self):
        d=g.verify_independent_anchors(self.a,trust_roots=self.keys,session_id=self.session,cell_id=self.cell,
                  expected_first_reference_t=self.start,expected_last_reference_t=self.start+200)
        self.assertFalse(d.passed)
    def test_honest_5_distinct_virtual_cells(self):
        for cell,pre in v.PRELOADS_KN.items():
            with self.subTest(cell=cell):
                e,s=v.generate_synthetic(cell,self.seed+int(cell),preload_kN=pre,clock_offset_s=.2)
                a,k=g.mock_independent_witnesses(seed=self.seed+int(cell),session_id="session-"+cell,cell_id=cell,
                           truth_first_t=s[0].truth_t,clock_offset_s=.2)
                d=g.verify_and_join(e,s,anchors=a,trust_roots=k,session_id="session-"+cell,
                         expected_cell=cell,true_reference_bounds=(s[0].truth_t,s[0].truth_t+1200),phase_source_authentic=True)
                self.assertTrue(d["gate_passed"])
                self.assertEqual(d["wrong_time_accepted"],0)
    def test_both_trust_roots_compromised_remains_explicit_real_world_blocker(self):
        # Deliberately construct a compromised *entire* reference clock domain.
        # All signatures verify, yet there is no genuine independent timing truth.
        # This tests a known failure mode, not a laboratory safety certification.
        e,s=v.generate_synthetic(self.cell,self.seed,preload_kN=3.,clock_offset_s=3.)
        roots_proofs,roots=g.mock_independent_witnesses(seed=self.seed,session_id=self.session,
               cell_id=self.cell,truth_first_t=s[0].truth_t,clock_offset_s=3.,
               correlated_fake_reference=True)
        d=g.verify_and_join(e,s,anchors=roots_proofs,trust_roots=roots,
                session_id=self.session,expected_cell=self.cell,
                true_reference_bounds=(s[0].truth_t,s[0].truth_t+1200),
                phase_source_authentic=True)
        self.assertTrue(d["gate_passed"])
        self.assertGreater(d["wrong_time_accepted"],0)
        self.assertFalse(d["physical_production_release_allowed"])
    def test_valid_high_offset_fails_even_if_real_root_signed(self):
        a,k=g.mock_independent_witnesses(seed=self.seed,session_id=self.session,cell_id=self.cell,
                  truth_first_t=self.start,clock_offset_s=.9)
        self.assertFalse(self.check(anchors=a,roots=k)["gate_passed"])
    def test_reject_bogus_key_or_short_key(self):
        with self.assertRaises(ValueError):g.sign_anchor(dataclasses.replace(self.a[0],mac_hex=""),signing_key=b"a")
    def test_median_offset_corrected(self):
        d=self.check()
        self.assertAlmostEqual(d["corrected_sensor_offset_s"],.2,delta=.03)
    def test_malformed_bool_limit(self):
        with self.assertRaises(ValueError):self.check(max_jitter_s=True)

if __name__=="__main__":unittest.main()
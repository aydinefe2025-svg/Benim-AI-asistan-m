#!/usr/bin/env python3
"""Adversarial tests for F79 necessary source-node enthalpy theorem."""
import json, math, os, tempfile, unittest
from pathlib import Path
import numpy as np
from f79_enthalpy_causal_feasibility import (inspect_knots,
                        summary_for_real_centres, SCHEMA, GEOM_E_TO_G_CM3)

HERE=Path(__file__).resolve().parent
SOURCE=Path(os.getenv('F79_SOURCE_DIR',str(HERE/'source')))
ARTIFACTS=Path(os.getenv('F79_ARTIFACTS_DIR',str(HERE/'artifacts')))
SOURCE_MANIFEST=Path(os.getenv('F79_SOURCE_MANIFEST',str(HERE/'input/source_manifest.json')))
ARTIFACT_MANIFEST=Path(os.getenv('F79_ARTIFACT_MANIFEST',str(HERE/'input/archived_artifact_manifest.json')))


def linear_causal(slope=2.0):
    # E(P)=0.8+slope*(P-0.1). This is a geometrized smooth cold causal EOS.
    p=np.array([0.1,0.12,0.15,0.2,0.3],dtype=float)
    e=0.8+slope*(p-0.1)
    h=np.array([(math.log((e[i]+p[i])/(e[0]+p[0]))/(slope+1))
                for i in range(len(p))])
    return p,e,h

class F79MathematicalAdversarialTests(unittest.TestCase):
    def test_01_exact_causal_linear_path_admissible(self):
        q=inspect_knots(*linear_causal(2.0));self.assertFalse(q['causal_enthalpy_violation'].any())
    def test_02_light_speed_exact_bound(self):
        q=inspect_knots(*linear_causal(1.0))
        self.assertTrue(np.allclose(q['causal_enthalpy_bound_min'],q['causal_enthalpy_bound_max'],rtol=1e-12))
        self.assertFalse(q['causal_enthalpy_violation'].any())
    def test_03_steeper_stiffness_is_causal(self):
        self.assertFalse(inspect_knots(*linear_causal(9.0))['causal_enthalpy_violation'].any())
    def test_04_superluminal_source_secant_is_rejected(self):
        p,e,h=linear_causal(0.5);v=inspect_knots(p,e,h)
        self.assertTrue(v['secant_superluminal'].all());self.assertFalse(v['causal_envelope_eligible'].any())
    def test_05_monotone_only_still_allows_subcausal_h(self):
        p,e,h=linear_causal(0.5);v=inspect_knots(p,e,h)
        self.assertFalse(v['monotone_enthalpy_violation'].any())
    def test_06_wrong_native_h_too_large(self):
        p,e,h=linear_causal(2.0);h[1:]+=0.02
        v=inspect_knots(p,e,h);self.assertTrue(v['causal_enthalpy_above'][0]);self.assertTrue(v['monotone_enthalpy_above'][0])
    def test_07_wrong_native_h_too_small(self):
        p,e,h=linear_causal(2.0);h[2]=h[1]-0.005
        # shift baseline to keep positive h increments but less than lower bound
        with self.assertRaisesRegex(ValueError,'NONINCREASING_NATIVE_H'):
            inspect_knots(p,e,h)
        h=np.cumsum(np.r_[0.,np.diff(linear_causal(2.0)[2])*0.5])
        v=inspect_knots(p,e,h);self.assertTrue(v['causal_enthalpy_below'].any())
    def test_08_bad_energy_endpoint(self):
        p,e,h=linear_causal(2.0);e[2]=e[1]-0.003
        v=inspect_knots(p,e,h);self.assertTrue(v['de_nonpositive'][1])
    def test_09_pressure_must_strictly_rise(self):
        p,e,h=linear_causal(2.0);p[2]=p[1]
        with self.assertRaisesRegex(ValueError,'NONPOSITIVE_NONMONOTONE'):inspect_knots(p,e,h)
    def test_10_nonfinite_fails_closed(self):
        p,e,h=linear_causal(2.0);h[2]=float('nan')
        with self.assertRaisesRegex(ValueError,'NONFINITE'):inspect_knots(p,e,h)
    def test_11_negative_pressure_fails_closed(self):
        p,e,h=linear_causal(2.0);p[0]=-1.0
        with self.assertRaisesRegex(ValueError,'NONPOSITIVE'):inspect_knots(p,e,h)
    def test_12_source_h_must_increase(self):
        p,e,h=linear_causal(2.0);h[2]=h[1]
        with self.assertRaisesRegex(ValueError,'NONINCREASING_NATIVE_H'):inspect_knots(p,e,h)
    def test_13_tolerance_cannot_hide_large_violation(self):
        p,e,h=linear_causal(2.0)
        with self.assertRaisesRegex(ValueError,'INVALID_FAIL_CLOSED_TOLERANCE'):
            inspect_knots(p,e,h,rtol=.1)
    def test_14_wrong_shape_rejected(self):
        p,e,h=linear_causal(2.0)
        with self.assertRaisesRegex(ValueError,'INVALID_SOURCE_KNOT_SHAPES'):
            inspect_knots(p,e[:-1],h)
    def test_15_native_sources_all_323_and_exact_subgroups(self):
        x=summary_for_real_centres(SOURCE,ARTIFACTS,SOURCE_MANIFEST,ARTIFACT_MANIFEST)
        self.assertEqual(x['schema'],SCHEMA)
        self.assertEqual(x['original_star_count'],323)
        self.assertEqual(x['original_numerical_source_rejected_stars'],294)
        self.assertEqual(x['candidate_without_endpoint_obstruction'],29)
        self.assertEqual([x['models'][k]['source_interval_violation_counts']['causal_enthalpy_violation'] for k in ('APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2')],[2,411,364,338,338,316,251])
        self.assertEqual(sum(v['F79_additional_C_star_count_not_already_F77'] for v in x['models'].values()),0)
        self.assertEqual(x['native_XPSI_photon_inference'],'NOT_RUN')
        self.assertEqual(x['physical_seven_EOS_Bayes'],'NOT_RUN')
    def test_16_manifest_belongs_to_pinned_original(self):
        x=json.loads((SOURCE_MANIFEST).read_text())
        self.assertEqual(x['pinned_commit'],'e6768650ce992abfd1153a6833857572fe5cd230')
        self.assertEqual(set(x['records']),{'APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2'})
    def test_17_source_sha_tamper_fails_closed(self):
        f=SOURCE_MANIFEST;d=json.loads(f.read_text());d['records']['MPA1']['sha256']='0'*64
        with tempfile.TemporaryDirectory() as root:
            q=Path(root)/'altered.json';q.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,'SOURCE_SHA_MISMATCH'):
                summary_for_real_centres(SOURCE,ARTIFACTS,q,ARTIFACT_MANIFEST)
    def test_18_missing_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(FileNotFoundError):
                summary_for_real_centres(HERE/'source',Path(root),SOURCE_MANIFEST,HERE/'input/archived_artifact_manifest.json')

if __name__=='__main__':unittest.main()

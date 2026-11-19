"""Adversarial mathematical bounds for source-original seven-EOS uncomputed mass."""
import copy
import json
import math
import pathlib
import unittest
import numpy as np
from scipy.integrate import quad
from scipy.interpolate import RegularGridInterpolator
from scipy.stats import truncnorm
import j0740_missing_mass_upper as z

ROOT=pathlib.Path(__file__).parent
SOURCE_ENVELOPES=ROOT/'missing_rank/J0740_source_F38_rows_max_envelopes.json'

class ExactKDEBounds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.en=json.loads(SOURCE_ENVELOPES.read_text())

    def test_original_source_mass_pins(self):
        self.assertEqual(z.F38_SHA,'4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307')
        self.assertEqual(len(z.EOS),7)
        self.assertEqual(len(self.en['six_original_F38_scores']),6)

    def test_gaussian_exact_integral_agrees_with_independent_quad(self):
        cases=[(1.73,2.09,0.,3.,1.74,2.04),(1.90,2.24,8.,.2,1.95,2.22),(2.18,2.43,2.,0.,2.19,2.42),
               (2.01,2.15,7.,3.,2.03,2.14),(2.4,2.43,10.,1.,2.41,2.429)]
        for a,b,ya,yb,lo,hi in cases:
            with self.subTest(a=a):
                expected=quad(lambda m:truncnorm.pdf(m,-5,5,loc=z.MU,scale=z.SD)* (ya+(yb-ya)*(m-a)/(b-a)),lo,hi,
                              epsabs=1e-12,epsrel=1e-12)[0]
                actual=z.integral_gaussian_times_linear(a,b,ya,yb,lo,hi)
                self.assertAlmostEqual(actual,expected,delta=max(1e-11,expected*1e-9))

    def test_row_max_convex_upper_for_every_r_within_original_KDE_grid(self):
        mass=np.linspace(1.8,2.3,8)
        radii=np.linspace(6.,16.,12)
        rng=np.random.default_rng(14)
        twoD=rng.uniform(0,25,size=(len(mass),len(radii)))
        interp=RegularGridInterpolator((mass,radii),twoD,method='linear',bounds_error=False,fill_value=0.)
        rowmax=twoD.max(axis=1)
        for i in range(60):
            m=rng.uniform(mass[0],mass[-1]);r=rng.uniform(radii[0],radii[-1])
            actual=float(interp(np.array([[m,r]]))[0]);bound=float(np.interp(m,mass,rowmax))
            self.assertLessEqual(actual,bound+1e-13)

    def test_finite_envelope_bound_not_exceeded_by_known_radius_curves(self):
        rng=np.random.default_rng(2)
        mass=np.linspace(1.74,2.43,21);env=rng.uniform(.1,2,size=21)
        lo=1.84;hi=2.17
        upper=z.max_possible_unseen(mass,env,lo,hi)
        actual=quad(lambda m:truncnorm.pdf(m,-5,5,loc=z.MU,scale=z.SD)*np.interp(m,mass,env)*((m<lo) or (m>hi)),1.74,lo,
                    points=mass[(mass>1.74)&(mass<lo)].tolist(),epsabs=1e-11)[0]
        actual+=quad(lambda m:truncnorm.pdf(m,-5,5,loc=z.MU,scale=z.SD)*np.interp(m,mass,env),hi,2.43,
                    points=mass[(mass>hi)&(mass<2.43)].tolist(),epsabs=1e-11)[0]
        self.assertAlmostEqual(upper,actual,delta=1e-9)

    def test_all_six_original_F38_witnesses_rank_top_three(self):
        report,_=z.run(envelope_data=self.en)
        self.assertEqual(report['status'],'ALL_SIX_F38_CONDITIONAL_RANK_1_2_3_ROBUST_TO_ARBITRARY_MISSING_BRANCHES')
        self.assertTrue(report['all_six_MPA1_rank1'] and report['all_six_ENG_rank2'] and report['all_six_APR4_rank3'])
        self.assertGreater(report['minimum_MPA1_score_advantage_over_any_maximal_competitor'],.49)
        for x in report['six_kde_upper_bounds'].values():
            self.assertTrue(all(v>0 for v in x['MPA1_minus_every_other_maximal_score'].values()))
            self.assertTrue(all(v>0 for v in x['ENG_minus_every_other_lower_rank_maximal_score'].values()))
            self.assertTrue(all(v>0 for v in x['APR4_minus_lower_rank_maximal_score'].values()))

    def test_zero_missing_mass_for_full_covered_models(self):
        report,_=z.run(envelope_data=self.en)
        for k,v in report['six_kde_upper_bounds'].items():
            for n in ('MPA1','MS1','MS1B'):
                self.assertEqual(v['mathematically_max_additional_missing_mass_scores'][n],0.,(k,n))

    def test_wff1_WFF2_and_apr_missing_source_scores_are_positive(self):
        report,_=z.run(envelope_data=self.en)
        for k,v in report['six_kde_upper_bounds'].items():
            for n in ('WFF1','WFF2','APR4_EPP','ENG'):
                self.assertGreater(v['mathematically_max_additional_missing_mass_scores'][n],0,(k,n))

    def test_tampered_source_envelope_fails_sha(self):
        en=copy.deepcopy(self.en)
        en['six_F38_source_rowmax_envelopes']['weighted_0.015_0.20']['max_radius_likelihood'][15]*=100
        with self.assertRaisesRegex(ValueError,'source pinned fingerprint'):
            z.run(envelope_data=en)

    def test_tampered_model_score_fails_sha(self):
        en=copy.deepcopy(self.en)
        en['six_original_F38_scores']['weighted_0.015_0.20']['MPA1']*=1.1
        with self.assertRaisesRegex(ValueError,'source pinned fingerprint'):
            z.run(envelope_data=en)

    def test_tampered_source_identity_fails_sha(self):
        en=copy.deepcopy(self.en)
        en['source_f38_sha256']='0'*64
        with self.assertRaises(ValueError):z.run(envelope_data=en)

    def test_rejects_invalid_negative_KDE_or_wrong_sorted_mass(self):
        env=np.linspace(1,2,12);mass=np.linspace(1.75,2.43,12)
        with self.assertRaises(ValueError):z.max_possible_unseen(mass,np.full(12,-1.),2.,2.1)
        with self.assertRaises(ValueError):z.max_possible_unseen(mass[::-1],env,2.,2.1)

    def test_independent_probability_bounds_contain_observed_scores(self):
        report,_=z.run(envelope_data=self.en)
        for item in report['six_kde_upper_bounds'].values():
            for n,bound in item['conditional_probability_bounds'].items():
                self.assertGreaterEqual(bound['baseline_conditional']+1e-14,bound['minimum_under_arbitrary_unseen_F38_likelihood'])
                self.assertGreaterEqual(bound['maximum_under_arbitrary_unseen_F38_likelihood']+1e-14,bound['baseline_conditional'])
                self.assertTrue(0<=bound['minimum_under_arbitrary_unseen_F38_likelihood']<=1)

if __name__=='__main__':unittest.main()

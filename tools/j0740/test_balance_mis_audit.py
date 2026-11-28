"""Synthetic, exactly normalized deterministic-mixture importance checks."""
import math
import unittest
import numpy as np
from scipy.special import logsumexp
from balance_mis_audit import EvidenceError, evaluate_pair, summarize_four_pairs


def standard(x, mean=0, scale=1):
    return (-.5 * np.sum(((x-mean)/scale)**2, axis=1)
            -x.shape[1]*(math.log(scale)+.5*math.log(2*math.pi)))


def synthetic(seed=21,n=512):
    rng=np.random.default_rng(seed)
    za=rng.normal(size=(n,13))
    zb=rng.normal(0.3,1.2,size=(n,13))
    aa=standard(za)
    ab=standard(za, .3, 1.2)
    ba=standard(zb)
    bb=standard(zb,.3,1.2)
    mixa=np.logaddexp(aa,ab)-math.log(2)
    mixb=np.logaddexp(ba,bb)-math.log(2)
    # Target is *exactly* the mixture, so all corrected weights are one.
    return dict(seed=seed,za=za,zb=zb,lwa=mixa-aa,lwb=mixb-bb,
                logqa_on_a=aa,logqb_on_a=ab,logqa_on_b=ba,logqb_on_b=bb)

class BalanceMISTests(unittest.TestCase):
    def test_analytic_normalized_target_has_exact_unit_weights(self):
        p=evaluate_pair(**synthetic())
        self.assertAlmostEqual(p['ESS'],1024,places=8)
        self.assertAlmostEqual(p['max_weight_fraction'],1/1024,places=12)
        self.assertAlmostEqual(p['logI'],0,places=12)
        self.assertAlmostEqual(p['half_to_full_logI_drift'],0,places=12)
        self.assertEqual(p['pair_status'],'PASS')

    def test_original_failure_cannot_be_hidden(self):
        p=evaluate_pair(**synthetic())
        self.assertTrue(p['original_single_proposal_status_unchanged'])
        self.assertTrue(p['all_samples_preserved'])
        self.assertEqual(p['draws'],1024)

    def test_reject_missing_seed_and_nonfinite_density(self):
        arg=synthetic()
        arg['logqb_on_a'][1]=-math.inf
        with self.assertRaises(EvidenceError): evaluate_pair(**arg)
        arg=synthetic()
        arg['lwb'][10]=math.nan
        with self.assertRaises(EvidenceError): evaluate_pair(**arg)

    def test_minus_inf_logL_preserved_without_deletion(self):
        arg=synthetic()
        arg['lwb'][10]=-math.inf
        p=evaluate_pair(**arg)
        self.assertEqual(p['draws'],1024)
        self.assertEqual(p['finite_likelihood_draws'],1023)
        self.assertLess(p['ESS'],1024)

    def test_four_pair_aggregate_predeclared_gate(self):
        p=[evaluate_pair(**synthetic(seed=k)) for k in (21,22,23,24)]
        result=summarize_four_pairs(p)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['full_MR_convergence'],'NOT_ESTABLISHED')
        self.assertEqual(result['EOS_Bayes'],'NOT_RUN')
        with self.assertRaises(EvidenceError): summarize_four_pairs(p[:3])
        with self.assertRaises(EvidenceError): summarize_four_pairs([p[0]]*4)

    def test_per_pair_fail_is_retained_even_if_aggregate_pooled_ess_would_pass(self):
        p=[evaluate_pair(**synthetic(seed=k)) for k in (21,22,23,24)]
        p[2]['individual_gates']['max_weight_fraction_max']=False
        p[2]['pair_status']='FAIL'
        r=summarize_four_pairs(p)
        self.assertEqual(r['status'],'FAIL')
        self.assertFalse(r['gates']['max_weight_fraction_max'])

if __name__=='__main__': unittest.main()
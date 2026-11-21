"""Synthetic-only red/green tests, no NICER/X-PSI imports."""
import math
import unittest
import numpy as np
from scipy.special import logsumexp
from scipy.stats import multivariate_normal
from mode_stratified_v4 import fit_partitioned_modes, ModeStratifiedV4


def prior(z):return -.5*(13*math.log(2*math.pi)+np.sum(z*z,axis=-1))

class TestModeProposal(unittest.TestCase):
    def setUp(self):
        self.z=np.random.default_rng(1531).normal(size=(4096,13))
        self.logw=-.3*self.z[:,0] + .9*np.cos(3*self.z[:,2])

    def test_normalized_density_safety_floor(self):
        m,audit=fit_partitioned_modes(self.z,self.logw)
        self.assertEqual(audit['heldout_status'],'NOT_EVALUATED')
        for samples in [self.z[:30],np.full((3,13),8.5),np.zeros((3,13))]:
            p=m.logpdf(samples)
            self.assertTrue(np.isfinite(p).all())
            self.assertTrue(np.all(p>=prior(samples)+math.log(.5)-1e-12))

    def test_moderate_broad_component_for_each_mode(self):
        model,_=fit_partitioned_modes(self.z,self.logw)
        self.assertEqual(len(model.fractions),5)
        self.assertAlmostEqual(sum(model.fractions),1.0,places=12)
        self.assertEqual(model.broad_scale,1.5)

    def test_stratification_has_two_finite_mode_components_and_no_loss(self):
        m,audit=fit_partitioned_modes(self.z,self.logw)
        self.assertEqual(audit['training_rows'],len(self.z))
        self.assertEqual(len(m.modes),2)
        self.assertTrue(np.all(np.isfinite(m.logpdf(self.z[:20]))))
        self.assertAlmostEqual(sum(m.mode_weights),1.,places=12)

    def test_draws_are_deterministic_and_density_normalizes(self):
        m,_=fit_partitioned_modes(self.z,self.logw)
        z1=m.sample(7000,np.random.default_rng(101))
        z2=m.sample(7000,np.random.default_rng(101))
        self.assertTrue(np.array_equal(z1,z2))
        w=np.exp(prior(z1)-m.logpdf(z1))
        self.assertAlmostEqual(w.mean(),1.0,delta=.04)

    def test_underdetermined_rare_mode_rejected(self):
        z=self.z.copy();z[:,2]=np.abs(z[:,2])+.01
        with self.assertRaises(ValueError):fit_partitioned_modes(z,self.logw)

    def test_invalid_rows_and_nonfinite_weights_rejected(self):
        with self.assertRaises(ValueError):fit_partitioned_modes(self.z[:400],self.logw[:400])
        lw=self.logw.copy();lw[3]=np.nan
        with self.assertRaises(ValueError):fit_partitioned_modes(self.z,lw)
        lw=self.logw.copy();lw[3]=-np.inf
        m,audit=fit_partitioned_modes(self.z,lw)
        self.assertEqual(audit['training_rows'],len(self.z))

if __name__=='__main__':unittest.main()
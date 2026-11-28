import math
import unittest
import numpy as np
from scipy.special import ndtr, logsumexp
from scipy.stats import qmc
from support_aware_mixture import BoundedGaussian, DefensiveBoundedMixture, fit_training_only

D=13
class UnitBase:
    def from_unit(self,u):
        if u.shape[1]<D: raise ValueError('missing base unit coordinates')
        from scipy.special import ndtri
        return ndtri(u[:,:D])
    def logpdf(self,z):
        return -0.5*np.sum(z*z,axis=-1)-0.5*D*math.log(2*math.pi)

class TestSupportAware(unittest.TestCase):
    def test_change_of_variables_matches_manual_jacobian(self):
        c=BoundedGaussian(np.zeros(D),np.eye(D),bound=7.0)
        z=np.full((1,D),0.5)
        y=7*np.arctanh(z/7)
        expected=-0.5*np.sum(y*y)-D/2*math.log(2*math.pi)-np.sum(np.log1p(-(z/7)**2))
        np.testing.assert_allclose(c.logpdf(z),expected,rtol=0,atol=1e-12)
    def test_bounded_samples_never_hit_normal_cdf_endpoint(self):
        c=BoundedGaussian(np.zeros(D),np.eye(D)*2,bound=7)
        u=qmc.Sobol(D,scramble=True,seed=17).random_base2(12)
        z=c.from_unit(u)
        self.assertTrue(np.all(np.abs(z)<7))
        self.assertTrue(np.all((ndtr(z)>0)&(ndtr(z)<1)))
        self.assertTrue(np.all(np.isfinite(c.logpdf(z))))
    def test_mixture_normalized_by_independent_importance_identity(self):
        base=UnitBase(); mu=np.ones(D)*.2
        core=BoundedGaussian(mu,np.eye(D)*.8,bound=7)
        broad=BoundedGaussian(mu,np.eye(D)*1.4,bound=7)
        q=DefensiveBoundedMixture(base,core,broad)
        u=qmc.Sobol(17,scramble=True,seed=1221).random_base2(15)
        z=q.from_unit(u)
        w=np.exp(base.logpdf(z)-q.logpdf(z))
        self.assertAlmostEqual(float(np.mean(w)),1.0,delta=.025)
        self.assertTrue(np.isfinite(w).all())
    def test_core_support_has_full_coverage_from_defensive_base(self):
        base=UnitBase(); c=BoundedGaussian(np.zeros(D),np.eye(D),bound=7)
        q=DefensiveBoundedMixture(base,c,c)
        z=np.full((1,D),7.2)
        self.assertTrue(np.isneginf(c.logpdf(z)[0]))
        self.assertAlmostEqual(q.logpdf(z)[0],float(np.log(.75)+base.logpdf(z)[0]),places=10)
    def test_mixture_log_density_matches_three_terms(self):
        base=UnitBase(); c=BoundedGaussian(np.zeros(D),np.eye(D),bound=7)
        b=BoundedGaussian(np.zeros(D),np.eye(D)*1.8,bound=7)
        q=DefensiveBoundedMixture(base,c,b)
        z=np.full((3,D),.2)
        expected=logsumexp(np.array([np.log(.75)+base.logpdf(z),np.log(.2)+c.logpdf(z),np.log(.05)+b.logpdf(z)]),axis=0)
        np.testing.assert_allclose(q.logpdf(z),expected,atol=1e-12)
    def test_fit_is_training_only_preserves_all_rows_and_hashes_params(self):
        base=UnitBase()
        z=qmc.Sobol(D,scramble=True,seed=20).random_base2(9)
        from scipy.special import ndtri
        z=ndtri(z)
        lw=-.4*np.sum(z*z,axis=1)
        lw[1]=-np.inf
        z0=z.copy();w0=lw.copy()
        q,m=fit_training_only(z,lw,base,model_sha256='test',broad_scale=1.6)
        q2,m2=fit_training_only(z,lw,base,model_sha256='test',broad_scale=1.7)
        self.assertEqual(m['rows'],512)
        self.assertNotEqual(m['proposal_sha256'],m2['proposal_sha256'])
        self.assertEqual(m['heldout_status'],'NOT_EVALUATED')
        self.assertTrue(np.array_equal(z,z0)); np.testing.assert_array_equal(lw,w0)
        np.testing.assert_allclose(q.logpdf(z[:10]),q.logpdf(z[:10]))
    def test_invalid_training_and_mismatched_frozen_configuration_rejected(self):
        z=np.zeros((512,D)); lw=np.full(512,-np.inf)
        with self.assertRaises(ValueError):fit_training_only(z,lw,UnitBase())
        with self.assertRaises(ValueError):BoundedGaussian(np.zeros(D),np.eye(D),bound=9)
        with self.assertRaises(ValueError):DefensiveBoundedMixture(UnitBase(),BoundedGaussian(np.zeros(D),np.eye(D)),BoundedGaussian(np.zeros(D),np.eye(D)),fractions=(.7,.2,.2))
    def test_given_same_unit_cube_draws_are_deterministic(self):
        q=DefensiveBoundedMixture(UnitBase(),BoundedGaussian(np.zeros(D),np.eye(D)),BoundedGaussian(np.zeros(D),np.eye(D)*1.6))
        u=qmc.Sobol(17,scramble=True,seed=123).random_base2(10)
        np.testing.assert_array_equal(q.from_unit(u),q.from_unit(u))

if __name__=='__main__':unittest.main()

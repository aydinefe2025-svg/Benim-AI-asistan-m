"""Independent frozen-pilot posterior proposal tests, not J0740 photon inference."""
import unittest
import numpy as np
from scipy.special import logsumexp, ndtr
from weighted_torus_fit import fit_defensive_torus
from defensive_torus_mixture import ConditionalGaussianTorus, DefensiveGaussianTorus, D, LOG2PI

PHASE=(2,9)


def truth():
    mu=np.zeros(D);mu[:3]=[.3,-.25,.2]
    reg=np.zeros((2,D));reg[0,:3]=[.13,-.11,.07];reg[1,:3]=[.2,-.17,.1]
    return ConditionalGaussianTorus(mu,np.eye(D)*.85,[.91,.05],reg,[[.017,.008],[.008,.015]])


def density13(comp,z):
    p,s=PHASE
    u=ndtr(z[:,[p,s]])
    phi=np.column_stack([u[:,1],np.mod(u[:,0]-u[:,1],1.)])
    x=np.delete(z,(p,s),axis=1)
    return comp.logpdf(x,phi)-.5*(z[:,p]**2+z[:,s]**2)-LOG2PI


def log_prior(z):
    return -.5*np.sum(z*z,axis=1)-6.5*LOG2PI


def summary(w):
    nw=np.exp(w-logsumexp(w))
    return 1/np.dot(nw,nw),float(nw.max()),float(logsumexp(w)-np.log(len(w)))


class FitTests(unittest.TestCase):
    def test_train_frozen_candidate_and_reproducible_digest(self):
        z=np.random.default_rng(43).normal(size=(700,13))
        w=np.random.default_rng(44).normal(size=700)
        w[0]=-np.inf
        copyz=z.copy();copyw=w.copy()
        q,m=fit_defensive_torus(z,w,phase_indices=PHASE)
        self.assertEqual(m['training_rows'],700)
        self.assertEqual(m['status'],'TRAINING_ONLY_FROZEN_CANDIDATE')
        self.assertEqual(m['heldout_convergence'],'NOT_EVALUATED')
        self.assertEqual(len(m['proposal_identity_sha256']),64)
        self.assertEqual(m['EOS_Bayes'],'NOT_RUN')
        np.testing.assert_array_equal(z,copyz)
        np.testing.assert_array_equal(w,copyw)
        qq,mm=fit_defensive_torus(z,w,phase_indices=PHASE)
        self.assertEqual(m,mm)
        self.assertEqual(qq.logpdf_latent_z(z[:5],phase_indices=PHASE).shape,(5,))

    def test_training_collapse_rejected_not_truncated(self):
        z=np.random.default_rng(54).normal(size=(512,13))
        w=np.full(512,-1000.)
        w[23]=0.
        with self.assertRaisesRegex(ValueError, 'training ESS'):
            fit_defensive_torus(z,w,phase_indices=PHASE)
        self.assertEqual(np.count_nonzero(w==0),1)

    def test_bad_phase_axes_and_cdf_endpoints_rejected(self):
        z=np.zeros((512,13))
        w=np.zeros(512)
        with self.assertRaises(ValueError):
            fit_defensive_torus(z,w,phase_indices=(2,2))
        z[0,2]=100
        with self.assertRaises(ArithmeticError):
            fit_defensive_torus(z,w,phase_indices=PHASE)

    def test_independent_synthetic_holdout_efficiency_lift(self):
        t=truth()
        baseline=DefensiveGaussianTorus([t],[t],[1.],[1.],base_fraction=1.,core_fraction=0,broad_fraction=0)
        z=baseline.sample_latent_z(4096,np.random.default_rng(3364),phase_indices=PHASE)
        pilot_logw=density13(t,z)-log_prior(z)
        q,m=fit_defensive_torus(z,pilot_logw,phase_indices=PHASE)
        self.assertGreater(m['training_ESS'],64)
        # Held-out independent pilot/test draws: truth is a NORMALIZED target, Z=1 exactly.
        base_z=baseline.sample_latent_z(1024,np.random.default_rng(555),phase_indices=PHASE)
        fit_z=q.sample_latent_z(1024,np.random.default_rng(555),phase_indices=PHASE)
        base=summary(density13(t,base_z)-baseline.logpdf_latent_z(base_z,phase_indices=PHASE))
        improved=summary(density13(t,fit_z)-q.logpdf_latent_z(fit_z,phase_indices=PHASE))
        self.assertGreater(improved[0],base[0]*1.25)
        self.assertLess(improved[1],base[1])
        self.assertLess(abs(improved[2]),.10)
        self.assertLess(abs(base[2]),.10)


if __name__=='__main__':
    unittest.main()

"""Synthetic proofs for the 13D original source-prior unit-coordinate bridge."""
import unittest
import numpy as np
from scipy.special import ndtr

from native_prior_bridge import (
    latent_to_source_unit, source_unit_to_latent, audit_importance_batch
)


class ToyProposal:
    def sample_latent_z(self, n, rng, *, phase_indices):
        return rng.standard_normal((n, 13))

    def logpdf_latent_z(self, z, *, phase_indices):
        return -.5*np.sum(z*z, axis=-1)-6.5*np.log(2*np.pi)


class BridgeTests(unittest.TestCase):
    def test_round_trip_source_unit_coordinates(self):
        z = np.random.default_rng(67).normal(size=(1000,13))
        u = latent_to_source_unit(z)
        self.assertEqual(u.shape,(1000,13))
        # ndtr/ndtri roundtrip incurs ~2e-13 absolute error in Gaussian tails.
        np.testing.assert_allclose(source_unit_to_latent(u),z,atol=3e-13,rtol=0)

    def test_known_normalized_phase_correlation_evidence(self):
        q=ToyProposal()
        z=q.sample_latent_z(12000,np.random.default_rng(113),phase_indices=(2,9))
        # Under independent source-unit priors, integral cos(2*pi*(up-us)) = 0.
        def logL(u): return np.log1p(.60*np.cos(2*np.pi*(u[:,2]-u[:,9])))
        result=audit_importance_batch(q,z,logL,phase_indices=(2,9))
        self.assertLess(abs(result["log_evidence"]),.018)
        self.assertGreater(result["ESS"],7000)
        self.assertEqual(result["raw_draws"],12000)
        self.assertEqual(result["status"],"SYNTHETIC_OR_USER_CALLBACK_ONLY")

    def test_callback_receives_original_source_unit_phases_not_torus(self):
        z=np.zeros((5,13));z[:,2]=np.linspace(-.8,.8,5);z[:,9]=.4
        captured=[]
        def cb(u):
            captured.append(u.copy())
            return np.zeros(len(u))
        audit_importance_batch(ToyProposal(),z,cb,phase_indices=(2,9))
        np.testing.assert_allclose(captured[0],ndtr(z),atol=0,rtol=0)

    def test_reject_endpoints_nonfinite_and_bad_callback(self):
        with self.assertRaises(ValueError): source_unit_to_latent(np.zeros(13))
        with self.assertRaises(ArithmeticError): latent_to_source_unit(np.full(13,100.))
        with self.assertRaises(ValueError):
            audit_importance_batch(ToyProposal(),np.zeros((3,13)),
                lambda u: np.array([0.,np.nan,0.]),phase_indices=(2,9))

    def test_zero_support_preserves_all_valid_draws(self):
        z=np.random.default_rng(21).normal(size=(500,13))
        def cb(u): return np.where(u[:,0]>.5,0.,-np.inf)
        out=audit_importance_batch(ToyProposal(),z,cb,phase_indices=(2,9))
        self.assertLess(out["finite_likelihood_draws"],500)
        self.assertEqual(out["raw_draws"],500)
        self.assertLess(out["ESS"],500)
        self.assertFalse(out["samples_deleted_or_weights_clipped"])


class FullDefensiveProposalTests(unittest.TestCase):
    def test_full_13d_defensive_proposal_unity_evidence(self):
        from defensive_torus_mixture import (
            ConditionalGaussianTorus, DefensiveGaussianTorus, D
        )
        center=np.zeros(D)
        regression=np.zeros((2,D))
        regression[:,0]=[.19,-.13]
        core=ConditionalGaussianTorus(center,np.eye(D)*.8,[.88,.07],
              regression,[[.04,.011],[.011,.055]])
        broad=ConditionalGaussianTorus(center,np.eye(D)*2.2,[.88,.07],
              regression,[[.12,.015],[.015,.15]])
        q=DefensiveGaussianTorus([core],[broad],[1.],[1.])
        z=q.sample_latent_z(4096,np.random.default_rng(91832),phase_indices=(2,9))
        def logL(u): return np.log1p(.6*np.cos(2*np.pi*(u[:,2]-u[:,9])))
        out=audit_importance_batch(q,z,logL,phase_indices=(2,9))
        self.assertEqual(out["raw_draws"],4096)
        self.assertEqual(out["finite_likelihood_draws"],4096)
        self.assertLess(abs(out["log_evidence"]),.06)
        self.assertFalse(out["samples_deleted_or_weights_clipped"])
        self.assertEqual(out["EOS_Bayes"],"NOT_RUN")


if __name__=="__main__":
    unittest.main()

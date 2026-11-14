"""Training-only normalized 13D latent proposal, with an exact Gaussian safety base.

This mathematical candidate has NO NICER / X-PSI likelihood access and does
not establish a physically valid EOS posterior. Crucially, sampling is direct
in R^13: there is no inverse Gaussian CDF or phase endpoint conversion.

The original X-PSI source-prior transport and likelihood MUST remain untouched.
When source-likelihood is available, compute log importance weights using
  logL(source_transform(Phi(z))) + log N_13(z;0,I) - proposal.logpdf(z).
If source_transform(Phi(z)) itself hits numeric endpoints, reject the experiment;
do not clamp u or silently discard draws. This module avoids proposal-generated
phase inverse-CDF endpoint failures; it does not certify the source transform.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

D = 13
LOG2PI = math.log(2.0 * math.pi)
FRACTIONS = (0.50, 0.40, 0.10)  # frozen mathematical design, not tuned on held-out data


def _vectors(z):
    a = np.asarray(z, dtype=np.float64)
    if a.ndim < 1 or a.shape[-1] != D or not np.all(np.isfinite(a)):
        raise ValueError("expected finite latent 13-vectors")
    return a


class DefensiveLatentV3:
    """Mixture 0.5 N(0,I) + 0.4 N(mu,Sigma) + 0.1 N(mu,1.5*Sigma).

    Every component integrates to one. Unlike very broad Gaussian or Student-t
    tails, the modest tail scale avoids frequent float-CDF endpoint events in
    typical training fits; the caller still MUST check original source u=Phi(z)
    and fail closed on any endpoint rather than silently clipping. q >= 0.5 p0.
    """
    def __init__(self, mean, covariance):
        self.mean = _vectors(np.asarray(mean, dtype=np.float64))
        if self.mean.shape != (D,):
            raise ValueError("expected one 13-vector mean")
        self.covariance = np.asarray(covariance, dtype=np.float64)
        if (self.covariance.shape != (D, D) or
                not np.all(np.isfinite(self.covariance)) or
                not np.allclose(self.covariance, self.covariance.T,
                                rtol=0, atol=1e-12)):
            raise ValueError("expected finite symmetric 13x13 covariance")
        try:
            self.chol = np.linalg.cholesky(self.covariance)
        except np.linalg.LinAlgError as exc:
            raise ValueError("covariance must be positive definite") from exc
        self.logdet = 2.0 * float(np.log(np.diag(self.chol)).sum())
        self.tail_scale = 1.5
        self.tail_chol = math.sqrt(self.tail_scale) * self.chol
        self.tail_logdet = self.logdet + D * math.log(self.tail_scale)
        self.fractions = np.array(FRACTIONS, dtype=np.float64)

    def logpdf(self, z):
        z = _vectors(z)
        residual = (z - self.mean).reshape(-1, D)
        whiten = solve_triangular(self.chol, residual.T, lower=True,
                                  check_finite=True).T
        q2 = np.sum(whiten * whiten, axis=1).reshape(z.shape[:-1])
        base = -0.5 * (D * LOG2PI + np.sum(z * z, axis=-1))
        gaussian = -0.5 * (D * LOG2PI + self.logdet + q2)
        tail_gaussian = -0.5 * (D * LOG2PI + self.tail_logdet + q2 / self.tail_scale)
        return logsumexp(np.stack([base + math.log(FRACTIONS[0]),
                                   gaussian + math.log(FRACTIONS[1]),
                                   tail_gaussian + math.log(FRACTIONS[2])], axis=0), axis=0)

    def sample(self, n, rng, *, return_component=False):
        if type(n) is not int or n < 1 or not isinstance(rng, np.random.Generator):
            raise ValueError("positive integer n and numpy Generator required")
        label = rng.choice(3, size=n, p=self.fractions)
        z = np.empty((n, D), dtype=np.float64)
        for k in range(3):
            mask = label == k
            count = int(mask.sum())
            if not count:
                continue
            normals = rng.standard_normal((count, D))
            if k == 0:
                z[mask] = normals
            elif k == 1:
                z[mask] = self.mean + normals @ self.chol.T
            else:
                z[mask] = self.mean + normals @ self.tail_chol.T
        if not np.all(np.isfinite(z)):
            raise ArithmeticError("nonfinite proposal sample")
        return (z, label) if return_component else z


def fit_training_only(z, logweights, *, ridge=0.1, covariance_floor=0.25):
    """Weighted Gaussian moment fit using TRAINING draws only, retaining -inf.

    Only an algebraically normalized *candidate* is returned. Do not use held-
    out v1/v2 to fit the candidate, change parameters or claim new PASS gates.
    """
    z = _vectors(z)
    logw = np.asarray(logweights, dtype=np.float64)
    if z.ndim != 2 or len(z) < 512:
        raise ValueError("at least 512 training-only 13D draws required")
    if (logw.shape != (len(z),) or np.any(np.isnan(logw)) or
            np.any(np.isposinf(logw)) or not np.any(np.isfinite(logw))):
        raise ValueError("logweights must be finite or -inf with one finite value")
    if not (0 < ridge < 1 and 0 < covariance_floor <= 1):
        raise ValueError("regularization parameters out of range")
    w = np.exp(logw - logsumexp(logw))
    ess = float(1.0 / np.dot(w, w))
    if ess < 64:
        raise ValueError("training ESS below 64; fitting is underidentified")
    mu = w @ z
    centered = z - mu
    cov = (centered * w[:, None]).T @ centered
    cov = (1.0 - ridge) * cov + ridge * np.eye(D)
    eig, basis = np.linalg.eigh(cov)
    cov = (basis * np.maximum(eig, covariance_floor)) @ basis.T
    cov = 0.5 * (cov + cov.T)
    model = DefensiveLatentV3(mu, cov)
    train_hash = hashlib.sha256(
        np.ascontiguousarray(z).tobytes() + np.ascontiguousarray(logw).tobytes()
    ).hexdigest()
    proposal_hash = hashlib.sha256(
        np.ascontiguousarray(mu, dtype=np.float64).tobytes()
        + np.ascontiguousarray(cov, dtype=np.float64).tobytes()
        + np.ascontiguousarray(model.fractions).tobytes()
        + np.asarray([model.tail_scale], dtype=np.float64).tobytes()
    ).hexdigest()
    audit = {
        "status": "SYNTHETICALLY_TESTED_MATHEMATICAL_CANDIDATE",
        "training_draws": len(z), "training_ess": ess,
        "training_sha256": train_hash, "proposal_sha256": proposal_hash,
        "heldout_evaluated": False, "xpsi_native_likelihood": "NOT_RUN",
        "source_prior_transport": "NOT_VERIFIED_HERE", "EOS_Bayes": "NOT_RUN",
        "qbase_fraction": FRACTIONS[0], "qgaussian_fraction": FRACTIONS[1],
        "qgaussian_tail_fraction": FRACTIONS[2],
        "gaussian_tail_covariance_scale": model.tail_scale,
    }
    return model, audit

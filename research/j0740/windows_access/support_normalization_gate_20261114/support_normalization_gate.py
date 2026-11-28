"""Fail-closed *mathematical* source-prior support-normalization gate.

Never infer which measure a real X-PSI run used from its filename, posterior,
reported support fraction, or this module. That distinction requires source
prior/runner/config and likelihood identity checks independently.

If p_0 is an unconditioned probability density and A its permitted support,
S = int_A p_0(x) dx, the conditional-prior evidence is
    Z_A = int_A p_0(x) L(x) dx / S.

If the native prior transport ALREADY samples p_0(x | A), the evidence must
NOT be divided by S a second time. Both cases are model dependent.

Here the user supplies the raw log integral and explicitly selects which
measure applies. All results are stamped MATHEMATICAL_ONLY_SOURCE_NOT_VERIFIED.
No native photon calls, π_eff, mass-radius convergence or EOS Bayes calculation.
"""
from __future__ import annotations

import math
from numbers import Integral, Real

Z95 = 1.959963984540054


def _finite_real(v, name):
    if isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v):
        raise ValueError(f'{name} must be finite real, not boolean')
    return float(v)


def wilson_support_interval(successes: int, total: int) -> tuple[float,float]:
    """95% Wilson interval for *iid source-prior Bernoulli* support trials.

    Not valid for deterministic/quasi-Monte-Carlo, correlated samples, or
    importance-weighted draws. Refuse zero successes: no finite log lower bound.
    """
    if (isinstance(successes, bool) or not isinstance(successes, Integral)
            or isinstance(total, bool) or not isinstance(total, Integral)
            or total <= 0 or not (0 < successes <= total)):
        raise ValueError('need 0 < iid successes <= iid total')
    n=float(total)
    phat=float(successes)/n
    z2=Z95*Z95
    denom=1.0+z2/n
    center=(phat+z2/(2*n))/denom
    half=(Z95/denom)*math.sqrt(phat*(1-phat)/n+z2/(4*n*n))
    lo,hi=max(0.,center-half),min(1.,center+half)
    if lo <= 0.: raise ValueError('no positive support lower bound')
    return lo,hi


def conditional_evidence(raw_log_integral: float, *, measure: str,
                         support_probability: float|None=None,
                         provenance: str|None=None,
                         support_counts: tuple[int,int]|None=None) -> dict:
    """Normalize one raw log integral with an explicitly identified measure.

    'unconditioned_support_indicator': raw numerator uses p0(x)1_A(x).
    'already_conditional': native transport already uses p0(x|A).
    In both cases this function cannot attest source identity or correctness.
    """
    raw=_finite_real(raw_log_integral,'raw_log_integral')
    if measure not in ('unconditioned_support_indicator','already_conditional'):
        raise ValueError('prior measure not verified; normalization ambiguous')
    if measure=='already_conditional':
        if support_probability is not None or support_counts is not None:
            raise ValueError('would double-normalize already conditional prior')
        result={'conditional_log_evidence':raw,'normalization_applied':False,
                'support_probability':None}
    else:
        p=_finite_real(support_probability,'support_probability')
        if not (0. < p <= 1.):
            raise ValueError('support_probability must be in (0,1]')
        if not isinstance(provenance,str) or not provenance.strip():
            raise ValueError('explicit support normalization provenance required')
        result={'conditional_log_evidence':raw-math.log(p),
                'normalization_applied':True,'support_probability':p,
                'support_probability_provenance_label':provenance}
        if support_counts is not None:
            if not isinstance(support_counts,tuple) or len(support_counts)!=2:
                raise ValueError('support_counts must be (iid_successes,iid_total)')
            k,n=support_counts
            low,high=wilson_support_interval(k,n)
            if not math.isclose(p,k/n,rel_tol=0,abs_tol=1e-14):
                raise ValueError('support_probability differs from supplied iid counts')
            result['conditional_log_evidence_bounds_95']=[raw-math.log(high),raw-math.log(low)]
            result['support_interval_type']='WILSON_95_BINOMIAL_ONLY'
            result['support_interval_does_not_include']='raw numerator MC uncertainty'
    return {'status':'MATHEMATICAL_ONLY_SOURCE_NOT_VERIFIED',
            'source_prior_lineage_verified':False,
            'raw_log_integral':raw,
            'prior_measure_assumed':measure,
            'EOS_Bayes':'NOT_RUN',
            'full_MR_convergence':'NOT_ESTABLISHED',
            **result}

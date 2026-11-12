"""Weighted conditional-torus proposal fit from preserved, *training-only* draws.

A candidate mathematical estimator, not an X-PSI or EOS result. All samples
(including -infinity log weights) remain in the training arrays; no weight
trimming or sample deletion. Regularization is on covariance, not weights.
"""
from __future__ import annotations
import hashlib
import math
import numpy as np
from scipy.special import logsumexp, ndtr
from defensive_torus_mixture import ConditionalGaussianTorus, DefensiveGaussianTorus, D


def fit_defensive_torus(z, logw, *, phase_indices, ridge=0.05,
                        x_floor=0.25, phase_floor=0.002,
                        base_fraction=0.5, core_fraction=0.25,
                        broad_fraction=0.25, broad_scale=4.0):
    """Fit a K1 conditional-torus candidate; freeze before new test likelihoods.

    Weighted circular residual regression approximates the joint posterior.
    This does *not* establish exact source-conditional-prior transport or
    posterior correctness. Use only independently validated source callbacks.
    """
    if len(phase_indices) != 2 or any(type(i) is not int for i in phase_indices):
        raise ValueError('two phase indices required')
    p,s=phase_indices
    if p==s or not (0<=p<D+2 and 0<=s<D+2):
        raise ValueError('invalid phase indices')
    z=np.asarray(z,dtype=float)
    lw=np.asarray(logw,dtype=float)
    if z.ndim!=2 or z.shape[1]!=D+2 or len(z)<512 or not np.all(np.isfinite(z)):
        raise ValueError('need >=512 preserved finite 13D training draws')
    if lw.shape!=(len(z),) or np.any(np.isnan(lw)) or np.any(np.isposinf(lw)) or not np.isfinite(lw).any():
        raise ValueError('invalid logweights; -inf is permitted')
    values=(ridge,x_floor,phase_floor,broad_scale,base_fraction,core_fraction,broad_fraction)
    if any(not np.isfinite(v) for v in values) or not (0<ridge<1 and x_floor>0 and 0<phase_floor<.25 and broad_scale>=1):
        raise ValueError('invalid regularization')
    w=np.exp(lw-logsumexp(lw))
    ess=float(1/np.dot(w,w))
    if ess < 64:
        raise ValueError(f'training ESS {ess:.3f} below prespecified 64 floor')
    u=ndtr(z[:,[p,s]])
    if np.any((u<=0)|(u>=1)):
        raise ArithmeticError('phase CDF at endpoint')
    phase=np.column_stack((u[:,1],np.mod(u[:,0]-u[:,1],1.)))
    x=np.delete(z,(p,s),axis=1)
    mu=w@x
    centered=x-mu
    cov=(centered*w[:,None]).T@centered
    cov=(1-ridge)*cov+ridge*np.eye(D)
    eig,val=np.linalg.eigh(cov)
    cov=(val*np.maximum(eig,x_floor))@val.T
    circular=np.sum(w[:,None]*np.exp(2j*np.pi*phase),axis=0)
    if np.min(np.abs(circular))<1e-5:
        raise ValueError('phase circular location unresolved, do not fit')
    loc=np.mod(np.angle(circular)/(2*np.pi),1.)
    residual=np.mod(phase-loc+0.5,1.)-.5
    B=((residual*w[:,None]).T@centered)@np.linalg.inv(cov)
    remainder=np.mod(residual-centered@B.T+0.5,1.)-.5
    correction=w@remainder
    loc=np.mod(loc+correction,1.)
    remainder=np.mod(remainder-correction+0.5,1.)-.5
    phase_cov=(remainder*w[:,None]).T@remainder
    peig,pvec=np.linalg.eigh(phase_cov)
    phase_cov=(pvec*np.maximum(peig,phase_floor))@pvec.T
    core=ConditionalGaussianTorus(mu,cov,loc,B,phase_cov)
    broad=ConditionalGaussianTorus(mu,broad_scale*cov,loc,B,broad_scale*phase_cov)
    proposal=DefensiveGaussianTorus([core],[broad],[1.],[1.],base_fraction,core_fraction,broad_fraction)
    digest=hashlib.sha256(np.ascontiguousarray(z).tobytes()+np.ascontiguousarray(lw).tobytes()).hexdigest()
    metadata={'status':'TRAINING_ONLY_FROZEN_CANDIDATE','training_rows':len(z),
              'training_ESS':ess,'training_array_sha256':digest,
              'proposal_identity_sha256':hashlib.sha256(b''.join(
                  np.ascontiguousarray(arr, dtype=np.float64).tobytes() for arr in
                  (mu,cov,loc,B,phase_cov,proposal.fractions))).hexdigest(),
              'training_phase_indices':[p,s], 'ridge':ridge,'x_floor':x_floor,
              'phase_floor':phase_floor,'broad_scale':broad_scale,
              'base_fraction':base_fraction,'core_fraction':core_fraction,
              'broad_fraction':broad_fraction,'heldout_convergence':'NOT_EVALUATED',
              'EOS_Bayes':'NOT_RUN'}
    return proposal,metadata

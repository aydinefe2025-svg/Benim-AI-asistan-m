"""Exploratory K2 13D source-normal latent proposal (SYNTHETIC ONLY).

q(z) = 0.5 N13(0,I) + sum_{sign +/-} a_sign*[0.4 N13(z;mu_sign,Sigma_sign) + 0.1 N13(z;mu_sign,1.5 Sigma_sign)]
with all terms normalized and a_sign fitted solely on training observations.
The sign split is fixed at phase-index 2 and zero; no after-the-fact phase
rotation or held-out tuning is allowed. Does not run/verify X-PSI or EOS.

The native source transport remains wholly separate and MUST be validated
before actual importance weights logL(source(Phi(z))) + log p0(z)-logq(z).
Reject any source CDF endpoint; no sample clipping or silent omission.
"""
from __future__ import annotations
import hashlib
import math
import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

DIM=13
PHASE_IDX=2
LOG2PI=math.log(2*math.pi)
DEFENSIVE=0.50
VERSION='j0740-latent-k2-exploratory-1'


def _validate_z(z):
    z=np.asarray(z,dtype=np.float64)
    if z.ndim!=2 or z.shape[1]!=DIM or not np.all(np.isfinite(z)):
        raise ValueError('need finite (n,13) latent samples')
    return z


class ModeStratifiedV4:
    """Exact five-component normalized mixture, in original latent measure."""
    def __init__(self, means, covariances, mode_weights, phase_index=PHASE_IDX):
        means=np.asarray(means,dtype=np.float64)
        covs=np.asarray(covariances,dtype=np.float64)
        weights=np.asarray(mode_weights,dtype=np.float64)
        if phase_index!=PHASE_IDX:raise ValueError('fixed z2 split only')
        if means.shape!=(2,DIM) or covs.shape!=(2,DIM,DIM) or weights.shape!=(2,):
            raise ValueError('wrong component dimensions')
        if not all(np.isfinite(x).all() for x in (means,covs,weights)):
            raise ValueError('nonfinite parameter')
        if np.any(weights<=0) or not np.isclose(weights.sum(),1.,atol=1e-12,rtol=0):
            raise ValueError('mode weights must be strictly positive and normalized')
        chols=[]
        for cov in covs:
            if not np.allclose(cov,cov.T,atol=1e-12,rtol=0):
                raise ValueError('asymmetric covariance')
            chols.append(np.linalg.cholesky(cov))
        self.means=means.copy()
        self.covariances=covs.copy()
        self.modes=tuple((self.means[i], self.covariances[i]) for i in (0,1))
        self.mode_weights=weights.copy()
        self.chols=tuple(chols)
        self.logdets=tuple(float(2*np.log(np.diag(chol)).sum()) for chol in chols)
        self.broad_scale=1.5
        self.fractions=np.array([DEFENSIVE, 0.4*weights[0],0.4*weights[1],0.1*weights[0],0.1*weights[1]])

    def logpdf(self,z):
        z=_validate_z(z)
        terms=[-.5*(DIM*LOG2PI + np.einsum('ij,ij->i',z,z))+math.log(DEFENSIVE)]
        for k in (0,1):
            delta=z-self.means[k]
            whiten=solve_triangular(self.chols[k],delta.T,lower=True).T
            q2=np.einsum('ij,ij->i',whiten,whiten)
            terms.append(-.5*(DIM*LOG2PI+self.logdets[k]+q2)+math.log(self.fractions[k+1]))
            terms.append(-.5*(DIM*LOG2PI+self.logdets[k]+DIM*math.log(self.broad_scale)+q2/self.broad_scale)+math.log(self.fractions[k+3]))
        return logsumexp(np.stack(terms,axis=0),axis=0)

    def sample(self,n,rng):
        if type(n)!=int or n<=0 or not isinstance(rng,np.random.Generator):
            raise ValueError('need n>0 and numpy RNG')
        labels=rng.choice(5,size=n,p=self.fractions)
        z=np.empty((n,DIM))
        for k in range(5):
            ids=np.flatnonzero(labels==k)
            if len(ids):
                normal=rng.standard_normal((len(ids),DIM))
                if k==0:
                    z[ids]=normal
                else:
                    j=(k-1)%2
                    broad=(k>=3)
                    z[ids]=self.means[j]+(math.sqrt(self.broad_scale) if broad else 1.0)*(normal@self.chols[j].T)
        if not np.isfinite(z).all():raise ArithmeticError('nonfinite sample')
        return z


def fit_partitioned_modes(z,logweights,*,phase_index=PHASE_IDX,ridge=0.10,eigen_floor=0.20):
    """Fit K2 using only supplied training rows, with original -inf retained.

    Per-mode ESS>=32 and global ESS>=64 required; no row clipping.
    Failure to meet either requirement means the proposal is underidentified.
    """
    z=_validate_z(z)
    lw=np.asarray(logweights,dtype=np.float64)
    if len(z)<512 or lw.shape!=(len(z),):raise ValueError('need >=512 weighted training rows')
    if np.any(np.isnan(lw)) or np.any(np.isposinf(lw)) or not np.isfinite(lw).any():
        raise ValueError('invalid weights')
    if phase_index!=PHASE_IDX or not (0<ridge<1) or not (0<eigen_floor<=1):
        raise ValueError('invalid frozen options')
    w=np.exp(lw-logsumexp(lw))
    overall_ess=float(1/np.dot(w,w))
    if overall_ess<64:raise ValueError('training global ESS below 64')
    means=[];covariances=[];mode_probs=[];mode_ess=[]
    for selector in (z[:,phase_index]<0,z[:,phase_index]>=0):
        ww=w[selector]; data=z[selector]
        if not len(data) or not np.any(ww>0):raise ValueError('missing phase mode')
        p=float(ww.sum()); mode_probs.append(p)
        weight=ww/p
        ess=float(1/np.dot(weight,weight));mode_ess.append(ess)
        if ess<32:raise ValueError('training mode ESS below 32')
        mu=weight@data;centered=data-mu
        cov=(centered*weight[:,None]).T@centered
        cov=(1-ridge)*cov+ridge*np.eye(DIM)
        ev,vec=np.linalg.eigh(cov)
        cov=(vec*np.maximum(ev,eigen_floor))@vec.T
        means.append(mu);covariances.append((cov+cov.T)*.5)
    proposal=ModeStratifiedV4(means,covariances,mode_probs,phase_index)
    training_hash=hashlib.sha256(z.tobytes()+lw.tobytes()).hexdigest()
    packet=b''.join(np.ascontiguousarray(a,dtype=np.float64).tobytes() for a in [proposal.means,proposal.covariances,proposal.fractions])
    packet+=np.asarray([ridge,eigen_floor,phase_index,proposal.broad_scale],dtype=np.float64).tobytes()
    return proposal,{'status':'EXPLORATORY_TRAINING_ONLY','version':VERSION,
      'training_rows':len(z),'training_sha256':training_hash,'training_ess':overall_ess,
      'phase_mode_training_ess':mode_ess,'phase_mode_weight_mass':mode_probs,
      'proposal_sha256':hashlib.sha256(packet).hexdigest(),'heldout_status':'NOT_EVALUATED',
      'X_PSI':'NOT_RUN','full_MR_convergence':'NOT_ESTABLISHED','EOS_Bayes':'NOT_RUN'}
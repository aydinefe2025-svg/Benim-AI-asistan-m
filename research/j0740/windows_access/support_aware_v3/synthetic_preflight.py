"""Synthetic-only J0740 proposal numerical smoke test, not native validation."""
import hashlib
import json
import math
import numpy as np
from scipy.special import logsumexp, ndtri, ndtr
from scipy.stats import qmc
from support_aware_mixture import DIM, BoundedGaussian, DefensiveBoundedMixture, fit_training_only

class StandardNormalBase:
    def from_unit(self,u):
        if u.ndim!=2 or u.shape[1]!=16 or np.any((u[:,:DIM]<=0)|(u[:,:DIM]>=1)):
            raise ValueError('synthetic base expects open 16D unit coordinates')
        return ndtri(u[:,:DIM])
    def logpdf(self,z):
        return -.5*np.sum(z*z,axis=1)-.5*DIM*math.log(2*math.pi)

def metrics(x,lp,lq):
    logw=lp-lq
    w=np.exp(logw-logsumexp(logw))
    return {'ESS':float(1/(w@w)), 'max_weight':float(w.max()),
            'logZ_error':float(logsumexp(logw)-math.log(len(logw))),
            'cdf_endpoints':int(np.logical_or(ndtr(x)<=0,ndtr(x)>=1).sum())}

def main():
    base=StandardNormalBase()
    # Analytic Z=1 synthetic target, explicitly NOT the X-PSI target.
    target=BoundedGaussian(np.ones(DIM)*.22,np.eye(DIM)*.85,bound=7)
    tr=base.from_unit(qmc.Sobol(17,scramble=True,seed=1107).random_base2(11)[:,1:17])
    training_lw=target.logpdf(tr)-base.logpdf(tr)
    proposal,meta=fit_training_only(tr,training_lw,base,model_sha256='SYNTHETIC_NO_XPSI')
    records=[]
    for seed in [2101,2103,2107,2111]:
        u=qmc.Sobol(17,scramble=True,seed=seed).random_base2(10)
        b=base.from_unit(u[:,1:17]); v=proposal.from_unit(u)
        records.append({'seed':seed,'base':metrics(b,target.logpdf(b),base.logpdf(b)),
                        'candidate':metrics(v,target.logpdf(v),proposal.logpdf(v))})
    result={'scope':'SYNTHETIC ONLY -- NOT NATIVE PHOTON / EOS',
            'target':'normalized 13D bounded transformed Gaussian, analytic evidence=1',
            'proposal_identity_sha256':meta['proposal_sha256'],
            'training_sha256':meta['training_sha256'],
            'training_ESS':meta['training_ESS'],
            'phase_two_dimensions':'included in 13D source-normal latent; no torus-fit claim',
            'fresh_real_photon_calls':0,'records':records}
    with open('synthetic_report.json','x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write('\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()

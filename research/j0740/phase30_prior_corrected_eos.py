"""Constrained seven-source-EOS posterior/prior-ratio calculation.

This is NOT a final physical EOS posterior. Seven fixed EOS labels, empirical
same-baryonic-mass rotation and a chosen star population mass measure are used.
X-PSI prior source geometry is algebraically restored from archived code, but
photon likelihood is inferred through gridded posterior-density KDE. Radio mass
information is included once: pi_target_mass=pi_radio, pi_source includes
pi_radio, and the ratio cancels it algebraically.
"""
from __future__ import annotations
import hashlib
import json
import sys
import os
from pathlib import Path
import numpy as np
from scipy.stats import truncnorm
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'phase28_base'))
from j0740_eos_phase25 import posterior_grid, integrate_eos_curve
from rotation_same_baryon_audit import fit_forward
from phase28_7eos_integrated_mass_radius_diagnostic import eos_curves,restrict_static_curve,load_causal,SPIN
from phase30_prior_core import star_support,R_MIN_KM,R_MAX_KM,geometric_analytic,POSTERIOR_SHA,MASS_MU,MASS_STD

D_PATH=Path(os.environ.get('J0740_POSTERIOR','/mnt/data/j0740_inputs/J07406620_amsterdam_gamma_NICERXMM_equal_weights_recent.npz'))

def source_mass_pdf(x):
    return truncnorm.pdf(x,-5,5,loc=MASS_MU,scale=MASS_STD)


def source_effective_prior_grid(mg,rg,geometry_acceptance):
    if not (geometry_acceptance>0):raise ValueError('invalid geometric acceptance')
    ok=star_support(mg[:,None],rg[None,:])
    return (source_mass_pdf(mg)[:,None]/(R_MAX_KM-R_MIN_KM)/geometry_acceptance)*ok,ok


def run(path=D_PATH):
    path=Path(path)
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    if sha!=POSTERIOR_SHA:raise ValueError('unexpected Salmi SHA256')
    with np.load(path,allow_pickle=False) as z:
        m=np.asarray(z['mass']);r=np.asarray(z['radius'])
    curves=eos_curves();causal=load_causal()
    acceptance=geometric_analytic()['acceptance']
    output={'status':'SEVEN_FIXED_EOS_POSTERIOR_PRIOR_LIKELIHOOD_RATIO_DIAGNOSTIC_CONDITIONAL_NOT_FINAL',
        'source_sha256':sha,'source_n':len(m),'xpsi_prior_analytic_acceptance':acceptance,
        'radio_factorization':'pi_source(M,R)=pi_radio(M)*U(R)*I_native_shape_g(M,R)/A_geom; target_mass_prior=pi_radio once; cancels inside q/pi_source ratio, no second independent radio likelihood multiplied',
        'curve_label_set':list(curves),'reproduction':'Direct seven-source-EOS fixed-curve proxy; rotating M-R via empirical same-baryon fit, not full GR',
        'grid_modes':{},'statistical_limits':[
           'Relative likelihood proxy from a KDE of a 100k posterior subsample, not direct event-level X-PSI evaluation or nested-sampler convergence.',
           'Spin correction uses approximate mass/radius relation, not full rotating GR stellar sequences.',
           'Model mass/population/selection measure is an explicit choice; EOS stability support and alternative normalization must be compared.',
           'The native effective gravity Cython formula was transcribed to Python, not executed as compiled original extension.',
           'Nuisance factorization follows user-extracted STU CustomPrior and assumes no additional hidden M/R-coupled base-prior transformations.',
           'Relative scores are not universal EOS probabilities and must not be combined with Legred GP 10k posterior as independent data.'
        ]}
    for smooth in [.7,1.2,2.0]:
        for mode in ['truncate','reflect']:
            mg,rg,q=posterior_grid(m,r,smooth_bins=smooth,radius_boundary=mode)
            pi,valid=source_effective_prior_grid(mg,rg,acceptance)
            dM=mg[1]-mg[0];dR=rg[1]-rg[0]
            leaked_mass=float(np.sum(q[~valid])*dM*dR)
            q=np.where(valid,q,0.)
            q/=np.sum(q)*dM*dR
            scores={};diagnostics={}
            for name,(ms,rs) in curves.items():
                sm,sr=restrict_static_curve(ms,rs,causal[name])
                cm,cr=fit_forward(sm,sr,SPIN)
                logv=integrate_eos_curve(mg,rg,q,pi,cm,cr,target_mass_pdf=source_mass_pdf)
                score=float(np.exp(logv)) if np.isfinite(logv) else 0.0
                a=float(truncnorm.cdf(cm[-1],-5,5,loc=MASS_MU,scale=MASS_STD)-truncnorm.cdf(cm[0],-5,5,loc=MASS_MU,scale=MASS_STD))
                if not a>0:raise RuntimeError('missing EOS support')
                scores[name]=score
                diagnostics[name]={'relative_likelihood_proxy':score,'mass_support_probability':a,'conditioned_score_sensitivity':score/a}
            output['grid_modes'][f'sigma={smooth}|boundary={mode}']={
                'outside_native_prior_KDE_probability_before_clip':leaked_mass,
                'inside_KDE_probability_after_clip':float(np.sum(q)*dM*dR),
                'scores':diagnostics,
                'ordering_raw':[k for k,v in sorted(scores.items(),key=lambda a:-a[1])],
                'ordering_mass_conditioned_sensitivity':[k for k,v in sorted(diagnostics.items(),key=lambda a:-a[1]['conditioned_score_sensitivity'])]}
    return output

if __name__=='__main__':
    o=run()
    (ROOT/'phase30_seven_eos_prior_corrected_proxy.json').write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n')
    for mode,x in o['grid_modes'].items():
        print(mode,'KDE clipped %',x['outside_native_prior_KDE_probability_before_clip']*100,
              'RATIO-SCORE order',x['ordering_raw'], 'MASS-conditioned order',x['ordering_mass_conditioned_sensitivity'])
        if mode=='sigma=1.2|boundary=truncate':
            for n,v in x['scores'].items():print(n, f"{v['relative_likelihood_proxy']:.8g}",f"{v['conditioned_score_sensitivity']:.8g}")

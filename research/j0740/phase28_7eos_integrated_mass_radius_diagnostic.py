#!/usr/bin/env python3
"""Scientific **diagnostic**, not calibrated EOS likelihood/evidence.

Integrate q(R_eq(M)|M,D) against the radio mass prior for seven source EOS,
using observed 100k Salmi (M,R_eq) draws, with source-identified 2020 empirical
same-baryon-mass rotating-star fitting equations. Values have units km^-1.

NEVER treat these source-posterior-conditional density scores as EOS Bayes
factors or evidence. This code does not reconstruct the native pi_eff(M,R_eq).
"""
from __future__ import annotations
import hashlib, json, sys, os
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from scipy.interpolate import PchipInterpolator
sys.path.insert(0,str(Path(__file__).parent))
from j0740_eos_phase25 import posterior_grid,normal_pdf,integrate_eos_curve
from rotation_same_baryon_audit import fit_forward

ROOT=Path(__file__).parent
DATA=Path(os.environ.get('J0740_POSTERIOR',str(ROOT/'J07406620_amsterdam_gamma_NICERXMM_equal_weights_recent.npz')))
EXPECTED_SHA='4587a7d71aca7b561e5cf22623e3f0e2d80a6c54add0ecb7abc0389d705e8d5b'
SPIN=346.536369
SOURCE_REF='e6768650ce992abfd1153a6833857572fe5cd230'
BLOB_SHA={
'APR4_EPP':'970790a9fd2aeb1f2fccd3ebfdccf206fcd80f89',
'ENG':'d7aada15699c8c5fe297591019150a026e05936b',
'MPA1':'9d8677f69046a4c46b85fbbfefe7c642348d9e50',
'MS1':'e64b9fd2f7b8b6decbaca085268784bb628d9d4b',
'MS1B':'89faf11369935426a4706edf4cb64b5158cb0362',
'WFF1':'208dd291ba9c1107dc02920843f6be55ddc07f79',
'WFF2':'cca4d8c78e20182c18b9c375f486ebac6453e343',
}

def load_causal():
    data=json.loads((ROOT/'phase23_results.json').read_text())
    return {d['model']:float(d['static_causal_mass_cut_msun']) for d in data['models']}


def restrict_static_curve(m,r,limit):
    m=np.asarray(m,float);r=np.asarray(r,float)
    ok=m<limit
    m2=m[ok];r2=r[ok]
    if m2.size<3:raise ValueError('too few supported causal nodes')
    if limit<m[-1]:
        val=np.interp(limit,m,r)
        m2=np.r_[m2,limit];r2=np.r_[r2,val]
    return m2,r2


def eos_curves():
    curves=json.loads((ROOT/'eos_jester_exact_source_adaptive_knots.json').read_text())
    return {name:(np.array(nodes,float)[:,0],np.array(nodes,float)[:,1]) for name,nodes in curves.items()}


def conditional_density_score(mg,rg,q,curve_m,curve_r):
    dr=rg[1]-rg[0]
    qmass=q.sum(axis=1)*dr
    # At all grid mass centers the conditional source posterior density q/q(M) is well-defined.
    # No false source-native prior here: q(M) itself is a *posterior* marginal.
    if np.any((qmass==0)&(np.max(q,axis=1)>0)):
        raise RuntimeError('Positive joint density with zero mass marginal')
    pi=np.broadcast_to(qmass[:,None],q.shape).copy()
    return float(np.exp(integrate_eos_curve(mg,rg,q,pi,curve_m,curve_r,
                                          target_mass_pdf=normal_pdf)))


def one_grid(m,r,curves,causal,sigma,method):
    mg,rg,q=posterior_grid(m,r,smooth_bins=sigma,radius_boundary=method)
    out={}
    for name,(ms,rs) in curves.items():
        mr,rr=fit_forward(ms,rs,SPIN)
        if not np.all(np.diff(mr)>0):raise RuntimeError('Nonmonotonic rotating mass mapping')
        cm,cr=restrict_static_curve(ms,rs,causal[name])
        mc,rc=fit_forward(cm,cr,SPIN)
        out[name]={
          'score_static_unrestricted_km_inv':conditional_density_score(mg,rg,q,ms,rs),
          'score_rotating_unrestricted_km_inv':conditional_density_score(mg,rg,q,mr,rr),
          'score_rotating_causal_km_inv':conditional_density_score(mg,rg,q,mc,rc),
          'max_static_mass_in_knots_Msun':float(ms[-1]),
          'causality_static_Mmax_Msun':causal[name],
          'rotating_radius_at_Mobs_median_km':float(np.interp(2.0726268494094584,mr,rr)) if mr[0]<2.0726268494094584<mr[-1] else None,
        }
    return out


def analyze():
    sh=hashlib.sha256(DATA.read_bytes()).hexdigest()
    if sh!=EXPECTED_SHA:raise RuntimeError('Source mismatch')
    with np.load(DATA,allow_pickle=False) as f:
        m,r=np.array(f['mass'],float),np.array(f['radius'],float)
    curves=eos_curves();causal=load_causal();assert set(curves)==set(BLOB_SHA)
    res={'status':'SOURCE_POSTERIOR_CONDITIONAL_DENSITY_DIAGNOSTIC_ONLY_NOT_EOS_BAYES_EVIDENCE',
      'source_posterior_sha256':sh,'source_n':int(len(m)),
      'source_eos_git_commit':SOURCE_REF,'source_eos_blob_sha':BLOB_SHA,
      'eos_mass_radius_knot_error_upper_bound_km':0.002,
      'rotating_fit':'Suleimanov et al 2020 A&A 639 A33, same-baryon empirical fit; not full GR/rns',
      'spin_hz':SPIN,
      'measure':'integral of observed posterior conditional radius density q(R_eq(M)|M,D) against N(2.082,0.0703) mass PDF; units km^-1; not actual event likelihood or Bayes factor',
      'methods':{},
      'warning':'Do not normalize to purported EOS model posterior probabilities; exact native pi_eff and branch/population prior absent.'}
    for sigma in [.7,1.2,2.0]:
        for method in ['truncate','reflect']:
            key=f'sigma={sigma}|boundary={method}'
            res['methods'][key]=one_grid(m,r,curves,causal,sigma,method)
    return res

if __name__=='__main__':
    r=analyze();p=ROOT/'phase28_7eos_source_diagnostic.json';p.write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'status':r['status'],'baseline_rotating_causal':{k:float(v['score_rotating_causal_km_inv']) for k,v in r['methods']['sigma=1.2|boundary=truncate'].items()},'out':str(p)},indent=2))

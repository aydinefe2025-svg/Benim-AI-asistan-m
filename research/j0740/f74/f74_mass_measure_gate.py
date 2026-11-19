#!/usr/bin/env python3
"""F74: empirical mass-measure audit for pinned JESTER NICER gamma posterior.

This is an analysis of the JESTER posterior integration MEASURE, not a source-native
X-PSI likelihood and not an EOS Bayes calculation. In particular the gamma
posterior's exact prior/runner has not been proved identical to the ST-U headline.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np

JESTER_COMMIT="e6768650ce992abfd1153a6833857572fe5cd230"
NICER_FILE="jesterTOV/inference/likelihoods/nicer.py"
NPZ_FILE="jesterTOV/inference/data/NICER/J07406620_amsterdam_gamma_NICERXMM_equal_weights_recent.npz"
NICER_BLOB_SHA="69bd82517ff3f5a8857cd514c711bc5bc039a771"
NPZ_BLOB_SHA="8a5adb339699ea1065aa858bdab406de11b22f72"

def git_blob_sha(p):
    b=Path(p).read_bytes()
    return hashlib.sha1(b'blob '+str(len(b)).encode('ascii')+b'\x00'+b).hexdigest()

def source_semantics(path):
    p=Path(path)
    if not p.exists():raise FileNotFoundError(p)
    sha=git_blob_sha(p)
    if sha!=NICER_BLOB_SHA:raise ValueError('JESTER_SOURCE_BLOB_DRIFT: '+sha)
    s=p.read_text(encoding='utf8')
    flags={
      'pre_sample_mass_from_posterior_flow': 'flow.sample(' in s and ')[:, 0]' in s,
      'log_prob_joint_M_R': 'flow.log_prob(mr_point)' in s,
      'average_joint_prob_at_posterior_mass_samples': 'return logsumexp(logprobs) - jnp.log(logprobs.shape[0])' in s,
      'no_source_prior_division_in_current_NICERLikelihood': '/pi_eff' not in s and 'source_prior' not in s,
    }
    if not all(flags.values()):raise ValueError('JESTER_METHOD_CHANGED: re-audit required')
    return {'source_blob_sha1':sha,'observed_source_operators':flags,'source_commit':JESTER_COMMIT}

def pdf_grid(x, y):
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float)
    if x.ndim!=1 or y.shape!=x.shape or len(x)<3 or np.any(np.diff(x)<=0) or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or np.any(y<0):
        raise ValueError('invalid density grid')
    n=float(np.trapezoid(y,x))
    if not n>0:raise ValueError('density zero')
    return y/n

def weighted_moments(x,p):
    q=pdf_grid(x,p)
    mu=float(np.trapezoid(q*x,x)); var=float(np.trapezoid(q*(x-mu)**2,x))
    if not var>0:raise ValueError('variance nonpositive')
    return {'mean':mu,'sigma':math.sqrt(var)}

def infer_mass_measure(x,p):
    p=pdf_grid(x,p)
    c=float(np.trapezoid(p*p,x))
    qq=pdf_grid(x,p*p)
    a=weighted_moments(x,p);b=weighted_moments(x,qq)
    return {'ordinary_mass_pdf_moments':a,'double_weighted_mass_pdf_moments':b,
      'mass_marginal_squared_integral_per_Msun':c,
      'sigma_ratio_squared_over_original':b['sigma']/a['sigma']}

def line_integrals(x,p_mass,q_line):
    x=np.asarray(x,dtype=float);p=np.asarray(p_mass,dtype=float);q=np.asarray(q_line,dtype=float)
    if x.shape!=p.shape or x.shape!=q.shape or not np.all(np.isfinite(q)) or np.any(q<0):raise ValueError('invalid q line')
    # Mass sampling from the posterior marginal: q_m -> E_{q_m}[q(M,R_E(M))].
    if np.any(p<=0) or np.any(~np.isfinite(p)):raise ValueError('source mass marginal has zero / nonfinite support')
    p=pdf_grid(x,p)
    direct=float(np.trapezoid(q,x))
    jester_measure=float(np.trapezoid(p*q,x))
    corrected=float(np.trapezoid(p*(q/p),x))
    return direct,jester_measure,corrected

def empirical_mass_density(mass,n_bins=400,bandwidth_msun=0.006):
    from scipy.ndimage import gaussian_filter1d
    a=np.asarray(mass,dtype=float)
    if a.ndim!=1 or len(a)<1000 or not np.isfinite(a).all():raise ValueError('invalid mass samples')
    m_lo=float(a.min()-0.05);m_hi=float(a.max()+0.05)
    bins=np.linspace(m_lo,m_hi,n_bins+1)
    x=(bins[1:]+bins[:-1])/2
    h=np.histogram(a,bins=bins)[0].astype(float)
    h=gaussian_filter1d(h,sigma=bandwidth_msun/float(np.diff(bins)[0]),mode='constant')
    return x,pdf_grid(x,h)

def kde_line_example(mass,radius,r_points=(11.0,12.5,14.0),bandwidth_msun=0.018,bandwidth_r_km=0.25):
    from scipy.ndimage import gaussian_filter
    mass=np.asarray(mass,dtype=float);radius=np.asarray(radius,dtype=float)
    if len(mass)!=len(radius) or np.any(~np.isfinite(radius)) or radius.min()<0:raise ValueError('wrong radii')
    m_edges=np.linspace(float(mass.min()-0.08),float(mass.max()+0.08),401)
    r_edges=np.linspace(float(radius.min()-0.8),float(radius.max()+0.8),401)
    m=(m_edges[1:]+m_edges[:-1])/2;r=(r_edges[1:]+r_edges[:-1])/2
    dm=float(m_edges[1]-m_edges[0]);dr=float(r_edges[1]-r_edges[0])
    raw=np.histogram2d(mass,radius,bins=(m_edges,r_edges))[0]
    q=gaussian_filter(raw,sigma=(bandwidth_msun/dm,bandwidth_r_km/dr),mode='constant')
    q=q/(np.sum(q)*dm*dr)
    pm=np.sum(q,axis=1)*dr
    if np.min(pm)<=0: # Extremely far Gaussian tails have zeros numerically; clip at positive density floor.
        positive=pm[pm>0];
        if not len(positive):raise ValueError('posterior has zero mass')
        pm=np.maximum(pm,max(1e-12,float(positive.min())*1e-4))
    pm=pdf_grid(m,pm)
    points={}
    for rad in r_points:
        if not r[0]<rad<r[-1]:continue
        line=np.array([np.interp(rad,r,qrow) for qrow in q])
        direct,twice,corr=line_integrals(m,pm,line)
        points[str(rad)]={'ordinary_mass_line_integral_per_km':direct,
          'posterior_mass_presampled_joint_density_integral_per_Msun_km':twice,
          'importance_corrected_to_plain_line_per_km':corr,
          'relative_twice_over_line_per_Msun':twice/direct if direct>0 else None}
    if len(points)<2:raise RuntimeError('insufficient real posterior radii for demonstration')
    return {'schema':'F74_REAL_POSTERIOR_Q_ONLY_MEASURE_DIAGNOSTIC',
      'smoothing_msun':bandwidth_msun,'smoothing_radius_km':bandwidth_r_km,
      'mass_count_grid':len(m),'radius_count_grid':len(r),
      'density_integral':float(np.sum(q)*dm*dr),'mass_marginal':infer_mass_measure(m,pm),
      'constant_radius_diagnostic_not_EOS':points}

def analyze(nicer_source:Path,npz_source:Path):
    source=source_semantics(nicer_source)
    gitsha=git_blob_sha(npz_source)
    if gitsha!=NPZ_BLOB_SHA:raise ValueError('JESTER_100K_NPZ_BLOB_DRIFT: '+gitsha)
    with np.load(npz_source,allow_pickle=False) as z:
        mass=np.asarray(z['mass'],dtype=float)
        radius=np.asarray(z['radius'],dtype=float)
    if mass.shape!=(100000,) or radius.shape!=(100000,):raise ValueError('unexpected source posterior shape')
    x,p=empirical_mass_density(mass)
    diag=kde_line_example(mass,radius)
    return {'schema':'A01.01.51_F74_JESTER_GAMMA_POSTERIOR_MEASURE_GUARD_V1',
      'source':source,'jester_gamma_npz_blob_sha1':gitsha,
      'sample_count':len(mass),'observed_mass_msun':{'mean':float(np.mean(mass)),'sd':float(np.std(mass,ddof=1)),
           'min':float(mass.min()),'max':float(mass.max())},
      'observed_radius_km':{'mean':float(np.mean(radius)),'sd':float(np.std(radius,ddof=1))},
      'empirical_mass_pdf_measure':infer_mass_measure(x,p),
      'KDE_empirical_Q_joint_measure':diag,
      'identity':{'JESTER_documented_operator':'E_{M~q_M}[q(M,R_EOS(M))] (joint posterior evaluated at masses drawn from its posterior marginal)',
        'direct_joint_posterior_line':'Integral q(M,R_EOS(M)) dM',
        'source_prior_corrected_target_evidence':'Integral pi_target(M) * q(M,R_EOS(M))/pi_gamma_source(M,R_EOS(M)) dM',
        'if_MC_draws_from_q_M':'Average [(pi_target(M)/q_M(M)) * (q(M,R_EOS(M))/pi_gamma_source(M,R_EOS(M)))]',
        'note':'The q-only plain-line comparison is a measure diagnostic, NOT a physical EOS likelihood; pi_gamma_source is NOT verified, so the final expression is NOT evaluated.'},
      'honest_flags':{'different_models':'Gamma posterior is NOT verified to be the same analysis run as ST-U headline source prior',
         'JESTER_q_only_source_corrected':'NO',
         'this_is_photon_likelihood':'NO',
         'EOS_Bayes_posterior':'NOT_RUN',
         'conclusion':'SOURCE_MEASURE_ARTIFACT_DEMONSTRATED; FINAL EOS INFERENCE STILL_BLOCKED'}}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--jester',type=Path,required=True);ap.add_argument('--npz',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();r=analyze(a.jester,a.npz);a.out.parent.mkdir(exist_ok=True,parents=True);a.out.write_text(json.dumps(r,indent=2,sort_keys=True,ensure_ascii=False)+'\n');print(json.dumps({'sample_count':r['sample_count'],'mass_pdf':r['empirical_mass_pdf_measure'],'radii':r['KDE_empirical_Q_joint_measure']['constant_radius_diagnostic_not_EOS']},indent=2))

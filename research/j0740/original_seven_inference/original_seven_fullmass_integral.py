#!/usr/bin/env python3
"""Full radio-mass integral of ORIGINAL seven JESTER/LAL static M-R curves.

This is an accurately computable, explicitly defined *static seven-hypothesis*
comparison with the archived F38 prior-corrected marginalized Salmi KDE. It is
NOT source-native photon re-inference, spin-346.5 Hz full-GR, or a physical
nuclear-EOS certification. F42 artificial EOSs are not used anywhere.
"""
from __future__ import annotations
import argparse, io, json, hashlib, zipfile
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator, RegularGridInterpolator
from scipy.integrate import simpson
from scipy.stats import truncnorm

PINNED_F38_SHA = '4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307'
PINNED_SEVEN_SHA = '2521501b7aaf0afec0e067d7bbb680ae1c36327a1f64c83070b58d4e2bc5e119'
PINNED_NPZ_SHA = {
    'APR4_EPP':'639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88',
    'ENG':'702da3ddf7c10b0091af5d8c0d576a9e9a85a85726849a2860bdd8ef3643f953',
    'MPA1':'0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22',
    'MS1':'531530be6253984622f667f454f825ccd13fa4e8960a1411aefe5dd7ea5ff3ad',
    'MS1B':'7a3302e8f2541469fc9ba26dbe52f97b1c8696b71864a208ca43ca7f5cde984c',
    'WFF1':'119b8a25435faeddf00f5d3638f3ff2ff00283ce60caacc24cc37c6e2e030ed3',
    'WFF2':'eb08edc3723fc32d428b3dc3b21aa612dad8a3bdb5da6246faedbb7ed65683ae',
}
M_MU, M_SD, R_MAX_KM = 2.082, .0703, 16.0
M_LOW, M_HIGH = M_MU-5*M_SD, M_MU+5*M_SD
R_MIN_KM=4.42987536
C=2.99792458e8
GM_M_SI=0.5*2.95325024e3
FREQ_HZ=346.53637

def sha(p):
    with open(p,'rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

def density(m):
    return truncnorm.pdf(m,-5.,5.,loc=M_MU,scale=M_SD)

def xpsi_source_support(m,r):
    """Independent copy of pinned F38 original source M-R support, evaluated on a curve."""
    m,r=np.broadcast_arrays(np.asarray(m,dtype=float),np.asarray(r,dtype=float))
    with np.errstate(divide='ignore',invalid='ignore',over='ignore'):
        rsi=1000*r
        zeta=m*GM_M_SI/rsi
        eps=(2*np.pi*FREQ_HZ)**2*rsi**3/(m*GM_M_SI*C*C)
        rp=1+eps*(-.788+1.030*zeta)
        ell=3*eps*(.788-1.030*zeta)
        g0=zeta*C*C/(rsi*np.sqrt(1-2*zeta))
        ce=-.791+.776*zeta
        cp=1.138-1.431*zeta
        de=(-1.315+2.431*zeta)*eps*zeta
        dp=(.653-2.864*zeta)*eps*zeta
        d60=(13.47-27.13*zeta)*eps*zeta
        fe=-1.172*zeta*eps**2
        fp=.975*zeta*eps**2
        ge=g0*(1+(ce+de+fe)*eps)
        gp=g0*(1+(cp+dp-d60)*eps+d60*eps)
        lge=np.log10(ge)+2
        lgp=np.log10(gp)+2
    return ((m>=.001)&(m<=3)&(r>=R_MIN_KM)&(r<=R_MAX_KM)&
            (zeta<.5)&(rp>=3.01*zeta)&(ell>0)&(ell<=1)&
            (lge>=13.7)&(lge<=15)&(lgp>=13.7)&(lgp<=15))

def load_eos(z, name):
    b=z.read(name+'.npz')
    digest=hashlib.sha256(b).hexdigest()
    if digest!=PINNED_NPZ_SHA[name]:raise ValueError(name+' original NPZ SHA mismatch')
    a=np.load(io.BytesIO(b),allow_pickle=False)
    mass=np.asarray(a['masses_EOS'],float);rad=np.asarray(a['radii_EOS'],float)
    if not 450<=len(mass)<=500 or len(rad)!=len(mass) or np.any(~np.isfinite(mass)) or np.any(~np.isfinite(rad)):
        raise ValueError('not original 500-point static curve '+name)
    mask=mass>=1.0 # below this some published TOV curves show non-monotonic low-M crust branches
    m,r=mass[mask],rad[mask]
    if len(m)<60 or np.any(np.diff(m)<=0) or np.any(r<=0):
        raise ValueError(name+' no unique monotone high-mass static branch')
    maxM=float(mass.max())
    if abs(m[-1]-maxM)>1e-8:raise ValueError(name+' latest source point is not its original source MTOV')
    return PchipInterpolator(m,r,extrapolate=False),maxM,float(np.interp(2.073,m,r)),digest

def load_surface(z, key):
    a=np.load(io.BytesIO(z.read('posterior_prior_ratio_'+key+'.npz')),allow_pickle=False)
    mass=np.asarray(a['mass_centres'],float);radius=np.asarray(a['radius_centres_km'],float)
    source=np.asarray(a['relative_likelihood_L_over_Z'],float)
    mask=np.asarray(a['hard_source_support'],bool)
    if source.shape != (401,581) or np.any(~np.isfinite(source)) or np.any(source<0) or np.any(source[~mask]>0):
        raise ValueError('F38 source KDE malformed')
    if abs(mass.min()-1.731376558603491)>1e-10 or abs(mass.max()-2.4326234413965087)>1e-10:
        raise ValueError('F38 mass support changed')
    return RegularGridInterpolator((mass,radius),source,method='linear',bounds_error=False,fill_value=0.),float(np.max(source))

def model_integration(rcurve,maxM,surface,*,n=4001):
    lo=float(M_LOW)
    hi=float(min(M_HIGH,maxM))
    if hi<=lo:return dict(value=0,source_support_prior_probability=0)
    m=np.linspace(lo,hi,n)
    r=np.asarray(rcurve(m),float)
    allowed=xpsi_source_support(m,r)
    pts=np.column_stack([m,r])
    y=surface(pts)
    y[~allowed]=0.
    result=float(simpson(density(m)*y,x=m))
    # Note: <p> 16km cutoff part of observation support; source prior is zero there.
    support=float(simpson(density(m)*allowed.astype(float),x=m))
    if not np.isfinite(result) or result<0 or not 0<=support<=1+1e-4:
        raise ValueError('mass source integration out of valid range')
    return dict(value=result,source_support_prior_probability=support,
                static_branch_mass_max_msun=maxM,integrated_mass_interval_msun=[lo,hi],
                upper_truncated_radio_prior_mass=float(truncnorm.sf(maxM,-5.,5.,loc=M_MU,scale=M_SD)),
                source_geometry_rejected_in_static_branch_fraction=max(0.,float(truncnorm.cdf(hi,-5,5,loc=M_MU,scale=M_SD)-truncnorm.cdf(lo,-5,5,loc=M_MU,scale=M_SD))-support))

def run(seven_zip,f38_zip,out):
    if sha(seven_zip)!=PINNED_SEVEN_SHA:raise ValueError('original 7 EOS archival bundle SHA mismatch')
    if sha(f38_zip)!=PINNED_F38_SHA:raise ValueError('archived F38 six observational KDE grids SHA mismatch')
    surfaces={};stars={}
    with zipfile.ZipFile(seven_zip) as ez,zipfile.ZipFile(f38_zip) as fz:
        for label in sorted(PINNED_NPZ_SHA):
            c,mmax,r073,dig=load_eos(ez,label)
            stars[label]={'curve':c,'max_mass':mmax,'radius_at_2p073_km':r073,'source_sha256':dig}
        for key in ('weighted_0.015_0.20','weighted_0.025_0.35','weighted_0.040_0.50','resampled_0.015_0.20','resampled_0.025_0.35','resampled_0.040_0.50'):
            surface,maxL=load_surface(fz,key)
            vals={label:model_integration(v['curve'],v['max_mass'],surface) for label,v in stars.items()}
            denom=sum(v['value'] for v in vals.values())
            if not denom>0:raise ValueError('No evidence for seven EOS')
            for v in vals.values():v['equal_discrete_model_prior_posterior_conditioned_on_static_source_model_set']=v['value']/denom
            surfaces[key]={'model_scores':vals,'max_KDE_L_over_Z':maxL,
                           'mathematical_setting':'static original JESTER LALSuite seven discrete sources, equal prior, F38 reconstructed source-marginalized likelihood; excludes unphysical star masses'}
    summary={}
    for name in sorted(stars):
        vals=np.array([surf['model_scores'][name]['value'] for surf in surfaces.values()])
        ps=np.array([surf['model_scores'][name]['equal_discrete_model_prior_posterior_conditioned_on_static_source_model_set'] for surf in surfaces.values()])
        st=stars[name]
        summary[name]={'original_static_tov_mmax_msun':st['max_mass'],'original_static_R_at_2p073_km':st['radius_at_2p073_km'],
                      'source_npz_sha256':st['source_sha256'],
                      'full_radio_support_L_over_Z_median':float(np.median(vals)),
                      'full_radio_support_L_over_Z_range':[float(np.min(vals)),float(np.max(vals))],
                      'equal_discrete_seven_prior_probability_median_conditional_static_model_set':float(np.median(ps)),
                      'equal_discrete_seven_prior_probability_range_conditional_static_model_set':[float(np.min(ps)),float(np.max(ps))],
                      'observational_support_outside_static_Mtov':float(truncnorm.sf(st['max_mass'],-5,5,loc=M_MU,scale=M_SD))}
    out.mkdir(parents=True,exist_ok=True)
    result={'schema':'j0740-original-seven-native-static-full-radio-mass-source-KDE-v1',
            'source_eos_git_commit':'e6768650ce992abfd1153a6833857572fe5cd230',
            'original_eos_zip_sha256':PINNED_SEVEN_SHA,'source_reconstructed_likelihood_zip_sha256':PINNED_F38_SHA,
            'source_prior_radio_mass_mu_sigma_msun':[M_MU,M_SD],
            'source_prior_radio_mass_truncation_sigma':[-5.,5.],
            'static_not_rotating':True,
            'sample_count_source_F38_original_weighted':1137394,
            'observed_spin_hz':346.536369,
            'evidence_operator':'I_EOS = integral πradio(M) [q(M,R_static_EOS(M))/πsource(M,R_static_EOS(M))] dM; source M/R geometry hard mask, EOS star nonexistent outside Mtov',
            'result_status':'SEVEN_ORIGINAL_EOS_STATIC_FULL_MASS_PRIOR_KDE_BAYES_DIAGNOSTIC_CALCULATED',
            'summary':summary,'six_F38_KDE_surfaces':surfaces,
            'limitations':['The physical pulsar rotates at 346.536369 Hz; static EOS curve is a diagnostic, not a spin-corrected physical Bayes evidence.',
                           'Original LALSuite EOS spline has documented negative cs^2 on six source EOSs (F66); high-density superluminal candidates also occur (F61). Physical 7-EOS admissibility is NOT_CERTIFIED.',
                           'The six F38 KDE ratio arrays approximate the source-native nuisance-marginalized likelihood from published weighted/equal-weight posterior; they are not re-evaluated original photon-event likelihood.',
                           'Only seven discrete source hypotheses, equal model prior. Do not treat this conditional probability as universal EOS posterior.',
                           'Original run1 source 4/4 byte and 4/4 weighted moments validated in prior F31/F32; complete resumed engine v1.2.0/1.2.1 version uncertain.'],
            'real_seven_spin_corrected_eos_Bayes':'NOT_COMPUTED',
            'conditional_seven_original_static_model_scores':'COMPUTED',
            'physical_EOS_acceptance':'NOT_CERTIFIED'}
    file=out/'J0740_original_seven_static_full_mass_KDE_integrals_20261119.json'
    file.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    lines=['eos,M_TOV_solar,R_static_at_2p073_km,L_over_Z_median,L_over_Z_min,L_over_Z_max,static_conditional_prob_median,static_conditional_prob_min,static_conditional_prob_max,missing_static_mass_prior_fraction']
    for name,x in summary.items():
        lines.append(','.join([name,str(x['original_static_tov_mmax_msun']),str(x['original_static_R_at_2p073_km']),
           str(x['full_radio_support_L_over_Z_median']),str(x['full_radio_support_L_over_Z_range'][0]),str(x['full_radio_support_L_over_Z_range'][1]),
           str(x['equal_discrete_seven_prior_probability_median_conditional_static_model_set']),str(x['equal_discrete_seven_prior_probability_range_conditional_static_model_set'][0]),str(x['equal_discrete_seven_prior_probability_range_conditional_static_model_set'][1]),
           str(x['observational_support_outside_static_Mtov'])]))
    (out/'J0740_original_seven_static_full_mass_results_20261119.csv').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'status':result['result_status'],'scores_median':{k:round(v['full_radio_support_L_over_Z_median'],5) for k,v in summary.items()},'probability_median':{k:round(v['equal_discrete_seven_prior_probability_median_conditional_static_model_set'],4) for k,v in summary.items()},'missing_upper_static_mass_prior':{k:round(v['observational_support_outside_static_Mtov'],4) for k,v in summary.items()}},indent=2))
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--original-eos-zip',type=Path,required=True);ap.add_argument('--f38-kde-zip',type=Path,required=True);ap.add_argument('--outdir',type=Path,required=True)
    args=ap.parse_args();run(args.original_eos_zip,args.f38_kde_zip,args.outdir)

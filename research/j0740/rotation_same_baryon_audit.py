"""J0740+6620: rotating/static same-baryonic-mass fit diagnostic.

Suleimanov, Poutanen & Werner (2020), A&A 639 A33, Eqs. (1)--(3),
AlGendy & Morsink (2014) shape and effective gravity, as reproduced in
Suleimanov et al. Appendix A equations A.13--A.16.

This is an empirical fit to relativistic configurations; not a direct rotating
stellar-structure calculation and not a proper X-PSI likelihood evaluation.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import numpy as np

G = 6.67430e-11
C = 299792458.0
MSUN = 1.988409870698051e30
PERIOD_SECONDS = 0.0028857
EXPECTED_POSTERIOR_SHA256 = '4587a7d71aca7b561e5cf22623e3f0e2d80a6c54add0ecb7abc0389d705e8d5b'


def fit_forward(m_static_msun, r_static_km, frequency_hz=1.0/PERIOD_SECONDS):
    """Compute predicted rotating mass and Req from same-baryon static M and R."""
    m = np.asarray(m_static_msun, dtype=float)
    r = np.asarray(r_static_km, dtype=float)
    if np.any(~np.isfinite(m)) or np.any(~np.isfinite(r)) or np.any(m <= 0) or np.any(r <= 0):
        raise ValueError('Mass and radius must be positive and finite')
    if not np.isfinite(frequency_hz) or frequency_hz < 0:
        raise ValueError('Frequency must be finite and nonnegative')
    nu_cr = 1278.0 * np.sqrt(m/1.4) * (10.0/r)**1.5
    q = frequency_hz/nu_cr
    if np.any(q >= 1.07):
        raise ValueError('Fit singularity approached; outside supported regime')
    fR = .9766 + .025/(1.07-q) + .07*(m/1.4)**1.5*q**2
    a1 = .001*(m/1.4)**1.5
    fM = 1.0-a1/1.1 + a1/(1.1-q) + 10*a1*q*q
    return m*fM, r*fR


def fit_inverse(m_rot_msun, r_eq_km, frequency_hz=1.0/PERIOD_SECONDS, maxiter=48):
    """Invert both published fit relations at fixed baryonic mass.

    This is a deterministic transformation of posterior samples, not a new
    posterior reweighting or an EOS likelihood calculation.
    """
    mr = np.asarray(m_rot_msun, dtype=float)
    re = np.asarray(r_eq_km, dtype=float)
    if mr.shape != re.shape:
        raise ValueError('Mass/radius paired arrays must have identical shape')
    if np.any(mr <= 0) or np.any(re <= 0) or np.any(~np.isfinite(mr+re)):
        raise ValueError('Invalid paired posterior mass/radius')
    ms,rs=mr.copy(),re.copy()
    for _ in range(maxiter):
        predicted_m, predicted_re = fit_forward(ms, rs, frequency_hz)
        mnext=ms*mr/predicted_m
        rnext=rs*re/predicted_re
        err=np.max(np.abs(mnext-ms)+np.abs(rnext-rs))
        ms,rs=mnext,rnext
        if err < 1e-12:
            break
    predicted_m, predicted_re = fit_forward(ms, rs, frequency_hz)
    if np.max(np.abs(predicted_m-mr))>1e-9 or np.max(np.abs(predicted_re-re))>1e-8:
        raise RuntimeError('Fit inversion did not converge')
    return ms,rs


def shape_and_gravity(m_rot_msun,r_eq_km, frequency_hz=1.0/PERIOD_SECONDS):
    m=np.asarray(m_rot_msun,dtype=float)
    r=np.asarray(r_eq_km,dtype=float)
    x=G*MSUN*m/(C*C*r*1000.0)
    eta=(2*np.pi*frequency_hz)**2*(r*1000.0)**3/(G*MSUN*m)
    rp=r*(1-eta*(.788-1.03*x))
    g0=G*MSUN*m/(r*1000.0)**2/np.sqrt(1-2*x)
    ce=.776*x-.791
    cp=1.138-1.431*x
    ge=g0*(1+ce*eta)
    gp=g0*(1+cp*eta)
    if np.any(x>=.5) or np.any(ge<=0) or np.any(gp<=0):
        raise ValueError('Invalid surface compactness or gravity')
    return {'polar_radius_km':rp, 'compactness':x,'eta':eta,
            'log10_g_equator_cgs':np.log10(ge*100),
            'log10_g_pole_cgs':np.log10(gp*100)}


def eos_at_rotating_mass(masses_eos, radii_eos, m_rot, frequency_hz=1.0/PERIOD_SECONDS):
    """Return EOS rotating estimate at a fixed observed gravitational mass.

    Stable-branch EOS M/R samples must be monotone increasing in mass.
    """
    m=np.asarray(masses_eos,dtype=float);r=np.asarray(radii_eos,dtype=float)
    if m.ndim!=1 or r.ndim!=1 or m.size!=r.size or m.size<3 or np.any(np.diff(m)<=0):
        raise ValueError('Expected strictly increasing EOS mass curve')
    if np.any(~np.isfinite(m)) or np.any(~np.isfinite(r)) or np.any(r<=0):
        raise ValueError('Invalid EOS curve')
    def from_mass(v):
        rv=np.interp(v,m,r)
        mm,rr=fit_forward(v,rv,frequency_hz)
        return float(mm),float(rr)
    left=float(m[0]);right=float(min(m[-1],m_rot))
    if from_mass(right)[0] < m_rot or from_mass(left)[0] > m_rot:
        raise ValueError('Observed mass cannot be placed on stable EOS branch')
    for _ in range(55):
        mid=(left+right)/2
        if from_mass(mid)[0]<m_rot:left=mid
        else:right=mid
    static_mass=(left+right)/2
    static_r=float(np.interp(static_mass,m,r))
    mcheck,req=from_mass(static_mass)
    if abs(mcheck-m_rot)>1e-9:raise RuntimeError('Wrong EOS rotating mass bracket')
    geo=shape_and_gravity(m_rot,req,frequency_hz)
    return {'M_static_Msun':static_mass,'M_rot_Msun':m_rot,
            'R_static_km':static_r,'R_equatorial_rotating_km':req,
            'R_polar_rotating_km':float(geo['polar_radius_km']),
            'delta_equator_vs_static_m':1000*(req-static_r),
            'mass_shift_Msun':m_rot-static_mass}


def audit_posterior(path):
    path=Path(path)
    source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    if source_hash != EXPECTED_POSTERIOR_SHA256:
        raise ValueError('Unexpected input posterior SHA256')
    with np.load(path,allow_pickle=False) as dat:
        mr=np.array(dat['mass'],dtype=float)
        req=np.array(dat['radius'],dtype=float)
    ms,rs=fit_inverse(mr,req)
    g=shape_and_gravity(mr,req)
    rg=G*MSUN*mr/C**2/1000
    q=lambda x: [float(t) for t in np.quantile(x,[.16,.50,.84])]
    good_gravity=(g['log10_g_equator_cgs']>=13.7)&(g['log10_g_equator_cgs']<=15.)&(g['log10_g_pole_cgs']>=13.7)&(g['log10_g_pole_cgs']<=15.)
    good_pole=g['polar_radius_km']>3*rg
    return {'sha256':source_hash,'count':len(mr),'M_rot_Msun_q16_q50_q84':q(mr),
            'M_static_Msun_q16_q50_q84':q(ms),'R_eq_rot_km_q16_q50_q84':q(req),
            'R_static_km_q16_q50_q84':q(rs),
            'delta_R_eq_vs_static_m_q16_q50_q84':q((req-rs)*1000),
            'delta_mass_Msun_q16_q50_q84':q(mr-ms),
            'R_eq_minus_R_polar_m_q16_q50_q84':q((req-g['polar_radius_km'])*1000),
            'eta_q16_q50_q84':q(g['eta']),
            'support_polar_fraction':float(np.mean(good_pole)),
            'support_gravity_fraction':float(np.mean(good_gravity)),
            'support_both_fraction':float(np.mean(good_pole&good_gravity)),
            'g_equator_log10_cgs_q16_q50_q84':q(g['log10_g_equator_cgs']),
            'g_polar_log10_cgs_q16_q50_q84':q(g['log10_g_pole_cgs'])}

if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser()
    p.add_argument('posterior',help='Local Salmi equal weights M-R NPZ')
    p.add_argument('--eos-dir',help='Optional directory of source JESTER lalsuite EOS NPZs')
    args=p.parse_args()
    out={'posterior':audit_posterior(args.posterior),'eos_models':{}}
    if args.eos_dir:
        with np.load(args.posterior,allow_pickle=False) as d:
            target=float(np.median(d['mass']))
        for name in ['APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2']:
            filepath=Path(args.eos_dir)/(name+'.npz')
            if filepath.exists():
                with np.load(filepath,allow_pickle=False) as d:
                    out['eos_models'][name]=eos_at_rotating_mass(d['masses_EOS'],d['radii_EOS'],target)
    print(json.dumps(out,indent=2,ensure_ascii=False))

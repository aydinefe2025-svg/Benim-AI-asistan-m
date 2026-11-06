"""J0740 phase 30: reconstruction of the ORIGINAL STU X-PSI hard prior.

Grounded in the user's extracted October 2026 Windows console text:
CustomPrior_GLS_compressed_scaling_Dfix.py, main_lp40k_Xse001_Dfix.py.

Exact source expressions for polar surface shape and inequality; geometric
prior integrates other nuisance dimensions only when they are independent of
M/R in the original source. Native X-PSI compiled effective_gravity is NOT
executed: AlGendy-Morsink fit from the earlier F28 audit is an explicitly
labelled approximation, cross-tested for non-binding support on a wide grid.
This is NOT a native pulse-profile likelihood, EOS evidence, or final posterior.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.integrate import trapezoid
from scipy.optimize import brentq
from scipy.stats import norm, skewnorm, qmc, truncnorm
from rotation_same_baryon_audit import G, C, MSUN, shape_and_gravity
from gravity_xpsi_v121 import RG1_XPSI_KM, native_pole_equator_gravity, xpsi_v121_log10_g

MASS_MU, MASS_STD = 2.082, 0.0703
COS_MU, COS_STD, MASS_COS_RHO = 0.0427, 0.00304, 0.800
SPIN_HZ = 346.53637
RG1_KM = RG1_XPSI_KM  # Exact X-PSI v1.2.1 _GM, unlike F28 CODATA
R_MIN_KM, R_MAX_KM = 3*RG1_KM, 16.
POLAR_SOURCE_FACTOR = 2*1.505  # Source literally: Rp/R_eq >= 1.505/R_r_s.
OLD_APPROX_FACTOR = 3.
POSTERIOR_SHA = '4587a7d71aca7b561e5cf22623e3f0e2d80a6c54add0ecb7abc0389d705e8d5b'


def polar_radius_model(m, r):
    """AlGendy & Morsink shape used verbatim in X-PSI CustomPrior line 80.

    epsilon and zeta supplied by tagged X-PSI v1.2.1 Spacetime.py.
    """
    m = np.asarray(m, dtype=float)
    r = np.asarray(r, dtype=float)
    zeta = RG1_KM*m/r
    eps = (2*np.pi*SPIN_HZ)**2*(r*1000.)**3/(RG1_KM*1000*m*C**2)
    return r*(1.+eps*(-0.788+1.030*zeta))


def ellipticity_ok(m, r):
    """Source line 84-90: sqrt(-1/[3 epsilon (-.788+1.030 zeta)])>=1."""
    m = np.asarray(m,dtype=float); r=np.asarray(r,dtype=float)
    eps=(2*np.pi*SPIN_HZ)**2*(r*1000.)**3/(RG1_KM*1000*m*C**2)
    factor=3.*eps*(.788-1.030*RG1_KM*m/r)
    return (factor>0)&(factor<=1)


def critical_radius(m, polar_factor=POLAR_SOURCE_FACTOR):
    """Smallest R_eq from source polar photon-sphere inequality.

    Exact source factor 3.01 (NOT F22 3.00). Other constraints assessed
    independently because X-PSI compiled surface gravity is not available.
    """
    if not np.isfinite(m) or m<=0 or not np.isfinite(polar_factor) or polar_factor<=0:
        raise ValueError('Invalid mass or polar support factor')
    f=lambda r:float(polar_radius_model(m,r))-polar_factor*RG1_KM*m
    if f(R_MAX_KM)<0: return np.nan
    if f(R_MIN_KM)>=0:return R_MIN_KM
    return float(brentq(f,R_MIN_KM,R_MAX_KM,xtol=1e-12))


def r_accept_fraction(m, polar_factor=POLAR_SOURCE_FACTOR):
    a=np.asarray(m,dtype=float)
    roots=np.array([critical_radius(t,polar_factor) for t in a.reshape(-1)])
    roots=roots.reshape(a.shape)
    return np.where(np.isfinite(roots),np.clip((R_MAX_KM-roots)/(R_MAX_KM-R_MIN_KM),0,1),0)


def conditional_radius_density(m,r,polar_factor=POLAR_SOURCE_FACTOR):
    m=float(m); r=float(r)
    low=critical_radius(m,polar_factor)
    if not np.isfinite(low) or r<low or r>R_MAX_KM: return 0.
    return 1./(R_MAX_KM-low)


def cosi_given_mass(m):
    mu=COS_MU+MASS_COS_RHO*(COS_STD/MASS_STD)*(np.asarray(m)-MASS_MU)
    sd=COS_STD*np.sqrt(1-MASS_COS_RHO**2)
    return mu,float(sd)


def star_support(m,r,include_gravity=True):
    m=np.asarray(m,dtype=float);r=np.asarray(r,dtype=float)
    m,r=np.broadcast_arrays(m,r)
    finite=np.isfinite(m)&np.isfinite(r)&(m>0)&(r>=R_MIN_KM)&(r<=R_MAX_KM)
    ok=finite & (polar_radius_model(np.where(m>0,m,1),np.where(r>0,r,R_MIN_KM)) >=POLAR_SOURCE_FACTOR*RG1_KM*np.where(m>0,m,1))
    ok=ok & ellipticity_ok(np.where(m>0,m,1),np.where(r>0,r,R_MIN_KM))
    if include_gravity:
        checked=np.zeros(ok.shape,dtype=bool)
        if np.any(ok):
            pole,eq=native_pole_equator_gravity(m[ok],r[ok],SPIN_HZ)
            checked[ok]=(eq>=13.7)&(eq<=15.)&(pole>=13.7)&(pole<=15.)
        ok=checked
    return ok


def geometric_analytic(polar_factor=POLAR_SOURCE_FACTOR):
    mass_grid=np.linspace(1.4,2.76,3501)
    prior=truncnorm.pdf(mass_grid,-5.,5.,loc=MASS_MU,scale=MASS_STD)
    af=r_accept_fraction(mass_grid,polar_factor)
    factor=trapezoid(prior*af,mass_grid)
    mmean=trapezoid(mass_grid*prior*af,mass_grid)/factor
    marginal=prior*af/factor
    cdf=np.concatenate([[0.],np.cumsum(np.diff(mass_grid)*(marginal[1:]+marginal[:-1])/2)])
    return {'acceptance':float(factor),'mean_mass_after_msun':float(mmean),
        'mass_shift_msun':float(mmean-MASS_MU),
        'm_quantile_16_50_84':np.interp([.16,.5,.84],cdf,mass_grid).tolist(),
        'm_grid_min':float(mass_grid.min()),'m_grid_max':float(mass_grid.max())}


def geometry_independent_qmc(pow2=19,seed=1453):
    u=qmc.Sobol(d=2,scramble=True,seed=seed).random_base2(m=pow2)
    mm=truncnorm.ppf(np.clip(u[:,0],1e-12,1-1e-12),-5.,5.,loc=MASS_MU,scale=MASS_STD)
    rr=R_MIN_KM+(R_MAX_KM-R_MIN_KM)*u[:,1]
    ok=star_support(mm,rr)
    return {'samples':int(ok.size),'acceptance':float(np.mean(ok)),
            'passed':int(np.sum(ok))}


def hot_spot_qmc(pow2=19,seed=27):
    """Draw six geometry coordinates: two isotropic colatitudes, spot radii, phases.

    The source's ordering and non-overlap test are independent of mass/radius,
    so the acceptance factor cancels in the *normalised* M/R marginal prior.
    """
    u=qmc.Sobol(d=6,scramble=True,seed=seed).random_base2(pow2)
    low=.001;hi=np.pi-low
    t1=np.arccos(np.cos(hi)+(np.cos(low)-np.cos(hi))*u[:,0])
    t2=np.arccos(np.cos(hi)+(np.cos(low)-np.cos(hi))*u[:,1])
    cap1=low+(np.pi/2-2*low)*u[:,2]
    cap2=low+(np.pi/2-2*low)*u[:,3]
    phi=2*np.pi*(u[:,4]-.5-u[:,5])
    cossep=np.cos(t1)*np.cos(t2)+np.sin(t1)*np.sin(t2)*np.cos(phi)
    sep=np.arccos(np.clip(cossep,-1,1))
    order=t1<=t2
    nooverlap=sep >= cap1+cap2
    accept=order & nooverlap
    return {'samples':int(u.shape[0]),'ordered_fraction':float(order.mean()),
        'nonoverlap_conditioned_on_order':float(nooverlap[order].mean()),
        'combined_acceptance':float(accept.mean())}


def support_grid_audit(nmass=520,nrad=100):
    masses=np.linspace(1.4,2.74,nmass)
    failing_gravity=0;failing_ellipse=0;sampled=0
    for m in masses:
        lo=critical_radius(m)
        if not np.isfinite(lo): continue
        radii=np.linspace(lo+1e-5,R_MAX_KM,nrad)
        gpole,gequator=native_pole_equator_gravity(m,radii,SPIN_HZ)
        gp=(gequator>=13.7)&(gequator<=15.)&(gpole>=13.7)&(gpole<=15.)
        failing_gravity+=int(np.count_nonzero(~gp))
        failing_ellipse+=int(np.count_nonzero(~ellipticity_ok(m,radii)))
        sampled+=len(radii)
    return {'sampled_points':sampled,'failed_tagged_xpsi_gravity_points':failing_gravity,'failed_source_shape_ellipticity_points':failing_ellipse,
      'warning':'Same published algebra as tagged X-PSI Cython, but Python transcription, not compiled X-PSI runtime; 52k grid samples not a continuum proof.'}


def posterior_support_audit(path):
    p=Path(path)
    h=hashlib.sha256(p.read_bytes()).hexdigest()
    if h!=POSTERIOR_SHA:raise RuntimeError(f'Salmi source SHA mismatch: {h}')
    with np.load(p,allow_pickle=False) as z:
        m=z['mass'];r=z['radius']
    ok=star_support(m,r)
    pole,eq=native_pole_equator_gravity(m,r,SPIN_HZ)
    return {'sha256':h,'samples':len(m),'source_reconstructed_support_pass':int(ok.sum()),
      'max_polar_log10g':float(pole.max()),
      'min_equatorial_log10g':float(eq.min()),
      'gravity_evaluator':'exact algebra from X-PSI v1.2.1 effective_gravity_universal.pyx; Python transcription'}


def run(posterior):
    source=geometric_analytic()
    old=geometric_analytic(OLD_APPROX_FACTOR)
    sim=geometry_independent_qmc()
    h=hot_spot_qmc()
    distance_accept=skewnorm.cdf(1.7,1.7,loc=1.002,scale=.227)-skewnorm.cdf(.01,1.7,loc=1.002,scale=.227)
    out={
      'status':'SOURCE_CODE_GROUNDED_MR_PRIOR_FACTORIZATION_XPSI_V121_GRAVITY_PYTHON_TRANSLATION_NOT_NATIVE_EVENT_LIKELIHOOD',
      'source':{
        'user_extracted_prior':'CustomPrior_GLS_compressed_scaling_Dfix_source.py',
        'source_prior_sha256':hashlib.sha256(Path(__file__).with_name('CustomPrior_GLS_compressed_scaling_Dfix_source.py').read_bytes()).hexdigest(),
        'tagged_xpsi_spacetime_blob_sha':'7897203ee59ee06960715f585f95dc6222580fc5',
        'tagged_xpsi_gravity_kernel_blob_sha':'8774124fbd962aa0e420e0cd72cbe7f1f0330574',
        'original_prior_written_sha_on_Windows':'ECABB879C38D4E4E343E5E304E1BE39D87A7B0A35D7077454E4677EA1458AA93',
        'source_caveat':'Original Windows SHA from user-provided console log, not recomputed on C drive this turn.'},
      'source_polar_multiplier':POLAR_SOURCE_FACTOR,
      'old_F22_multiplier':OLD_APPROX_FACTOR,
      'source_correlation_rho':MASS_COS_RHO,
      'source_radio_mass_prior':'truncnorm(-5,5,loc=2.082,scale=0.0703), as in original inverse_sample',
      'source_conditional_cosi_sigma':cosi_given_mass(MASS_MU)[1],
      'source_at_M2082':{'mass':2.082,
          'root_km':critical_radius(2.082),
          'old_F22_root_km':critical_radius(2.082,OLD_APPROX_FACTOR),
          'root_shift_m':1000*(critical_radius(2.082)-critical_radius(2.082,OLD_APPROX_FACTOR))},
      'geometric_only_analytic_source':source,
      'geometric_only_analytic_old_F22':old,
      'support_acceptance_difference_pp':100*(source['acceptance']-old['acceptance']),
      'geometry_2D_QMC':sim,'independent_hot_region_6D_QMC':h,
      'distance_truncation_acceptance':float(distance_accept),
      'factorized_star_hot_distance_acceptance_DIAGNOSTIC':float(sim['acceptance']*h['combined_acceptance']*distance_accept),
      'geometry_grid_check':support_grid_audit(),
      'posterior':posterior_support_audit(posterior),
      'hard_limitations':[
        'Exact X-PSI v1.2.1 effective-gravity Cython formula transcribed to Python and evaluated at poles/equator; compiled extension not executed, and source CustomPrior must be matched to headline version.',
        'User console text shows headline CustomPrior and main code; original C: drive files not directly re-opened in this session.',
        'Nuisance hot region ordering and overlap factor is independent of M,R and hence cancels after normalizing prior, conditional on shown code and base parameter priors.',
        'This reconstructs prior geometry and marginal factorization, not original event-level photon likelihood nor EOS Bayes factors.',
        'The source code density(point) is not itself a normalized M,R prior; it calls support via __call__ but omits hot-region Jacobian factors and rejection normalization.',
      ]}
    return out

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--posterior',required=True);p.add_argument('--out',required=True)
    args=p.parse_args()
    o=run(args.posterior)
    Path(args.out).write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:o[k] for k in ('source_at_M2082','geometric_only_analytic_source','geometric_only_analytic_old_F22','support_acceptance_difference_pp','geometry_2D_QMC','independent_hot_region_6D_QMC','distance_truncation_acceptance','geometry_grid_check','posterior')},ensure_ascii=False,indent=2))

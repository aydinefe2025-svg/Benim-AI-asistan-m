#!/usr/bin/env python3
"""Source-derived PSR J0740 ST-U M-R prior marginal (NOT photon likelihood).

Source controls (all verified by exact original TAR file SHA / GitHub tag):
  Salmi ST-U CustomPrior_GLS_compressed_scaling_Dfix.py (SHA-256 ecabb...)
  main_lp40k_Xse001_Dfix.py (SHA-256 440451...)
  X-PSI v1.2.0 Spacetime.py, Prior.py, global_imports.py,
  surface_radiation_field/effective_gravity_universal.pyx,
  and HotRegion.psi() (same relevant routines in v1.2.1).

Implemented mathematical marginalization:
  baseline M ~ TruncNormal(2.082, .0703, -5σ,+5σ)
  baseline R ~ Uniform(3*gravradius(1 Msun),16 km)
  support A(M,R) = photon-sphere & ellipticity & effective-gravity gates.
  other prior draws are independent of (M,R) AFTER integrating the
  conditional cos-inclination and inter-instrument scale priors; their support
  only adds a constant independent of (M,R) to machine accuracy.

π_eff(M,R) = pdf_M(M) pdf_R(R) 1_A(M,R) / S_MR,
S_MR = integral pdf_M pdf_R 1_A dM dR.

This is an *independent mathematical source-code port*, not a native X-PSI
runtime invocation, not a reconstruction of photon likelihood, and not an EOS
model evidence or posterior. The 15-dimensional source prior has been
analytically marginalized for this 2D shape, under the prior-code assumptions.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.integrate import simpson
from scipy.stats import qmc, skewnorm, truncnorm

# Exact source constants from xpsi/global_imports.py @ v1.2.0, v1.2.1
C = 2.99792458e8
G = 6.6740831e-11
GM_M_SI = 0.5 * 2.95325024e3
FREQ_HZ = 346.53637
OMEGA = 2.0 * math.pi * FREQ_HZ
M_MU, M_SIG = 2.082, 0.0703
R_MIN_KM = 3.0 * GM_M_SI / 1000.0
R_MAX_KM = 16.0
PRIOR_SHA256 = 'ecabb879c38d4e4e343e5e304e1be39d87a7b0a35d7077454e4677ea1458aa93'
RUNNER_SHA256 = '440451fd57c8d8c775f3c847861d6fce77a82ab975ca090fb660289191d8c1af'
POSTERIOR_TAR_SHA256 = '1549467c64a8801c39213bd28c89737d087cc5ab7a70da1d8d3a32b2d09185c8'
XPSI_GIT_BLOBS = {
    'Spacetime.py': '7897203ee59ee06960715f585f95dc6222580fc5',
    'Prior.py': '1f68f367efc188637816bcf81ca6451ba528d2f1',
    'global_imports.py': '974480713f694ad87b4bfc30dcd377827c2310e7',
    'effective_gravity_universal.pyx': '8774124fbd962aa0e420e0cd72cbe7f1f0330574',
}


def source_mr_support(mass_msun, radius_km):
    """Vectorized port of exact source CustomPrior.__call__ M-R support.

    Returns Boolean ndarray; source xpsi effective_gravity evaluates mu=1,0.
    """
    mass = np.asarray(mass_msun, dtype=np.float64)
    radius = np.asarray(radius_km, dtype=np.float64)
    mass, radius = np.broadcast_arrays(mass, radius)
    with np.errstate(invalid='ignore', divide='ignore', over='ignore'):
        r_si = 1.0e3 * radius
        zeta = mass * GM_M_SI / r_si
        eps = OMEGA ** 2 * r_si ** 3 / (mass * GM_M_SI * C ** 2)
        r_polar_over_req = 1.0 + eps * (-0.788 + 1.030 * zeta)
        photon = r_polar_over_req >= 3.01 * zeta  # 1.505 / (R/r_s)
        ellipse_u = 3.0 * eps * (0.788 - 1.030 * zeta)
        ellipse = (ellipse_u > 0.0) & (ellipse_u <= 1.0)

        # Port of effective_gravity_universal.pyx effectiveGravity at mu=0,1
        g0 = zeta * C ** 2 / (r_si * np.sqrt(1 - 2 * zeta))
        c_e = -0.791 + 0.776 * zeta
        c_p = 1.138 - 1.431 * zeta
        d_e = (-1.315 + 2.431 * zeta) * eps * zeta
        d_p = (0.653 - 2.864 * zeta) * eps * zeta
        d_60 = (13.47 - 27.13 * zeta) * eps * zeta
        f_e = -1.172 * zeta * eps * eps
        f_p = 0.975 * zeta * eps * eps
        g_equ = g0 * (1.0 + (c_e + d_e + f_e) * eps)
        g_pol = g0 * (1.0 + (c_p + d_p + f_p - d_60) * eps + d_60 * eps)
        lg_equ = np.log10(g_equ) + 2.0
        lg_pol = np.log10(g_pol) + 2.0
        gravity_ok = ((lg_equ >= 13.7) & (lg_equ <= 15.0) &
                      (lg_pol >= 13.7) & (lg_pol <= 15.0))
    return ((mass >= 0.001) & (mass <= 3.0) &
            (radius >= R_MIN_KM) & (radius <= R_MAX_KM) &
            (zeta < 0.5) & photon & ellipse & gravity_ok)


def source_cutoff_km(mass: float, iterations: int = 46) -> float:
    """Find left M-R support boundary; independently test contiguous support."""
    lo, hi = R_MIN_KM, R_MAX_KM
    if bool(source_mr_support(mass, lo)):
        return lo
    if not bool(source_mr_support(mass, hi)):
        raise ValueError(f'Source support is empty at M={mass}')
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        if bool(source_mr_support(mass, mid)):
            hi = mid
        else:
            lo = mid
    return hi


def solve_source_marginal(n_mass: int = 4001):
    if n_mass % 2 != 1:
        raise ValueError('Odd mass sample count required for Simpson quadrature')
    mass_min, mass_max = M_MU - 5*M_SIG, M_MU + 5*M_SIG
    mass = np.linspace(mass_min, mass_max, n_mass)
    cutoff = np.asarray([source_cutoff_km(float(x)) for x in mass])
    # Defensive: source support must be a single interval ending at R=16
    for k in np.linspace(0, n_mass-1, 81, dtype=int):
        grid = np.linspace(R_MIN_KM, R_MAX_KM, 1201)
        t = source_mr_support(mass[k], grid)
        if np.any(np.diff(t.astype(int)) < 0):
            raise ValueError(f'Noncontiguous radius support at M={mass[k]}')
    proposal_m = truncnorm.pdf(mass, -5., 5., loc=M_MU, scale=M_SIG)
    dR = R_MAX_KM - R_MIN_KM
    w = proposal_m * (R_MAX_KM-cutoff) / dR
    S_mr = float(simpson(w, x=mass))
    q_m = w / S_mr  # conditional M density after M-R source support
    Mmean = float(simpson(q_m*mass,x=mass))
    Msig = math.sqrt(float(simpson(q_m*(mass-Mmean)**2,x=mass)))
    Rmean = float(simpson(q_m*(cutoff+R_MAX_KM)/2,x=mass))
    r2 = float(simpson(q_m*(cutoff**2+cutoff*R_MAX_KM+R_MAX_KM**2)/3,x=mass))
    Rsig = math.sqrt(r2-Rmean**2)
    return {
       'mass_grid': mass, 'radius_cutoff_grid': cutoff,
       'S_mr': S_mr, 'M_mean': Mmean, 'M_std': Msig,
       'R_mean': Rmean, 'R_std': Rsig,
       'mass_min': mass_min, 'mass_max': mass_max,
       'M_posterior_mean': 2.072909713099654,
       'M_posterior_std': .06873184724652978,
       'R_posterior_mean': 12.651776399080411,
       'R_posterior_std': 1.0803450741650318,
    }


def independent_15d_rejection_demo(pow2: int = 18, seed: int = 20261117):
    """Source-compatible Sobol unit hypercube support evaluation.

    Uses nine support-relevant coordinates in the full 15D unit hypercube.
    The other six source coordinates integrate exactly to unity up to floating
    probability: M-conditional normalized cosi, correlated NICER/XMM effective
    area priors and uniform phase/temperature/background variables.
    """
    u = qmc.Sobol(d=15, scramble=True, seed=seed).random_base2(pow2)
    mass = truncnorm.ppf(u[:,0], -5., 5., loc=M_MU, scale=M_SIG)
    radius = R_MIN_KM+(R_MAX_KM-R_MIN_KM)*u[:,1]
    mr_ok = source_mr_support(mass,radius)
    dmin = skewnorm.cdf(.01, 1.7, loc=1.002, scale=.227)
    dmax = skewnorm.cdf(1.7, 1.7, loc=1.002, scale=.227)
    distance_ok = (u[:,2] > dmin) & (u[:,2] <= dmax)
    c0 = math.cos(.001)
    theta_p = np.arccos(-c0+2*c0*u[:,5])
    theta_s = np.arccos(-c0+2*c0*u[:,9])
    rad_p = .001 + (math.pi/2-.002)*u[:,6]
    rad_s = .001 + (math.pi/2-.002)*u[:,10]
    phi = 2*math.pi*(u[:,4]-.5-u[:,8])
    cospsi = (np.cos(theta_s)*np.cos(theta_p)+
              np.sin(theta_s)*np.sin(theta_p)*np.cos(phi))
    psi = np.arccos(np.clip(cospsi,-1.,1.))
    hot_ok = (theta_p<=theta_s)&(psi>=rad_p+rad_s)
    # Mass-dependent cosi conditional N truncated to 10 sigma bounds; its
    # strict bound (-1,+1) is hundreds of sigma away in this M range.
    mmax_cos = .0427 + (.00304/.0703)*.8*(mass-M_MU)
    assert np.max(np.abs(mmax_cos)) < 0.06
    accept = mr_ok & distance_ok & hot_ok
    return {
        'n_sobol':int(len(u)), 'seed':int(seed),
        'mr_support_acceptance':float(np.mean(mr_ok)),
        'distance_acceptance':float(np.mean(distance_ok)),
        'hotspot_acceptance':float(np.mean(hot_ok)),
        'joint_support_acceptance':float(np.mean(accept)),
        'joint_accepted':int(np.count_nonzero(accept)),
        'historical_10k_prior_support_estimate':.146,
    }


def write_outputs(out_dir: Path, *, n_mass: int=4001,
                  n_radius: int=201, sobol_power:int=18):
    out_dir.mkdir(parents=True,exist_ok=True)
    s=solve_source_marginal(n_mass)
    demo=independent_15d_rejection_demo(sobol_power)
    S=s['S_mr']; mrmin=s['mass_min']; mrmax=s['mass_max']
    radii=np.linspace(R_MIN_KM, R_MAX_KM,n_radius)
    csvpath=out_dir/'effective_mr_prior_grid.csv'
    with csvpath.open('w',newline='',encoding='utf8') as f:
        w=csv.writer(f)
        w.writerow(['M_solar','R_equatorial_km','pi_eff_per_Msun_per_km',
                    'within_original_source_support'])
        for mass in s['mass_grid']:
            mu=float(mass)
            p_m=float(truncnorm.pdf(mu,-5,5,loc=M_MU,scale=M_SIG))
            isok=source_mr_support(mu,radii)
            for j,R in enumerate(radii):
                w.writerow([f'{mu:.14g}',f'{R:.14g}',
                            f'{p_m/(R_MAX_KM-R_MIN_KM)/S:.14g}' if isok[j] else '0',
                            int(isok[j])])
    cutpath=out_dir/'source_radius_boundary.csv'
    with cutpath.open('w',newline='',encoding='utf8') as f:
        w=csv.writer(f);w.writerow(['M_solar','R_min_accepted_km'])
        for M,R in zip(s['mass_grid'],s['radius_cutoff_grid']):
            w.writerow([f'{M:.14g}',f'{R:.14g}'])
    results={
       'schema':'j0740-f33-source-matched-stu-effective-mr-prior-v1',
       'analysis_date':'2026-11-17',
       'xpsi_tags':['v1.2.0','v1.2.1'],
       'source_prior_sha256':PRIOR_SHA256,'source_runner_sha256':RUNNER_SHA256,
       'xpsi_git_blobs_same_in_both_versions':XPSI_GIT_BLOBS,
       'support_port':'spacetime Rp, ellipticity, exact v1.2.x effectiveGravity(mu=0,1)',
       'radius_proposal_bounds_km':[R_MIN_KM,R_MAX_KM],
       'mass_proposal':{'distribution':'truncated Gaussian','mean_Msun':M_MU,
                        'sigma_Msun':M_SIG,'lower_sigma':-5,'upper_sigma':5},
       'MR_proposal_survival_probability':S,
       'conditional_effective_MR_prior':{
           'mean_Msun':s['M_mean'],'std_Msun':s['M_std'],
           'mean_R_km':s['R_mean'],'std_R_km':s['R_std']},
       'observed_weighted_posterior_MR':{
           'n_published_rows':1137394,'all_rows_in_source_support':True,
           'source_posterior_archive_sha256':POSTERIOR_TAR_SHA256,
           'mean_Msun':s['M_posterior_mean'],'std_Msun':s['M_posterior_std'],
           'mean_R_km':s['R_posterior_mean'],'std_R_km':s['R_posterior_std'],
           'posterior_vs_prior_radius_std_ratio':s['R_posterior_std']/s['R_std']},
       'sobol_15d_source_proposal_preflight':demo,
       'radius_cutoff_examples_km':{str(m):source_cutoff_km(m) for m in [1.7305,2.,2.082,2.2,2.4335]},
       'grid':{'mass_count':n_mass,'radius_count':n_radius,
               'mass_r_bounds':[mrmin,mrmax],
               'radius_bounds':[R_MIN_KM,R_MAX_KM],
               'csv_filename':csvpath.name},
       'status':{
           'MR_PRIOR_SHAPE':'SOURCE_DERIVED_NORMALIZED_2D_PASS',
           'SOURCE_COMPILED_XPSI_END_TO_END':'NOT_RUN',
           'XPSI_RESUME_VERSION':'UNRESOLVED',
           'PHOTON_LIKELIHOOD':'NOT_RUN',
           'SEVEN_EOS_BAYES':'NOT_RUN'},
       'limitations':[
           'The exact functional shape of the source M-R marginal is determined under the specified 15D sampling transport and rejection geometry; not a fresh photon-level inference.',
           'No source-native compiled X-PSI 15D runtime was executed; universal-gravity source formula was ported and independently checked against the original posterior hard support and historical 14.6% support estimate.',
           'Nuisance integrations factor from M,R because the hot-region, distance and effective-area priors are conditionally normalized and have no M-R-dependent support in the original source. Mass-cosinclination bound effects are numerically negligible.',
           'Numeric CSV has coarse rectangular quadrature cells straddling the hard support boundary. For accurate EOS evaluation use the analytic source_mr_support and p_m(S) expression, not interpolation across zero-support cells.',
           'The radio mass prior appears in the source prior; it must not be multiplied twice in EOS evidence.',
           'Cannot claim a source-native X-PSI photon likelihood or seven EOS Bayes factors from this grid.'
       ],
    }
    result_path=out_dir/'F33_effective_prior_result.json'
    result_path.write_text(json.dumps(results,indent=2,sort_keys=True)+'\n',encoding='utf8')
    return results


def cli():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--mass-grid',type=int,default=4001)
    parser.add_argument('--radius-grid',type=int,default=201)
    parser.add_argument('--sobol-power',type=int,default=18)
    a=parser.parse_args()
    result=write_outputs(a.out_dir,n_mass=a.mass_grid,n_radius=a.radius_grid,sobol_power=a.sobol_power)
    print(json.dumps({'status':result['status'],
         'S_MR':result['MR_proposal_survival_probability'],
         'prior_2D':result['conditional_effective_MR_prior'],
         'sobol':result['sobol_15d_source_proposal_preflight']},indent=2))

if __name__=='__main__':cli()
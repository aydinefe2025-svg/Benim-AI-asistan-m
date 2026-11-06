"""Find an RNS rotating-GR solution at J0740's OBSERVED gravitational mass.

Same EOS source is checked against independent JESTER static TOV, then
compared against the 2020 semi-empirical same-baryon estimate. The result
is a fixed-EOS, fixed-mass *stellar solution*, NOT a Bayesian EOS posterior.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from rns_benchmark import OBSERVED_SPIN_HZ, run_rns
from validate_jester_rns import stable_reference_radius_at_mass

TARGET_MASS_MSUN = 2.073


def bracketed_rotating_mass_solver(eval_model, target:float, lo:float, hi:float,
                                   *, tolerance:float=0.0015, max_evaluations:int=20):
    """Bracketed bisection, always compare the GRAVITATIONAL MASS output."""
    if not (0 < lo < hi and 0 < target < 4 and tolerance >= 0.0005):
        raise ValueError("invalid mass or central-density bracket")
    l=eval_model(lo);r=eval_model(hi)
    if not (l['mass_msun']<target<r['mass_msun']):
        raise ValueError(f"Target mass not bracketed by increasing stable EOS branch: {l['mass_msun']} to {r['mass_msun']}")
    traces=[{'rho':lo,'mass':l['mass_msun']},{'rho':hi,'mass':r['mass_msun']}]
    for _ in range(max_evaluations):
        mid=(lo+hi)/2
        pred=eval_model(mid)
        m=float(pred['mass_msun'])
        traces.append({'rho':mid,'mass':m,'radius':float(pred['radius_eq_km'])})
        if not l['mass_msun']<=m<=r['mass_msun']:
            raise ValueError('Rotating GR mass nonmonotone in this EOS density bracket')
        if abs(m-target) <= tolerance:
            return pred,traces
        if m < target:
            lo,l=mid,pred
        else:
            hi,r=mid,pred
    raise RuntimeError(f"Target mass fit did not converge within {max_evaluations} evaluations")



def source_fit_valid_branch(masses, radii, frequency_hz):
    """Select the contiguous portion where the published 2020 fit is defined.

    Low-mass TOV sequences may have very large radii. Their fit parameter
    q=nu/nu_critical can exceed the published singularity threshold 1.07,
    even though the high-mass J0740 portion is valid. Never extrapolate
    through invalid nodes; report exactly which source points were removed.
    """
    m = np.asarray(masses, dtype=float)
    r = np.asarray(radii, dtype=float)
    if (m.ndim != 1 or r.shape != m.shape or m.size < 3
            or not np.all(np.isfinite(m)) or not np.all(np.isfinite(r))
            or np.any(m <= 0) or np.any(r <= 0) or np.any(np.diff(m) <= 0)
            or not math.isfinite(frequency_hz) or frequency_hz < 0):
        raise ValueError('Invalid source EOS curve or rotation frequency')
    nu_critical = 1278.0 * np.sqrt(m / 1.4) * (10.0 / r)**1.5
    q = frequency_hz / nu_critical
    valid = np.isfinite(q) & (q < 1.07)
    if np.count_nonzero(valid) < 3:
        raise ValueError('Too few EOS nodes in semi-empirical fit validity domain')
    first = int(np.flatnonzero(valid)[0])
    if not np.all(valid[first:]):
        raise ValueError('Fit-valid source EOS branch not a contiguous high-mass suffix')
    return m[first:], r[first:], {
        'source_nodes': int(m.size),
        'excluded_low_mass_nodes_outside_fit_domain': first,
        'fit_valid_nodes': int(m.size - first),
        'fit_valid_mass_min_msun': float(m[first]),
        'fit_valid_mass_max_msun': float(m[-1]),
        'fit_constraint': 'nu/nu_critical < 1.07; no EOS extrapolation',
    }



def fixed_gravitational_mass_radius_difference(rotating, static, target_mass, *, tolerance=0.0015):
    """Radius difference at the SAME gravitational mass, not same baryon mass.

    RNS prints gravitational mass to 0.001 Msun and radius to 0.01 km.
    Only compare models whose printed masses both match the requested target.
    """
    a=float(rotating['mass_msun']); b=float(static['mass_msun'])
    ra=float(rotating['radius_eq_km']); rb=float(static['radius_eq_km'])
    if not all(math.isfinite(v) for v in (a,b,ra,rb,target_mass)):
        raise ValueError('Non-finite mass or radius in fixed-mass rotation comparison')
    if (abs(a-target_mass)>tolerance or abs(b-target_mass)>tolerance
            or ra<=0 or rb<=0 or ra<=rb):
        raise ValueError('Fixed-gravitational-mass comparison not validated')
    return float(ra-rb)


def calculate(binary:Path,eos:Path,jester_npz:Path,target:float=TARGET_MASS_MSUN):
    if 'MPA1' not in eos.name or 'MPA1' not in jester_npz.name:
        raise ValueError('Source must be exactly matching MPA1 table for this first test')
    fn=lambda ec:run_rns(binary,eos,central_density=ec,spin_hz=OBSERVED_SPIN_HZ)
    rot,trace=bracketed_rotating_mass_solver(fn,target,1.0e15,1.4e15)
    static=run_rns(binary,eos,central_density=rot['central_energy_density_g_cm3'],spin_hz=0)
    # Additional independent zero-spin solve at the SAME gravitational mass.
    # The pre-existing fixed-central-density static result has a different mass.
    static_mass_fn=lambda ec:run_rns(binary,eos,central_density=ec,spin_hz=0)
    static_at_target,static_target_trace=bracketed_rotating_mass_solver(
        static_mass_fn,target,1.0e15,1.4e15)
    same_grav_mass_delta_r=fixed_gravitational_mass_radius_difference(
        rot,static_at_target,target)
    static_target_jester_r=stable_reference_radius_at_mass(
        jester_npz,static_at_target['mass_msun'])
    static_target_source_diff=static_at_target['radius_eq_km']-static_target_jester_r
    if abs(static_target_source_diff)>0.25:
        raise AssertionError('Same-EOS static target-mass TOV validation failed')
    source_static_r=stable_reference_radius_at_mass(jester_npz,static['mass_msun'])
    diff=static['radius_eq_km']-source_static_r
    if abs(diff) > 0.25:
        raise AssertionError(f"Same-EOS static validation failed at target: {diff} km")
    with np.load(jester_npz,allow_pickle=False) as d:
        masses=np.asarray(d['masses_EOS'],dtype=float)
        radii=np.asarray(d['radii_EOS'],dtype=float)
    from pathlib import Path
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from rotation_same_baryon_audit import eos_at_rotating_mass
    valid_masses, valid_radii, fit_domain = source_fit_valid_branch(masses,radii,OBSERVED_SPIN_HZ)
    empirical=eos_at_rotating_mass(valid_masses,valid_radii,target,frequency_hz=OBSERVED_SPIN_HZ)
    return {'status':'J0740_MPA1_FIXED_EOS_MATCHED_MASS_FULL_GR_SOLVED_NOT_BAYES',
            'source_eos':'JESTER MPA1 (NOT generic APR)',
            'source_eos_npz_sha256':hashlib.sha256(jester_npz.read_bytes()).hexdigest(),
            'converted_eos_table_sha256':hashlib.sha256(eos.read_bytes()).hexdigest(),
            'observed_spin_hz':OBSERVED_SPIN_HZ,
            'requested_mass_msun':target,
            'rns_rotating_GR_at_target':rot,
            'rns_nonrotating_same_central_density':static,
            'rns_nonrotating_same_gravitational_mass':static_at_target,
            'rns_equatorial_radius_change_at_fixed_gravitational_mass_km':same_grav_mass_delta_r,
            'rns_nonrotating_target_mass_jester_reference_radius_km':static_target_jester_r,
            'rns_nonrotating_target_mass_minus_jester_TOV_km':static_target_source_diff,
            'static_target_mass_bisection_trace':static_target_trace,
            'jester_source_static_radius_at_static_mass_km':source_static_r,
            'rns_minus_jester_static_TOV_km':diff,
            'F28_2020_empirical_same_baryon_prediction_at_target_mass':empirical,
            'F28_2020_fit_source_domain':fit_domain,
            'GR_minus_empirical_same_EOS_eq_radius_km':rot['radius_eq_km']-empirical['R_equatorial_rotating_km'],
            'central_density_bisection_trace':trace,
            'limitations':['single MPA1 EOS, no model-selection evidence or posterior',
                           'RNS stdout radius rounded to 0.01 km and mass to 0.001 Msun',
                           'finite EOS pressure interpolation from 836 source points to 196 RNS points',
                           'RNS vs semi-empirical fit comparison is at the same observed rotating mass, but frame-of-reference and crust systematic tests are still required',
                           'radius change compared at fixed gravitational mass, NOT fixed baryonic mass',
                           'radio mass prior and X-PSI photon likelihood have NOT been used for this fixed-mass point']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rns',type=Path,required=True)
    p.add_argument('--eos',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--target-mass',type=float,default=TARGET_MASS_MSUN)
    args=p.parse_args()
    answer=calculate(args.rns,args.eos,args.source,args.target_mass)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(answer,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps(answer,indent=2))

if __name__=='__main__':main()

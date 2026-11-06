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


def calculate(binary:Path,eos:Path,jester_npz:Path,target:float=TARGET_MASS_MSUN):
    if 'MPA1' not in eos.name or 'MPA1' not in jester_npz.name:
        raise ValueError('Source must be exactly matching MPA1 table for this first test')
    fn=lambda ec:run_rns(binary,eos,central_density=ec,spin_hz=OBSERVED_SPIN_HZ)
    rot,trace=bracketed_rotating_mass_solver(fn,target,1.0e15,1.4e15)
    static=run_rns(binary,eos,central_density=rot['central_energy_density_g_cm3'],spin_hz=0)
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
    empirical=eos_at_rotating_mass(masses,radii,target,frequency_hz=OBSERVED_SPIN_HZ)
    return {'status':'J0740_MPA1_FIXED_EOS_MATCHED_MASS_FULL_GR_SOLVED_NOT_BAYES',
            'source_eos':'JESTER MPA1 (NOT generic APR)',
            'source_eos_npz_sha256':hashlib.sha256(jester_npz.read_bytes()).hexdigest(),
            'converted_eos_table_sha256':hashlib.sha256(eos.read_bytes()).hexdigest(),
            'observed_spin_hz':OBSERVED_SPIN_HZ,
            'requested_mass_msun':target,
            'rns_rotating_GR_at_target':rot,
            'rns_nonrotating_same_central_density':static,
            'jester_source_static_radius_at_static_mass_km':source_static_r,
            'rns_minus_jester_static_TOV_km':diff,
            'F28_2020_empirical_same_baryon_prediction_at_target_mass':empirical,
            'GR_minus_empirical_same_EOS_eq_radius_km':rot['radius_eq_km']-empirical['R_equatorial_rotating_km'],
            'central_density_bisection_trace':trace,
            'limitations':['single MPA1 EOS, no model-selection evidence or posterior',
                           'RNS stdout radius rounded to 0.01 km and mass to 0.001 Msun',
                           'finite EOS pressure interpolation from 836 source points to 196 RNS points',
                           'RNS vs semi-empirical fit comparison is at the same observed rotating mass, but frame-of-reference and crust systematic tests are still required',
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

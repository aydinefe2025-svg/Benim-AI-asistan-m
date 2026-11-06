"""Cross-check JESTER native TOV M/R against independent static RNS before spin.

No calibration is accepted unless source thermodynamic EOS identity matches.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from rns_benchmark import OBSERVED_SPIN_HZ, run_rns


def stable_reference_radius_at_mass(source: Path, mass: float) -> float:
    with np.load(source,allow_pickle=False) as src:
        masses=np.asarray(src['masses_EOS'],float)
        radii=np.asarray(src['radii_EOS'],float)
    if (masses.ndim!=1 or radii.shape!=masses.shape or
        not np.all(np.isfinite(masses+radii)) or
        np.any(np.diff(masses)<=0)):
        raise ValueError('Source family is not strictly ordered stable branch; do not interpolate')
    if not masses[0]<=mass<=masses[-1]:
        raise ValueError('RNS star mass out of JESTER stable EOS range')
    return float(np.interp(mass,masses,radii))


def compare(binary:Path,eos:Path,npz:Path,ec:float=1e15):
    static=run_rns(binary,eos,central_density=ec,spin_hz=0)
    radius_ref=stable_reference_radius_at_mass(npz,static['mass_msun'])
    diff=static['radius_eq_km']-radius_ref
    rotating=run_rns(binary,eos,central_density=ec,spin_hz=OBSERVED_SPIN_HZ)
    result={'status':'SOURCE_MATCHED_JESTER_GR_STATIC_COMPARISON',
            'source':npz.name,'source_npz_sha256':hashlib.sha256(npz.read_bytes()).hexdigest(),
            'rns_table_sha256':hashlib.sha256(eos.read_bytes()).hexdigest(),
            'central_density_g_cm3':ec,'jester_static_radius_at_RNS_static_mass_km':radius_ref,
            'rns_minus_source_TOV_radius_km':diff,'rns_static':static,'rns_rotating':rotating,
            'radius_increase_at_fixed_central_density_km':rotating['radius_eq_km']-static['radius_eq_km'],
            'max_abs_static_radius_mismatch_allowed_km':0.25,
            'source_name_matches':'MPA1' in npz.name and 'MPA1' in eos.name,
            'disclaimer':'Validation at this central density only; not yet J0740 observed 2.073 solar mass posterior/evidence'}
    if not result['source_name_matches']:
        raise ValueError('Mismatched EOS source labels')
    if abs(diff)>0.25:
        raise AssertionError(f'Same-EOS static TOV radius mismatch {diff:.4f} km exceeds 0.25 km')
    if rotating['radius_eq_km'] <= static['radius_eq_km']:
        raise AssertionError('Rotation did not expand equatorial radius at fixed central density')
    result['status']='SOURCE_MATCHED_STATIC_TOV_AND_GR_SPIN_VALIDATED_ONE_CENTRAL_DENSITY'
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rns',type=Path,required=True)
    p.add_argument('--eos',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ec',type=float,default=1e15)
    a=p.parse_args()
    res=compare(a.rns,a.eos,a.source,a.ec)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(res,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps(res,indent=2))

if __name__=='__main__':main()

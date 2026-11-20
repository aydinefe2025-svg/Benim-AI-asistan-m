#!/usr/bin/env python3
"""F80: physically honest acceptance of two *actual* full-GR RNS C rotations.

Uses untouched legacy F67-BPS hybrid RNS runner only; no EOS claim of nuclear identity.
This step requires real two-grid RNS output (not an archive-only proxy).
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

MODEL = 'JESTER_BPS_CRUST_LAL_MPA1_HIGH_PRESSURE_CROSSING_CAUSAL_TAIL_V1'
RNS_COMMIT = '97e85d325a33e37f702306414533f6cd77812477'
EXPECTED_EOS_SHA = 'f4a183661962acdddc7aebde3830116578feb6fba88a1a68c9fd57a993058675'
GRIDS = ('151x301', '201x401')
TARGET_M = 2.073
TARGET_F = 346.536369


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(raw, tov, *, rns_table_path, enforce_sha=True):
    if raw.get('model') != MODEL or raw.get('schema') != 'J0740_BPS_MPA1_RNS_V1':
        raise ValueError('SOURCE_MODEL_IDENTITY_MISMATCH')
    if raw.get('rns_source', {}).get('commit') != RNS_COMMIT:
        raise ValueError('RNS_SOURCE_DRIFT')
    if raw.get('status') != 'PASS_RNS_TWO_GRID_CONVERGENCE':
        raise ValueError('REAL_TWO_GRID_RNS_NOT_PASS')
    source_sha = raw.get('rns_eos_export', {}).get('sha256')
    if enforce_sha and (source_sha != EXPECTED_EOS_SHA or sha(rns_table_path) != EXPECTED_EOS_SHA):
        raise ValueError('RNS_EOS_SOURCE_BYTE_DRIFT')
    if tov.get('model') != MODEL or tov.get('status') != 'PASS_NUMERICAL_HYBRID_EOS_CANDIDATE_PHYSICAL_ACCEPTANCE_NOT_ESTABLISHED':
        raise ValueError('BASELINE_TOV_NOT_VERIFIED')
    if tov.get('source', {}).get('original_sources_modified') is not False:
        raise ValueError('SOURCE_TOV_MODIFIED')
    reference=tov['TOV']['M2p073']
    if abs(reference['M_msun']-TARGET_M)>1e-5 or not 9.0<reference['R_km']<17.0:
        raise ValueError('TOV_BASELINE_WRONG')
    runs=raw.get('RNS_runs', [])
    if len(runs) != 2: raise ValueError('ACTUAL_RNS_TWO_RUNS_MISSING')
    stars=[];binaries=[]
    for idx,expected in enumerate(GRIDS):
        item=runs[idx]
        star=item.get('result', {})
        if star.get('grid')!=expected or star.get('status')!='PASS':
            raise ValueError('REAL_RNS_GRID_OR_SOLVER_FAILURE')
        f=float(star['spin_hz']);m=float(star['M_msun']);r=float(star['R_equatorial_km']);ec=float(star['rho_c_g_cm3'])
        if not all(map(math.isfinite,(f,m,r,ec))) or ec<=0 or abs(m-TARGET_M)>1e-5 or abs(f-TARGET_F)>.1 or not 8<r<20:
            raise ValueError('INVALID_GR_RNS_STAR')
        b=item.get('rns_binary_sha256','')
        if len(b)!=64: raise ValueError('RNS_BINARY_HASH_MISSING')
        binaries.append(b)
        stars.append({'grid':expected,'M_msun':m,'R_equatorial_km':r,'spin_hz':f,
                      'central_g_cm3':ec,'R_minus_static_km':r-float(reference['R_km']),
                      'binary_sha256':b})
    if binaries[0]==binaries[1]:raise ValueError('NOT_DISTINCT_RNS_GRID_BINARIES')
    dm=abs(stars[0]['M_msun']-stars[1]['M_msun']);dr_m=1000*abs(stars[0]['R_equatorial_km']-stars[1]['R_equatorial_km'])
    if dm>1e-4 or dr_m>50.0:raise ValueError('TWO_GRID_SPATIAL_DIFFERENCE_TOO_LARGE')
    if not all(z['R_minus_static_km']>0 for z in stars):
        raise ValueError('UNEXPECTED_ROTATING_RADIUS_NO_PHYSICAL_CLAIM')
    return {'schema':'J0740_F80_REAL_HYBRID_RNS_TWO_GRID_VALIDATION_V1',
            'model':MODEL,'not_original_nuclear_MPA1':True,'source_RNS_commit':RNS_COMMIT,
            'rns_eos_sha256':source_sha,'target_M_msun':TARGET_M,'target_f_hz':TARGET_F,
            'static_reference':reference,'stars':stars,'grid_delta_mass_msun':dm,
            'grid_delta_R_m':dr_m,
            'result':'REAL_C_ROTATING_GR_TWO_GRID_PASS_NUMERICAL_ONLY',
            'fixed_J_turning_point':'NOT_RUN',
            'global_rotation_stability':'NOT_ESTABLISHED',
            'BPS_core_phase_thermodynamic_microphysics':'NOT_ESTABLISHED_F73_SINGLE_PHASE_SWITCH_EXCLUSION',
            'source_native_XPSI_photon_likelihood':'NOT_RUN',
            'seven_original_physical_EOS_Bayes':'NOT_RUN'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--raw',type=Path,required=True)
    ap.add_argument('--tov',type=Path,required=True)
    ap.add_argument('--eos',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();result=validate(json.loads(a.raw.read_text()),json.loads(a.tov.read_text()),rns_table_path=a.eos)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('result','stars','grid_delta_R_m','grid_delta_mass_msun')},indent=2))
if __name__=='__main__':main()

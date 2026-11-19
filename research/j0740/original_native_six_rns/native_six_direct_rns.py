#!/usr/bin/env python3
"""Genuine (not F42) original six-source JESTER RNS-C stars at PSR J0740 spin.

Uses original F61 true LALSuite TOV roots for the same gravitational mass,
validates source bytes, runs two different EOS table densities, independently
roots BOTH rotating and static RNS C stars. MPA1 is already completed in F62.
NOT a certified physical EOS: low-P LALSuite cs2/phase and original n unphysical.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'research/j0740/rotating_gr'))
sys.path.insert(0,str(ROOT/'research/j0740/f62'))
# When launched from the checked-out repo, adapt relative paths explicitly.
_REPO=Path(__file__).resolve().parents[3] if 'research' in Path(__file__).parts else None
if _REPO and (_REPO/'research/j0740/rotating_gr').exists():
    sys.path.insert(0,str(_REPO/'research/j0740/rotating_gr'))
    sys.path.insert(0,str(_REPO/'research/j0740/f62'))

from jester_to_rns import from_jester_npz, write_rns, C, G
from rns_benchmark import OBSERVED_SPIN_HZ, RNS_COMMIT, sha256_file
from f62_native_mpa1_rotating import trial_root

NAMES=('APR4_EPP','ENG','MS1','MS1B','WFF1','WFF2')
SOURCE_SHA={
'APR4_EPP':'639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88',
'ENG':'702da3ddf7c10b0091af5d8c0d576a9e9a85a85726849a2860bdd8ef3643f953',
'MS1':'531530be6253984622f667f454f825ccd13fa4e8960a1411aefe5dd7ea5ff3ad',
'MS1B':'7a3302e8f2541469fc9ba26dbe52f97b1c8696b71864a208ca43ca7f5cde984c',
'WFF1':'119b8a25435faeddf00f5d3638f3ff2ff00283ce60caacc24cc37c6e2e030ed3',
'WFF2':'eb08edc3723fc32d428b3dc3b21aa612dad8a3bdb5da6246faedbb7ed65683ae'}
F61_SHA='7b2cbcf6df2dc55d33046d9af587dba179dcb2ec77bad0395e628742479cce0a'
TARGET=2.073
TABLES=(151,196)
STATIC_DIFF_LIMIT_KM=.20
MESH_DIFF_LIMIT_KM=.060

def assert_npz_and_F61(source, f61, model):
    if model not in NAMES:raise ValueError('unapproved source model')
    if sha256_file(source)!=SOURCE_SHA[model]:raise ValueError('source original SHA mismatch')
    if sha256_file(f61)!=F61_SHA:raise ValueError('F61 original LAL static source SHA mismatch')
    ref=json.loads(f61.read_text())
    if ref['status']!='DIRECT_NATIVE_STATIC_TOV_ONLY_NOT_ROTATING_OR_EOS_POSTERIOR' or ref['results'][model]['source_npz_sha256']!=SOURCE_SHA[model]:
        raise ValueError('original source not linked to actual F61 static TOV root')
    star=ref['results'][model]['stars']['2.073']
    if star['status']!='DIRECT_NATIVE_LAL_TOV_WITH_SOURCE_MR_CROSSCHECK':raise ValueError('F61 star not actual direct')
    with np.load(source,allow_pickle=False) as z:
        arr={k:np.asarray(z[k],float) for k in ('p','e','n','cs2','h')}
    if not np.all(np.isfinite(arr['p'])) or not np.all(np.diff(arr['p'])>0):raise ValueError('source pressure invalid')
    pc=float(star['central_pressure_si_pa'])*G/C**4
    if not arr['p'][0]<pc<arr['p'][-1]:raise ValueError('original F61 root pressure outside source')
    c2g=C*C/G*1e-3
    anchor=float(np.exp(np.interp(np.log(pc),np.log(arr['p']),np.log(arr['e'])))*c2g)
    issues={'original_negative_or_zero_cs2_knots':int(np.count_nonzero(arr['cs2']<=0)),
            'original_energy_nonincreasing_edges':int(np.count_nonzero(np.diff(arr['e'])<=0)),
            'original_cs2_gt_one_knots':int(np.count_nonzero(arr['cs2']>1)),
            'original_baryon_density_n_is_e_over_mavg_proxy_not_firstlaw_calibrated':True,
            'original_microphysical_thermo_certified':False}
    return anchor,float(star['radius_km']),issues

def run_one(source,f61,binary,model,out):
    out.mkdir(parents=True,exist_ok=True)
    report={'status':'PARTIAL_IN_PROGRESS','model':model,'mass_target_msun':TARGET,'target_spin_hz':OBSERVED_SPIN_HZ,
            'source_commit':'e6768650ce992abfd1153a6833857572fe5cd230',
            'RNS_commit':RNS_COMMIT,'RNS_binary_SHA256':sha256_file(binary),
            'original_eos_npz_SHA256':sha256_file(source) if source.is_file() else None,
            'F61_original_LAL_TOV_SHA256':sha256_file(f61) if f61.is_file() else None,
            'original_EOS_edited':False,'physical_certification':'NOT_ESTABLISHED','native_XPSI_photon_likelihood':'NOT_RUN',
            'full_seven_EOS_Bayes':'NOT_RUN','meshes':{},'failures':[]}
    result_file=out/f'ORIGINAL_{model}_2p073_RNS_C_direct_two_mesh_20261119.json'
    def save():result_file.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    try:
        anchor,static_reference,issues=assert_npz_and_F61(source,f61,model)
        report.update({'reference_F61_native_LAL_static_R_km':static_reference,
                       'F61_static_anchor_central_rho_g_cm3':anchor,'physical_source_flags':issues})
        save()
        for points in TABLES:
            mesh={'status':'IN_PROGRESS','points':points}
            report['meshes'][str(points)]=mesh
            save()
            rows,info=from_jester_npz(source,points=points)
            table=out/f'ORIGINAL_{model}_{points}_RNS_table.rns'
            write_rns(table,rows)
            mesh['source_RNS_table_SHA256']=sha256_file(table)
            mesh['resampling_metadata']=info
            save()
            for label,spin in [('rotating',OBSERVED_SPIN_HZ),('static',0.0)]:
                print(model,points,label,'original RNS-C start',flush=True)
                root=trial_root(binary,table,TARGET,anchor,spin)
                mesh[label]=root
                save()
                actual=root['star']
                if abs(actual['mass_msun']-TARGET)>0.0015 or abs(actual['spin_hz_reported']-spin)>0.25:
                    raise AssertionError('C computed star does not match requested mass or spin')
            rotating=mesh['rotating']['star'];static=mesh['static']['star']
            mesh['rotating_minus_static_req_km']=float(rotating['radius_eq_km']-static['radius_eq_km'])
            mesh['static_minus_direct_LAL_reference_km']=float(static['radius_eq_km']-static_reference)
            mesh['numeric_static_agrees_LAL']=abs(mesh['static_minus_direct_LAL_reference_km'])<STATIC_DIFF_LIMIT_KM
            mesh['rotating_eq_radius_gt_static_req']=mesh['rotating_minus_static_req_km']>0
            if not (mesh['numeric_static_agrees_LAL'] and mesh['rotating_eq_radius_gt_static_req']):
                raise AssertionError('source-original RNS static fails independent LAL TOV gate')
            mesh['status']='REAL_DIRECT_C_ROTATING_STATIC_MASS_SPIN_ROOT_PASS'
            save()
        coarse=report['meshes']['151']['rotating']['star']['radius_eq_km']
        fine=report['meshes']['196']['rotating']['star']['radius_eq_km']
        delta=fine-coarse
        report['196_minus_151_rotating_req_km']=delta
        report['both_eos_resampling_meshes_within_60m']=abs(delta)<MESH_DIFF_LIMIT_KM
        if not report['both_eos_resampling_meshes_within_60m']:
            raise AssertionError('original source RNS EOS sampling failed 60m gate')
        report['status']='SIX_NON_MPA1_REAL_C_MODEL_TWO_MESH_PASS_NOT_PHYSICAL_EOS_CERT'
    except Exception as e:
        report['status']='FAILED_DIRECT_PHYSICS_NUMERICAL_GUARD_NOT_CLAIMED'
        report['failures'].append({'reason':str(e)[:1200],'type':type(e).__name__})
    save()
    print(json.dumps({'model':model,'status':report['status'],'R196':report.get('meshes',{}).get('196',{}).get('rotating',{}).get('star',{}).get('radius_eq_km'),
                      'R151':report.get('meshes',{}).get('151',{}).get('rotating',{}).get('star',{}).get('radius_eq_km'),
                      'failures':report['failures']}),flush=True)
    return report

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--source',type=Path,required=True);a.add_argument('--f61',type=Path,required=True)
    a.add_argument('--rns',type=Path,required=True);a.add_argument('--model',choices=NAMES,required=True);a.add_argument('--out',type=Path,required=True)
    x=a.parse_args();obj=run_one(x.source,x.f61,x.rns,x.model,x.out)
    if not obj['status'].endswith('PASS_NOT_PHYSICAL_EOS_CERT'):raise SystemExit(2)

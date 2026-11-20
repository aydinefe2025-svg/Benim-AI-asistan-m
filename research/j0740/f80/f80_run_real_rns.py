#!/usr/bin/env python3
"""F80: solve two genuine C RNS rotating stars using already archived BPS–MPA1 EOS bytes.

No new EOS, no imaginary C rows: builds on the old untampered source-locked
runner and *original previously exported* 1213-row thermodynamic RNS file.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT/'research/j0740/physical_eos_validation'))
from run_jester_bps_mpa1_rns import solve_one_grid
from f80_rotation_acceptance import MODEL, RNS_COMMIT, EXPECTED_EOS_SHA, GRIDS, TARGET_M, TARGET_F, sha


def run(eos, binaries):
    if len(binaries)!=2 or len(eos.name)>8: raise ValueError('RNS short path and two binaries required')
    if sha(eos) != EXPECTED_EOS_SHA: raise ValueError('F80_ARCHIVED_EOS_INPUT_SHA_MISMATCH')
    if not all(Path(p).is_file() for p in binaries): raise ValueError('RNS_BINARIES_NOT_BUILT')
    if sha(binaries[0])==sha(binaries[1]):raise ValueError('RNS_GRIDS_NOT_DISTINCT')
    report={'schema':'J0740_BPS_MPA1_RNS_V1', 'model':MODEL,
            'rns_source':{'repository':'rns-alberta/rns','commit':RNS_COMMIT},
            'status':'RUNNING_NOT_CERTIFIED',
            'rns_eos_export':{'sha256':sha(eos),'path':eos.name,'rows':1213,
                'preexisting_archived_export_used_without_reprocessing':True},
            'targets':{'mass_msun':TARGET_M,'spin_hz':TARGET_F},
            'limits':{'source_native_XPSI':'NOT_RUN','hybrid_microphysics':'NOT_ESTABLISHED',
                      'seven_physical_EOS_Bayes':'NOT_RUN'},'RNS_runs':[]}
    for binary,grid in zip(binaries,GRIDS):
        result=solve_one_grid(Path(binary).resolve(),eos,grid)
        result['rns_binary_sha256']=sha(binary)
        report['RNS_runs'].append(result)
        if result['result'].get('status')!='PASS':
            report['status']='FAIL_REAL_RNS_C_GRID_'+grid
            return report
    stars=[x['result'] for x in report['RNS_runs']]
    dm=abs(stars[0]['M_msun']-stars[1]['M_msun'])
    dr=abs(stars[0]['R_equatorial_km']-stars[1]['R_equatorial_km'])
    ok=(dm<1e-4 and dr<0.05)
    report['grid_convergence']={'passed':ok,'mass_difference_msun':dm,'radius_difference_km':dr}
    report['status']='PASS_RNS_TWO_GRID_CONVERGENCE' if ok else 'FAIL_RNS_OR_GRID_CONVERGENCE'
    return report


def main():
    a=argparse.ArgumentParser();a.add_argument('--eos',type=Path,required=True)
    a.add_argument('--rns',type=Path,nargs=2,required=True)
    a.add_argument('--out',type=Path,required=True)
    z=a.parse_args();result=run(z.eos,z.rns)
    z.out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],
           'direct_C_stars':[x['result'] for x in result['RNS_runs']]},default=str))
    if result['status']!='PASS_RNS_TWO_GRID_CONVERGENCE':raise SystemExit('F80_REAL_RNS_NOT_ACCEPTED')
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Direct RNS root regression with the equilibrium iteration tightened only."""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=None
ROOT=None
for parent in HERE.parents:
    if (parent/"research"/"j0740"/"rotating_gr"/"precise_apr4_mass_spin_root.py").exists():
        REPO=parent; ROOT=parent.parent; break
    if (parent/"repo"/"research"/"j0740"/"rotating_gr"/"precise_apr4_mass_spin_root.py").exists():
        REPO=parent/"repo"; ROOT=parent; break
if REPO is None:
    raise RuntimeError("could not locate the repository containing precise_apr4_mass_spin_root.py")
RNSPY=REPO/"research"/"j0740"/"rotating_gr"
sys.path.insert(0,str(RNSPY))
import precise_apr4_mass_spin_root as solver

ACCURACY_OLD=1e-4
ACCURACY_NEW=1e-9
EXPECTED_SOURCE_SHA="01c75752fec9453ec63f0ef2fcb2de2070b5129d31134a238143428852200407"
# The pinned 151 and 201 findmodel.c files were byte-identical at the inspected commit.
TARGET_M=2.073
TARGET_F=346.536369
M_TOL=1e-5
F_TOL=1e-4


def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--table',type=Path,required=True)
    ap.add_argument('--prior-roots',type=Path,required=True)
    ap.add_argument('--baseline-v2',type=Path,required=True)
    ap.add_argument('--binary-151',type=Path,required=True)
    ap.add_argument('--binary-201',type=Path,required=True)
    ap.add_argument('--findmodel-151',type=Path,required=True)
    ap.add_argument('--findmodel-201',type=Path,required=True)
    ap.add_argument('--findmodel-source-151',type=Path)
    ap.add_argument('--findmodel-source-201',type=Path)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    if sha(a.findmodel_151)!=sha(a.findmodel_201): raise SystemExit('patched C sources differ')
    raw151=a.findmodel_source_151 or ROOT/'native_prior'/'rns-candidate-151'/'csrc'/'findmodel.c'
    raw201=a.findmodel_source_201 or ROOT/'native_prior'/'rns-candidate-201'/'csrc'/'findmodel.c'
    oldtext=raw151.read_text(encoding='utf-8')
    if sha(raw151)!=EXPECTED_SOURCE_SHA or sha(raw151)!=sha(raw201) or oldtext.count('double accuracy=1e-4;')!=1:
        raise SystemExit('pinned source drift or expected old convergence threshold missing')
    if 'double accuracy=1e-9;' not in a.findmodel_151.read_text(encoding='utf-8'):
        raise SystemExit('patched threshold is not 1e-9')
    prior=json.loads(a.prior_roots.read_text(encoding='utf-8'))
    baseline=json.loads(a.baseline_v2.read_text(encoding='utf-8'))
    patch151=solver.patch_equilibrium_accuracy(raw151,a.findmodel_151,accuracy=ACCURACY_NEW)
    patch201=solver.patch_equilibrium_accuracy(raw201,a.findmodel_201,accuracy=ACCURACY_NEW)
    if patch151['patched_source_sha256']!=patch201['patched_source_sha256']:
        raise SystemExit('151 and 201 patched RNS sources differ')
    meshes=[]
    for n,sd,binary in [(151,301,a.binary_151),(201,401,a.binary_201)]:
        oldmesh=next(x for x in prior['mesh_results'] if str(n) in x['grid'])
        seeds=oldmesh['reused_prior_root_coordinates_as_initial_guesses']
        result=solver.run_grid(binary,a.table,seeds)
        meshes.append({'grid':[n,sd],'binary_sha256':sha(binary),'seeds_used':seeds,
                       'independent_seed_agreement_pass':result['independent_seed_agreement_pass'],
                       'roots':result['seeds'],'failures':result['failures']})
    ok151=meshes[0]['independent_seed_agreement_pass']; ok201=meshes[1]['independent_seed_agreement_pass']
    roots151=meshes[0]['roots']; roots201=meshes[1]['roots']
    delta={'M_201_minus_151_msun':roots201[0]['mass_msun']-roots151[0]['mass_msun'],
           'Req_201_minus_151_km':roots201[0]['radius_eq_km']-roots151[0]['radius_eq_km'],
           'f_201_minus_151_hz':roots201[0]['spin_hz']-roots151[0]['spin_hz'],
           'M0_201_minus_151_msun':roots201[0]['rns_M0_using_native_Mb_msun']-roots151[0]['rns_M0_using_native_Mb_msun']}
    delta['radius_cross_mesh_pass']=abs(delta['Req_201_minus_151_km'])<=solver.BETWEEN_GRID_RADIUS_TOL_KM
    base151=next(x for x in baseline['mesh_results'] if '151' in x['grid'])
    bseed=base151['failures'][0]['trace'][0]
    nseed=roots151[0]['root_trace'][0]
    old_new={'same_seed':{'u_ec_1e15':nseed['u_ec_1e15'],'axis_ratio':nseed['axis_ratio']},
      'old_accuracy_1e-4_seed':{'M':bseed['mass_msun'],'f_Hz':bseed['spin_hz']},
      'tight_accuracy_1e-9_seed':{'M':nseed['mass_msun'],'f_Hz':nseed['spin_hz']},
      'delta_tight_minus_old':{'M_msun':nseed['mass_msun']-bseed['mass_msun'],'f_Hz':nseed['spin_hz']-bseed['spin_hz']}}
    tolpass=all(abs(x['mass_msun']-TARGET_M)<=M_TOL and abs(x['spin_hz']-TARGET_F)<=F_TOL for m in meshes for x in m['roots'])
    out={'schema':'j0740-apr4-rns-tight-inner-equilibrium-roots-v1',
      'status':'PASS_NUMERICAL_ROOT_AND_CROSS_MESH' if ok151 and ok201 and tolpass and delta['radius_cross_mesh_pass'] else 'FAILED_OR_PARTIAL',
      'explanation':'The original RNS rns() wrapper stopped spin iteration at relative equatorial-radius change 1e-4. Tightening only that stopping threshold to 1e-9 removed the low-grid residual floor; EOS table, physics equations, grid, and M/f acceptance tolerances were unchanged.',
      'source_identity':{'rns_commit':solver.RNS_COMMIT,'findmodel_c_sha256':sha(raw151),'patched_findmodel_c_sha256':sha(a.findmodel_151),'patched_lines':'double accuracy=1e-4; -> double accuracy=1e-9;','old_accuracy':ACCURACY_OLD,'new_accuracy':ACCURACY_NEW,'eos_table_sha256':sha(a.table),'eos_table_bytes':a.table.stat().st_size,'prior_root_sha256':sha(a.prior_roots),'baseline_failure_sha256':sha(a.baseline_v2)},
      'target':{'M_msun':TARGET_M,'f_hz':TARGET_F,'M_tolerance_msun':M_TOL,'f_tolerance_hz':F_TOL},
      'same_seed_solver_accuracy_comparison':old_new,'mesh_results':meshes,'cross_mesh':delta,
      'acceptance':{'151_two_independent_seeds_and_tolerances':ok151 and all(abs(x['mass_msun']-TARGET_M)<=M_TOL and abs(x['spin_hz']-TARGET_F)<=F_TOL for x in roots151),
       '201_two_independent_seeds_and_tolerances':ok201 and all(abs(x['mass_msun']-TARGET_M)<=M_TOL and abs(x['spin_hz']-TARGET_F)<=F_TOL for x in roots201),
       'cross_mesh_radius':delta['radius_cross_mesh_pass'],'physical_EOS':'NOT_ESTABLISHED','absolute_baryon_normalization':'CONDITIONAL','continuous_rotating_stability':'NOT_ESTABLISHED','EOS_Bayes':'NOT_RUN'},
      }
    a.out.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'status':out['status'],'sha256':sha(a.out),'bytes':a.out.stat().st_size,'same_seed_delta':old_new['delta_tight_minus_old'],'cross_mesh':delta,'mesh_roots':[{'grid':m['grid'],'pass':m['independent_seed_agreement_pass'],'roots':[{'M':x['mass_msun'],'R':x['radius_eq_km'],'f':x['spin_hz'],'M0':x['rns_M0_using_native_Mb_msun']} for x in m['roots']]} for m in meshes],'acceptance':out['acceptance']},indent=2))
    if out['status']!='PASS_NUMERICAL_ROOT_AND_CROSS_MESH': raise SystemExit(1)
if __name__=='__main__': main()







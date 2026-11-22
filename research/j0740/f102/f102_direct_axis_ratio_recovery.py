#!/usr/bin/env python3
"""F102: only THREE real Einstein C fixed-J roots not solved by F100/F101.

Works from immutable F100 original (24 GR stars, 399 C calls) and immutable
F101 double-SetSpin recovery (one genuine GR star, 70 calls). Never alters the
published matter EOS, spacetime equations, angular momentum goal/tolerance, or
predeclared central-density sample. Uses original RNS CLI -r axis ratio; this
avoids the discontinuous internal -s SetSpin Ridder iteration entirely.

Discrete fixed-J stationary turning point != rotating dynamical eigenmodes.
"""
from __future__ import annotations
import argparse,zipfile,json,hashlib,math,subprocess,sys
from pathlib import Path
from scipy.optimize import brentq
import numpy as np

F100_ZIP='a769506f87b10c63b03768a7b4011aa02aede6bcddd0ae94c99735f6edcc444a'
F101_ZIP='fff0b8b3bec5744ccd88e9825b96cf6984c82fad5a01efb801cde9c881c76eb6'
F100_RESULT='2f60a33262319a50af39d03641eb0a52375037450964d0f3206ae8687712506f'
EOS_SHA='c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
TARGET_J=4.8245626795750385e48
J_REL_TOL=3e-5
GRID=('151x301','201x401')
F101_RECOVERED=('201x401',6)
STILL_MISSING={'151x301':(12,), '201x401':(11,12)}
SOURCE_POINTS=14
RATIOS=(.999,.995,.99,.985,.98,.975,.97,.965,.96,.95,.94,.925,.91,.89)

def sha(b):return hashlib.sha256(b).hexdigest()
def read_data(old:Path,rec:Path):
    old_bytes=old.read_bytes();rec_bytes=rec.read_bytes()
    if sha(old_bytes)!=F100_ZIP:raise ValueError('IMMUTABLE_F100_ZIP_SHA_DRIFT')
    if sha(rec_bytes)!=F101_ZIP:raise ValueError('IMMUTABLE_F101_ZIP_SHA_DRIFT')
    with zipfile.ZipFile(old) as z:
        b=z.read('F100_REAL_NEW_28_TWO_GRID_EINSTEIN_C_STARS.json')
        if sha(b)!=F100_RESULT:raise ValueError('IMMUTABLE_F100_NATIVE_JSON_SHA_DRIFT')
        original=json.loads(b)
        assert original['native_real_C_stars']==24 and original['new_native_C_calls']==399
        assert original['derived_F99_eos_sha256']==EOS_SHA
        assert len(original['predeclared_central_densities_g_cm3'])==14
        for g,expected in [('151x301',(12,)),('201x401',(6,11,12))]:
            results=original['two_grid_results'][g]
            assert tuple(e['source_point_index'] for e in results['real_C_errors'])==expected
            assert len(results['actual_C_stars'])==14-len(expected)
            assert all(s['real_solver_checked'] and s['J_relative_error']<=J_REL_TOL for s in results['actual_C_stars'])
    with zipfile.ZipFile(rec) as z:
        records=[json.loads(line) for line in z.read('F101_ONLY_MISSING_ORIGINAL_F100_REAL_C_201x401.jsonl').decode().splitlines()]
        assert len([a for a in records if a['source_point_index']==6])==9
        report=json.loads(z.read('F101_F100_28_COMBINED_ORIGINAL_AND_PRECISION_RECOVERED_TRUE_C_STARS.json'))
        assert report['status']=='FOUR_C_ROOTS_NOT_ALL_PASS' and report['actual_new_C_success_stars']==1
        assert report['new_call_counts']=={'151x301':16,'201x401':54}
        assert [a['source_point_index'] for a in report['failures']['151x301']]==[12]
        assert [a['source_point_index'] for a in report['failures']['201x401']]==[11,12]
    chosen=records[8]
    assert chosen['source_point_index']==6 and chosen['actual_native_C'] is True
    assert abs(chosen['J_cgs']/TARGET_J-1)<1e-8
    assert math.isclose(chosen['rho_g_cm3'],original['predeclared_central_densities_g_cm3'][6],rel_tol=1e-14)
    # Original successful F101 source C raw trial: no fabricated or rerun stars.
    new_one={'source_point_index':6,'requested_rho_g_cm3':chosen['rho_g_cm3'],
      'reported_rho_g_cm3':chosen['rho_g_cm3'],'M_msun':chosen['M_msun'],
      'R_eq_km':chosen['R_eq_km'],'f_measured_hz':chosen['f_reported_hz'],
      'f_commanded_hz':chosen['requested_spin_hz'],'J_measured_cgs':chosen['J_cgs'],
      'J_target_cgs':TARGET_J,'J_relative_error':abs(chosen['J_cgs']/TARGET_J-1),
      'direct_C_evaluations':9,'real_solver_checked':True,
      'recovered_original_C':'F101_double_SetSpin_9_true_original_C_calls_source_trace_locked',
      'original_9_trials_replayed_without_C_rerun':True}
    return original,new_one

def compile_r_ratio_C(eos,bin_path,rho,ratio):
    """Actual upstream RNS C -r axis-ratio path, never simulator / -s inner root."""
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f81'))
    from f81_exact_mass_spin import parse_rns
    cmd=[str(Path(bin_path).resolve()),'-f',str(eos),'-e',f'{rho:.14e}','-r',f'{ratio:.12f}']
    p=subprocess.run(cmd,check=False,capture_output=True,text=True,timeout=120)
    if p.returncode!=0:raise RuntimeError('SOURCE_C_NONZERO '+p.stdout[-220:]+p.stderr[-220:])
    try:star=parse_rns(p.stdout)
    except Exception as e:raise RuntimeError('REAL_C_RESULT_INVALID '+repr(e)+' '+p.stdout[-200:])
    if abs(star['rho_c_g_cm3']/rho-1)>1e-9:raise ValueError('CENTRAL_SOURCE_DENSITY_CHANGED')
    return star

def root_ratio(eos,bin_path,rho,index,grid,journal):
    trials=[]
    def call(ratio):
        if not(.70<ratio<1):raise ValueError('UNPHYSICAL_R_RATIO')
        try:
            s=compile_r_ratio_C(eos,bin_path,rho,ratio)
            rec={'index':index,'grid':grid,'central_rho_g_cm3':rho,'requested_r_ratio':ratio,
                 'real_RNS_C_solver':True,'M_msun':s['M_msun'],'R_km':s['R_equatorial_km'],
                 'f_spin_report_hz':s['spin_hz'],'J_cgs':s['J_cgs'],
                 'J_rel_error_signed':s['J_cgs']/TARGET_J-1}
        except Exception as e:
            rec={'index':index,'grid':grid,'central_rho_g_cm3':rho,'requested_r_ratio':ratio,
                 'real_C_exception':repr(e)}
            with open(journal,'a') as f:f.write(json.dumps(rec,allow_nan=False)+'\n')
            raise
        with open(journal,'a') as f:f.write(json.dumps(rec,allow_nan=False)+'\n')
        trials.append(rec)
        return s
    bracket=None; last=None
    for r in RATIOS:
        try:s=call(r)
        except (RuntimeError,ValueError) as exc:
            raise RuntimeError('DIRECT_RATIO_NATIVE_C_EVALUATION_FAILED '+repr(exc))
        err=s['J_cgs']/TARGET_J-1
        if abs(err)<=J_REL_TOL:
            candidate=(r,s)
            break
        if last is not None and err*last[1]<0:
            bracket=(last[0],r);break
        last=(r,err)
    else:raise RuntimeError('SOURCE_C_FIXED_J_BRACKET_MISSING_AFTER_TRUE_RATIO_SCAN')
    if bracket is not None:
        def error(rr):return call(rr)['J_cgs']/TARGET_J-1
        rr=brentq(error,*sorted(bracket),xtol=1e-10,rtol=5e-13,maxiter=65)
        candidate=(rr,call(rr))
    r,s=candidate
    je=abs(s['J_cgs']/TARGET_J-1)
    if je>J_REL_TOL:raise RuntimeError('REAL_C_R_RATIO_FIXED_J_NOT_SOLVED_DISCONTINUOUS '+str(je))
    return {'source_point_index':index,'requested_rho_g_cm3':rho,'reported_rho_g_cm3':s['rho_c_g_cm3'],
      'M_msun':s['M_msun'],'R_eq_km':s['R_equatorial_km'],'f_measured_hz':s['spin_hz'],
      'f_commanded_hz':None,'r_ratio_command':r,'J_measured_cgs':s['J_cgs'],
      'J_target_cgs':TARGET_J,'J_relative_error':je,'direct_C_evaluations':len(trials),
      'real_solver_checked':True,'actual_source_branch':'DIRECT_NATIVE_RNS_C_AXIS_RATIO_NO_SetSpin',
      'source_C_evaluations':trials},len(trials)

def combine(real,existing,new_points,counts,eos_sha):
    if eos_sha!=EOS_SHA:raise ValueError('EOS_NOT_IDENTICAL')
    merged={}; signs={}
    for g in GRID:
        old=real['two_grid_results'][g]['actual_C_stars']
        fresh=new_points[g]
        rows=sorted(old+([existing] if g=='201x401' else [])+fresh,key=lambda z:z['source_point_index'])
        if [x['source_point_index'] for x in rows]!=list(range(14)):
            raise ValueError('MISSING_REAL_NATIVE_C_STARS '+g)
        if any(not x['real_solver_checked'] or x['J_relative_error']>J_REL_TOL for x in rows):
            raise ValueError('NATIVE_J_OR_SOURCE_FAIL '+g)
        masses=np.array([p['M_msun'] for p in rows]);rho=np.array([p['reported_rho_g_cm3'] for p in rows]);slopes=np.diff(masses)/np.diff(rho/1e15)
        if not(np.any(slopes>0) and np.any(slopes<0) and np.argmax(masses) in (6,7,8)):
            raise ValueError('NO_PHYSICAL_SAMPLED_ROTATING_TURN '+g)
        signs[g]={'peak_rho_g_cm3':float(rho[np.argmax(masses)]),'peak_M_msun':float(masses.max()),
          'positive_dM_intervals':int(sum(slopes>0)),'negative_dM_intervals':int(sum(slopes<0)),
          'slopes_Msun_per_1e15gcm3':slopes.tolist()}
        merged[g]={'original_F100_unchanged_24_C_stars':len(old),'F101_unchanged_true_C_recovered_star':int(g=='201x401'),
          'F102_new_direct_ratio_true_C_stars':len(fresh),'stars':rows,'measured_slope':signs[g],
          'continuous_axisymmetric_eigenmode_stability':'NOT_PROVEN_BY_EQUILIBRIA'}
    return {'schema':'J0740_F102_ORIGINAL_F100_24_PLUS_F101_1_PLUS_F102_3_TRUE_C_STARS',
     'status':'28_OF_28_ACTUAL_C_STARS_ACROSS_TWO_MESHES_SOURCE_FIXED_J_DISCRETE_TURN_ONLY',
     'original_F100_24_star_source_receipt':F100_RESULT,'original_F101_zip_sha256':F101_ZIP,
     'predeclared_same_central_densities':real['predeclared_central_densities_g_cm3'],
     'same_target_J_cgs':TARGET_J,'same_F99_derived_cold_EOS_sha256':EOS_SHA,
     'original_24_native_C_calls_not_rerun':399,'F101_new_C_calls_already_performed_NOT_RERUN':70,
     'F102_only_three_missing_native_C_calls':sum(counts.values()),'F102_per_grid_source_C_calls':counts,
     'both_native_C_grids':merged,
     'rotating_dynamical_eigenfrequencies':'NOT_RUN',
     'secular_rotating_fixed_J_turning':'DISCRETE_SAMPLED_PEAK_BOTH_GRIDS;_NO_CONTINUOUS_THEOREM_PROVEN',
     'seven_original_EOS_full_native_XPSI_photon_Bayes':'NOT_RUN',
     'different_source_EOS_model':'DERIVED_F99_NOT_SEVEN_ORIGINAL_APR4_EPP'}

def main():
    ap=argparse.ArgumentParser()
    for name in ('f100','f101','eos','rns151','rns201','out'):ap.add_argument('--'+name,required=True)
    a=ap.parse_args();old,one=read_data(Path(a.f100),Path(a.f101))
    if sha(Path(a.eos).read_bytes())!=EOS_SHA:raise ValueError('F99_SOURCE_EOS_SHA_FAIL')
    if len(str(a.eos))>60:raise ValueError('RNS_C_EOS_CHAR60_PATH_BOUND')
    bins={'151x301':a.rns151,'201x401':a.rns201}
    if any(not Path(b).is_file() for b in bins.values()):raise ValueError('MISSING_TWO_COMPILED_EINSTEIN_C_BINARIES')
    if sha(Path(bins['151x301']).read_bytes())==sha(Path(bins['201x401']).read_bytes()):raise ValueError('NOT_TWO_REAL_MESHES')
    output=Path(a.out);output.parent.mkdir(parents=True,exist_ok=True)
    successful={g:[] for g in GRID};counts={g:0 for g in GRID};errors=[]
    for grid in GRID:
        journal=output.parent/f'F102_DIRECT_TRUE_C_R_RATIO_ONLY_{grid}.jsonl'
        if journal.exists():raise FileExistsError('F102_NEVER_OVERWRITE_SOURCE_C_TRACE')
        for ix in STILL_MISSING[grid]:
            try:
                row,ct=root_ratio(Path(a.eos),bins[grid],old['predeclared_central_densities_g_cm3'][ix],ix,grid,journal)
                successful[grid].append(row);counts[grid]+=ct
                print('F102_TRUE_EINSTEIN_C_RATIO_J_ROOT_PASS',grid,ix,row['M_msun'],row['J_relative_error'],ct,flush=True)
            except Exception as exc:
                counts[grid]=sum(1 for s in journal.read_text().splitlines()) if journal.exists() else 0
                errors.append({'grid':grid,'index':ix,'error':repr(exc),'actual_C_calls':counts[grid]})
                print('F102_TRUE_C_RATIO_FAILURE_RETAINED',grid,ix,repr(exc),flush=True)
            output.write_text(json.dumps({'status':'IN_PROGRESS_ONLY_REAL_EINSTEIN_C',
                'F100_24_preserved':True,'F101_1_preserved':True,'F102_new_native_C_passes':successful,
                'errors':errors,'C_calls':counts},indent=2,allow_nan=False)+'\n')
    if errors:
        result={'schema':'F102_FAIL_CLOSED_SOURCE_NATIVE_R_RATIO_ROOTS', 'status':'MISSING_3_TRUE_C_ROOTS_NOT_ALL_PASS',
                'original_24_plus_F101_1_unmodified':True,'new_recovered':successful,'C_calls':counts,
                'errors':errors,'rotating_dynamic_modes':'NOT_RUN','EOS_seven_native_full_Bayes':'NOT_RUN'}
        output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        raise SystemExit(2)
    result=combine(old,one,successful,counts,sha(Path(a.eos).read_bytes()))
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('F102_TRUE_C_28_STAR_SOURCE_R_RATIO_MASS_TURN_COMPLETE',result['F102_only_three_missing_native_C_calls'],flush=True)

if __name__=='__main__': main()

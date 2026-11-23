#!/usr/bin/env python3
"""F128: authentic two-density loose-inner fixed-J RNS/C pilot (601x1201).

A *separate derived* F99 EOS, NOT any of the original published 7 EOS.
Fail-closed; no physical EOS, branch stability or photon-native Bayesian claim.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
import subprocess
import sys
import zipfile
from pathlib import Path

F806_SHA = '0570e05e0493847aefa5c9efc045ec9e0c1c7f5d5487ff6869a6d2f957aa99ad'
F125_SHA = 'c975a6cac8f841e2f4640990042d26a6bed263f90083a7b3d254f426866d82f5'
EOS_SHA = 'c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
UPSTREAM_RNS_COMMIT = '97e85d325a33e37f702306414533f6cd77812477'
J_TARGET = 4.8245626795750385e48
LOW_RHO = 2622286757812500
HIGH_RHO = 2622286761718750
GRID = '601x1201'
ACCURACY = 1e-4
J_TOL = 1e-9
PER_CALL_TIMEOUT_S = 240
MAX_UNIQUE_CALLS = 12
SEEDS = (0.99018, 0.99025, 0.98990, 0.99050, 0.9890, 0.9920)


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_pinned_source(f806_zip: bytes, eos: bytes) -> dict:
    if sha_bytes(f806_zip) != F806_SHA:
        raise ValueError('F806_SOURCE_SHA_MISMATCH')
    if sha_bytes(eos) != EOS_SHA:
        raise ValueError('F99_DERIVED_EOS_SHA_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(f806_zip)) as z:
        if z.testzip() is not None:
            raise ValueError('F806_SOURCE_ZIP_CRC_FAILURE')
        data = json.loads(z.read('F126/F126_UPPER_HALF_BISECTION.json'))
        raw = z.read('F126/F126_UPPER_HALF_BISECTION.jsonl')
        nested = z.read('F125/F125_artifact.zip')
    if sha_bytes(nested) != F125_SHA:
        raise ValueError('F806_NESTED_F125_SHA_MISMATCH')
    if sha_bytes(raw) != data.get('raw_journal_sha256'):
        raise ValueError('F806_RAW_JOURNAL_SHA_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(nested)) as n:
        if n.testzip() is not None:
            raise ValueError('F806_NESTED_F125_ZIP_CRC_FAILURE')
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    roots = data.get('fixed_J_solutions', [])
    if not (data.get('status') == 'F126_UPPER_HALF_BISECTION_COMPLETE' and len(roots) == len(rows) == 1
            and data.get('EOS_sha256') == EOS_SHA and data.get('pinned_RNS_upstream_commit') == UPSTREAM_RNS_COMMIT
            and data.get('mesh') == '3001x6001' and roots[0].get('J_relative_error', 1) <= J_TOL):
        raise ValueError('F806_SOURCE_ACCEPTANCE_FAILED')
    if any(roots[0].get(field) != rows[0].get(field) for field in ('M_msun', 'R_eq_km', 'J_relative_error')):
        raise ValueError('F806_SELECTED_ROOT_NOT_IN_REAL_C_JOURNAL')
    return {'source_F806_sha256': F806_SHA, 'source_F125_sha256': F125_SHA,
            'source_root': roots[0], 'source_chain_valid': True}


def patch_small_mesh(makefile_source: str) -> str:
    old = 'HIGHSIZE=-DMDIV=151 -DSDIV=301'
    if makefile_source.count(old) != 1:
        raise ValueError('PINNED_MAKEFILE_MESH_SOURCE_DRIFT')
    return makefile_source.replace(old, 'HIGHSIZE=-DMDIV=601 -DSDIV=1201', 1)


def parse_native(stdout: str, stderr: str, density: int, ratio: float) -> dict:
    """Accept only one physical C star and *final* spin-call convergence trace."""
    candidates = []
    for line in stdout.splitlines():
        pieces = line.split()
        if len(pieces) != 5:
            continue
        try:
            vals = [float(s) for s in pieces]
        except ValueError:
            continue
        if not all(math.isfinite(v) and v > 0 for v in vals):
            raise ValueError('REAL_NATIVE_C_STAR_NONPOSITIVE_OR_NONFINITE')
        candidates.append(vals)
    if len(candidates) != 1:
        raise ValueError('NOT_ONE_REAL_NATIVE_C_STAR')
    rho15, M, R, f, J = candidates[0]
    if abs(rho15*1e15/density-1) > 1e-9:
        raise ValueError('REAL_NATIVE_C_WRONG_CENTRAL_DENSITY')
    diagnostics = [line.split() for line in stderr.splitlines() if line.startswith('F127_SPIN_FINAL_DIFFERENCE')]
    if not diagnostics:
        raise ValueError('NO_REAL_C_SPIN_DIAGNOSTIC')
    parsed = []
    for v in diagnostics:
        if len(v) != 8 or [v[0],v[2],v[4],v[6]] != ['F127_SPIN_FINAL_DIFFERENCE','ITERATIONS','ACCURACY','ACHECK']:
            raise ValueError('MALFORMED_REAL_C_SPIN_DIAGNOSTIC')
        dif, iteration, tol, check = float(v[1]), int(v[3]), float(v[5]), int(v[7])
        if not all(math.isfinite(a) for a in (dif, tol)) or dif < 0 or tol <= 0 or iteration < 1 or check != 0:
            raise ValueError('INVALID_REAL_C_SPIN_DIAGNOSTIC')
        parsed.append((dif,iteration,tol,check))
    dif,iteration,tol,check = parsed[-1]
    if iteration < 2 or dif > tol or not math.isclose(tol, ACCURACY, rel_tol=1e-12, abs_tol=0):
        raise ValueError('RNS_INNER_STOP_NOT_CONVERGED_TO_LOOSE_TOLERANCE')
    return {'rho_g_cm3': int(density), 'r_ratio': float(ratio), 'M_msun': M, 'R_eq_km': R,
            'f_hz': f, 'J_cgs': J, 'signed_J_relative_error': J/J_TARGET-1.0,
            'J_relative_error': abs(J/J_TARGET-1.0), 'spin_calls_recorded': len(parsed),
            'spin_last_iteration': iteration, 'spin_last_dif': dif,
            'spin_inner_accuracy': tol, 'real_native_RNS_C': True}


def choose_bracket(samples: list[dict]) -> tuple[dict,dict] | None:
    """Choose the narrowest valid sign-changing pair from authentic, finite trials."""
    valid = sorted(
        (r for r in samples if r.get('status') == 'SUCCESS'
         and math.isfinite(r.get('star',{}).get('signed_J_relative_error',float('nan')))),
        key=lambda r:r['r_ratio_cli'])
    candidate_pairs = [(a,b) for a,b in zip(valid,valid[1:])
                       if a['star']['signed_J_relative_error']*b['star']['signed_J_relative_error'] < 0]
    return min(candidate_pairs, key=lambda pair: pair[1]['r_ratio_cli']-pair[0]['r_ratio_cli']) if candidate_pairs else None


class NativeProbe:
    def __init__(self, executable: Path, eos: Path, rho: int, journal_path: Path):
        self.exe, self.eos, self.rho, self.journal_path = executable, eos, int(rho), journal_path
        self.cache = {}

    def evaluate(self, ratio: float) -> dict:
        # Always use exactly the CLI-decimal ratio for cache and provenance.
        ratio = float(f'{ratio:.12f}')
        key = f'{ratio:.12f}'
        if key in self.cache:
            return self.cache[key]
        if len(self.cache) >= MAX_UNIQUE_CALLS:
            raise RuntimeError('MAX_NATIVE_C_TRIALS_EXCEEDED')
        cmd = [str(self.exe.resolve()), '-f', str(self.eos),
               '-e', f'{float(self.rho):.14e}', '-r', key]
        record = {'rho_g_cm3': self.rho, 'r_ratio_cli':ratio,
                  'command':cmd, 'mesh':GRID,'accuracy':ACCURACY,'real_native_RNS_C_attempt':True}
        try:
            p = subprocess.run(cmd, text=True, capture_output=True, timeout=PER_CALL_TIMEOUT_S, check=False)
            record.update({'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
            if p.returncode:
                raise RuntimeError(f'NATIVE_RNS_C_EXIT_{p.returncode}')
            star = parse_native(p.stdout, p.stderr, self.rho, ratio)
            record.update({'star':star,'status':'SUCCESS'})
        except subprocess.TimeoutExpired as err:
            record.update({'status':'FAIL_CLOSED','error':'NATIVE_RNS_C_TIMEOUT_240S',
                           'stdout':err.stdout.decode(errors='replace') if isinstance(err.stdout,bytes) else err.stdout,
                           'stderr':err.stderr.decode(errors='replace') if isinstance(err.stderr,bytes) else err.stderr})
        except Exception as err:
            record.update({'status':'FAIL_CLOSED','error':repr(err)})
        with self.journal_path.open('a',encoding='utf-8') as f:
            f.write(json.dumps(record,sort_keys=True,allow_nan=False)+'\n')
        self.cache[key] = record
        print('F128_REAL_C',self.rho,key,record['status'],
              record.get('star',{}).get('signed_J_relative_error'),record.get('error'),flush=True)
        return record


def solve_fixed_j(probe:NativeProbe) -> dict:
    """Bounded source-pinned same-J root, preserving EVERY genuine native C trial."""
    from scipy.optimize import brentq
    valid=[]
    for ratio in SEEDS:
        rec=probe.evaluate(ratio)
        if rec['status']=='SUCCESS':
            valid.append(rec)
            if rec['star']['J_relative_error'] <= J_TOL:
                return {'status':'ACCEPTED_LOOSE_SAME_J_ROOT','star':rec['star'],
                        'native_C_trials':len(probe.cache), 'method':'exact_cli_seed'}
        br=choose_bracket(valid)
        if br:
            break
    else:
        return {'status':'INCONCLUSIVE_NO_SIGN_CHANGE','native_C_trials':len(probe.cache)}
    lo,hi=br
    if not lo['r_ratio_cli'] < hi['r_ratio_cli']:
        raise ValueError('NON_ASCENDING_BRACKET')
    def signed_residual(r):
        v=probe.evaluate(float(r))
        if v['status'] != 'SUCCESS':
            raise RuntimeError('NATIVE_C_ROOT_REFINEMENT_FAILED')
        return v['star']['signed_J_relative_error']
    try:
        root=brentq(signed_residual,lo['r_ratio_cli'],hi['r_ratio_cli'],
                    xtol=1e-12,rtol=1e-13,maxiter=12)
        record=probe.evaluate(root)
        if record['status']=='SUCCESS' and record['star']['J_relative_error']<=J_TOL:
            return {'status':'ACCEPTED_LOOSE_SAME_J_ROOT','star':record['star'],
                    'native_C_trials':len(probe.cache), 'method':'brentq_on_genuine_native_C_stars'}
        return {'status':'INCONCLUSIVE_ROOT_J_RESIDUAL_TOO_LARGE',
                'native_C_trials':len(probe.cache),'candidate':record.get('star')}
    except Exception as err:
        return {'status':'INCONCLUSIVE_NATIVE_C_ROOT_FAILURE','error':repr(err),
                'native_C_trials':len(probe.cache)}


def main():
    p=argparse.ArgumentParser()
    for k in ('--f806','--eos','--binary','--out'):
        p.add_argument(k,required=True,type=Path)
    a=p.parse_args()
    source=load_pinned_source(a.f806.read_bytes(),a.eos.read_bytes())
    if not a.binary.is_file():
        raise FileNotFoundError('NO_PINNED_RNS_C_BINARY')
    if a.out.exists():
        raise FileExistsError('REFUSE_TO_OVERWRITE_F128_RESULTS')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    receipt={'schema':'J0740_F128_LOOSE_INNER_SAME_J_TWO_DENSITY_REAL_NATIVE_C_601X1201_V1',
             'experiment':'independent pilot at 601x1201; NOT the full 3001x6001 physical or EOS inference',
             'eos_sha256':EOS_SHA,'original_RNS_commit':UPSTREAM_RNS_COMMIT,
             'binary_sha256':sha_bytes(a.binary.read_bytes()),'mesh':GRID,
             'target_J_cgs':J_TARGET, 'inner_radius_iteration_tolerance':ACCURACY,
             'fixed_J_acceptance':J_TOL,'original_old_stop_reference':source,
             'stars':{},'status':'PARTIAL_FAIL_CLOSED',
             'claim_limit':'601x1201 numerical pilot ONLY: no rotating equilibrium virial certification, no mesh convergence, branch stability, original 7 EOS physical acceptance, or NICER/XMM X-PSI photon Bayes.'}
    def persist():
        a.out.write_text(json.dumps(receipt,sort_keys=True,indent=2,allow_nan=False)+'\n')
    persist()
    for label,rho in [('low',LOW_RHO),('high',HIGH_RHO)]:
        journal=a.out.with_name(a.out.stem+'_'+label+'.jsonl')
        if journal.exists():
            raise FileExistsError('REFUSE_TO_OVERWRITE_F128_RAW_NATIVE_C_JOURNAL')
        probe=NativeProbe(a.binary,a.eos,rho,journal)
        result=solve_fixed_j(probe)
        result['journal_SHA256']=sha_bytes(journal.read_bytes())
        receipt['stars'][label]=result
        persist()
    lo=receipt['stars']['low'];hi=receipt['stars']['high']
    if lo['status']==hi['status']=='ACCEPTED_LOOSE_SAME_J_ROOT':
        receipt['same_target_J_comparison']={'delta_M_msun':hi['star']['M_msun']-lo['star']['M_msun'],
        'delta_R_eq_cm':(hi['star']['R_eq_km']-lo['star']['R_eq_km'])*1e5,
        'relative_density_gap':(HIGH_RHO-LOW_RHO)/LOW_RHO,
        'both_loose_inner_converged':True,'both_loose_J_residuals_accepted':True,
        'physical_certification':False}
        receipt['status']='BOTH_REAL_C_LOOSE_J_CONTROL_ROOTS_COMPUTED_NOT_PHYSICALLY_CERTIFIED'
    persist()
    print('F128_RESULT',receipt['status'],json.dumps(receipt.get('same_target_J_comparison'),sort_keys=True))
    if receipt['status']=='PARTIAL_FAIL_CLOSED':
        raise SystemExit(2)

if __name__=='__main__':main()

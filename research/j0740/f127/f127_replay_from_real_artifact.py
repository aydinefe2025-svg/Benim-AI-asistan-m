#!/usr/bin/env python3
"""Recover audited F127 real C A/B stars from the original fail-closed Actions artifact.

The original CI failed because its parser expected a single diagnostic line,
whereas instrumentation inside the solver loop records each iteration.
This script does not run a new star or infer a fixed-J root for variant B.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path

F127_ZIP_SHA = 'dfc2d9161e7db0536d16bf9f1298b41b812da8c0b3ac5cda355d6911eaf48cb9'
F124_ZIP_SHA = 'd82d43d5b72d9d2f7e7ee90f4163bf308905ec2dfca9d5c709885976e42fb196'
F123_ZIP_SHA = '923e0fb508ecb7a4733ed5cc3da62834ba4caf4b4e4ed396ad29e229874d281f'
F99_EOS_SHA = 'c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
TARGET_J = 4.8245626795750385e48
TARGET_RHO = 2622286765625000
TARGET_RATIO = 0.990179463315
GRID = '3001x6001'
NAMES = ('a_check_initialized', 'a_check_initialized_accuracy_1e7')
DIAG = re.compile(r'^F127_SPIN_FINAL_DIFFERENCE (?P<dif>\S+) ITERATIONS (?P<iteration>\d+) ACCURACY (?P<accuracy>\S+) ACHECK (?P<check>-?\d+)$')


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require_sha(raw: bytes, expected: str, description: str) -> None:
    if digest(raw) != expected:
        raise ValueError(description + '_SHA256_MISMATCH')


def verify_zip(raw: bytes, description: str):
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        if archive.testzip() is not None:
            raise ValueError(description + '_ZIP_CRC_FAILURE')
        return archive
    except zipfile.BadZipFile as exc:
        raise ValueError(description + '_ZIP_CORRUPT') from exc


def parse_stdout(stdout: str) -> dict:
    rows = []
    for line in stdout.splitlines():
        cols = line.split()
        if len(cols) != 5:
            continue
        try:
            values = [float(x) for x in cols]
        except ValueError:
            continue
        if not all(math.isfinite(x) and x > 0 for x in values):
            raise ValueError('NONPHYSICAL_FIVE_COLUMN_STAR')
        rows.append(values)
    if len(rows) != 1:
        raise ValueError('EXPECTED_ONE_REAL_NATIVE_C_STAR')
    e15, mass, radius, frequency, J = rows[0]
    if abs(e15*1e15 / TARGET_RHO - 1) > 1e-9:
        raise ValueError('REAL_C_CENTER_DENSITY_CHANGED')
    return {'rho_g_cm3':TARGET_RHO,'r_ratio_C_input':TARGET_RATIO,
            'M_msun':mass,'R_eq_km':radius,'f_hz':frequency,'J_cgs':J,
            'J_signed_relative_error':J/TARGET_J-1,
            'J_relative_error':abs(J/TARGET_J-1), 'real_native_RNS_C':True}


def parse_trace(stderr: str, expected_accuracy: float) -> dict:
    matches = []
    for line in stderr.splitlines():
        m = DIAG.fullmatch(line.strip())
        if m:
            dif, it, tol, a_check = float(m['dif']), int(m['iteration']), float(m['accuracy']), int(m['check'])
            if not (math.isfinite(dif) and 0 <= dif < 1 and math.isfinite(tol) and tol > 0 and a_check == 0):
                raise ValueError('INVALID_INNER_ITERATION_DIAGNOSTIC')
            if not math.isclose(tol, expected_accuracy, rel_tol=1e-14, abs_tol=0):
                raise ValueError('INCORRECT_SOURCE_STOPPING_ACCURACY')
            matches.append({'relative_radius_change':dif,'iteration':it,'accuracy':tol,'a_check':a_check})
        elif 'F127_SPIN_FINAL_DIFFERENCE' in line:
            raise ValueError('MALFORMED_SOURCE_INSTRUMENTATION')
    if len(matches) < 4:
        raise ValueError('MISSING_MULTIPLE_REAL_SPIN_ITERATIONS')
    sequences = []
    for value in matches:
        if value['iteration'] == 1:
            sequences.append([])
        if not sequences or value['iteration'] != len(sequences[-1])+1:
            raise ValueError('INCOMPLETE_OR_UNORDERED_ITERATION_TRACE')
        sequences[-1].append(value)
    if len(sequences) != 2 or any(len(x) < 2 for x in sequences):
        raise ValueError('EXPECTED_INITIAL_SPHERE_AND_FINAL_ROTATING_SPIN_CALL')
    for seq in sequences:
        last = seq[-1]
        if last['relative_radius_change'] > expected_accuracy:
            raise ValueError('UNCONVERGED_SPIN_FINAL_ITERATE')
    return {'total_diagnostic_rows':len(matches),
            'calls':[{'spin_iterations':len(seq),
                      'terminal_dif':seq[-1]['relative_radius_change'],
                      'criterion':seq[-1]['accuracy'],
                      'passed_radius_step_stop':True} for seq in sequences],
            'final_rotating_star':{'spin_iterations':len(sequences[-1]),
                                  'terminal_dif':sequences[-1][-1]['relative_radius_change'],
                                  'criterion':expected_accuracy},
            'raw_iteration_trace':matches}


def replay(artifact_raw: bytes, eos_raw: bytes) -> dict:
    require_sha(artifact_raw, F127_ZIP_SHA, 'F127_ORIGINAL_FAILED_CI')
    require_sha(eos_raw, F99_EOS_SHA, 'F99_DERIVED_NOT_SEVEN_ORIGINAL_EOS')
    with verify_zip(artifact_raw, 'F127') as outer:
        f124 = outer.read('F124/F124_artifact.zip')
        require_sha(f124,F124_ZIP_SHA,'NESTED_ORIGINAL_F124')
        with verify_zip(f124,'F124') as old:
            source = json.loads(old.read('F124/F124_LOWER_HALF_BISECTION.json'))
            f123 = old.read('F123/F123_artifact.zip')
            require_sha(f123,F123_ZIP_SHA,'NESTED_ORIGINAL_F123')
            if not (source['status']=='F124_LOWER_HALF_BISECTION_COMPLETE'
                    and source['EOS_sha256']==F99_EOS_SHA
                    and source['mesh']==GRID and source['native_C_call_count']==1):
                raise ValueError('F124_BASELINE_SCIENCE_SOURCE_DRIFT')
            reference=source['fixed_J_solutions'][0]
            if (reference['rho_g_cm3']!=TARGET_RHO or
                reference['selected_r_ratio']!=TARGET_RATIO or
                reference['J_relative_error']>1e-9):
                raise ValueError('F124_ORIGINAL_FIXED_J_ROOT_CHANGED')
        prior = json.loads(outer.read('F127/F127_SOURCE_AB_COMPARISON.json'))
        if not (prior['status']=='PARTIAL_FAIL_CLOSED'
                and prior['eos_sha256']==F99_EOS_SHA and prior['source_F124_zip_sha256']==F124_ZIP_SHA
                and prior['same_rho_g_cm3']==TARGET_RHO and prior['same_r_ratio_input']==TARGET_RATIO):
            raise ValueError('F127_ORIGINAL_CI_REJECTION_NOT_EXPECTED')
        out = {}
        for name,accuracy in zip(NAMES,(1e-4,1e-7)):
            prefix='F127/F127_SOURCE_AB_COMPARISON_'+name
            sout=outer.read(prefix+'.stdout.txt')
            serr=outer.read(prefix+'.stderr.txt')
            if digest(sout)!=prior['results'][name]['stdout_sha256'] or digest(serr)!=prior['results'][name]['stderr_sha256']:
                raise ValueError('ORIGINAL_RAW_C_STREAM_CHECKSUM_CHANGED')
            if (prior['results'][name]['status']!='FAIL_CLOSED'
                    or prior['results'][name]['error']!="ValueError('SOURCE_INSTRUMENTATION_MISSING')"):
                raise ValueError('UNEXPECTED_ORIGINAL_CI_FAILURE_MODE')
            star=parse_stdout(sout.decode('utf-8'))
            trace=parse_trace(serr.decode('utf-8'),accuracy)
            star.update({'original_failed_CI_has_real_C_stdout':True,
                         'variant':name,'binary_sha256':prior['results'][name]['binary_sha256'],
                         'raw_stdout_sha256':digest(sout),'raw_stderr_sha256':digest(serr),
                         'spin_trace':trace})
            out[name]=star
    a=out[NAMES[0]];b=out[NAMES[1]]
    if any(a[key]!=reference[oldkey] for key,oldkey in (('M_msun','M_msun'),('R_eq_km','R_eq_km'),('f_hz','f_hz'),('J_cgs','J_cgs'))):
        raise ValueError('INITIALIZED_DEFAULT_DISAGREES_WITH_PREVIOUS_ORIGINAL_F124')
    if not(a['J_relative_error']<1e-9 and b['J_relative_error']>3e-5):
        raise ValueError('A_B_ANGULAR_MOMENTUM_CLASSIFICATION_CHANGED')
    jump=reference['M_msun']-reference['baseline_low_M_msun']
    delta=b['M_msun']-a['M_msun']
    return {'schema':'J0740_F127_CACHED_NATIVE_C_AB_RECOVERY_WITH_FULL_ITERATION_TRACE_V1',
            'status':'TWO_REAL_C_STARS_RECOVERED_FROM_ORIGINAL_FAIL_CLOSED_ARTIFACT_NO_NEW_NATIVE_RUN',
            'source_artifact_zip_sha256':F127_ZIP_SHA,
            'nested_F124_zip_sha256':F124_ZIP_SHA,'EOS_sha256':F99_EOS_SHA,
            'RNS_upstream_commit':'97e85d325a33e37f702306414533f6cd77812477',
            'mesh':GRID,'rho_g_cm3':TARGET_RHO,'input_r_ratio':TARGET_RATIO,
            'baseline_original_F124_equivalent_to_initialized_A_at_print_precision':True,
            'variants':out,
            'observed':{'B_minus_A_mass_Msun':delta,
                        'B_minus_A_equatorial_radius_cm':(b['R_eq_km']-a['R_eq_km'])*1e5,
                        'B_minus_A_frequency_hz':b['f_hz']-a['f_hz'],
                        'B_over_A_J_minus_one':b['J_cgs']/a['J_cgs']-1,
                        'tight_B_J_relative_error':b['J_relative_error'],
                        'original_F124_mass_jump_Msun':jump,
                        'AB_mass_difference_to_previous_sample_jump_ratio':abs(delta/jump)},
            'science_limits':('Convergence is only in last radius-step scalar dif; no virial/GR residual was checked. '
                              'The B-star does NOT match the A-star angular momentum, so their mass difference is NOT a fixed-J mass change. '
                              'Initialization alone reproduced the old star for this case, not a blanket proof of innocuousness. '
                              'A large 1e-4→1e-7 stopping-criterion sensitivity is established in real RNS C; '
                              'this does not by itself demonstrate the F124 rho-jump is a numerical artifact. '
                              'F99 is derived and separate from seven original EOS, and no X-PSI photon Bayes was run.')}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--f127',type=Path,required=True)
    p.add_argument('--eos',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    result=replay(args.f127.read_bytes(),args.eos.read_bytes())
    args.out.parent.mkdir(parents=True,exist_ok=True)
    if args.out.exists():raise FileExistsError('NEVER_OVERWRITE_F127_REPLAY_RECEIPT')
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
    print('F127_FULL_C_REPLAY_PASS',json.dumps({'status':result['status'],'observed':result['observed'],
          'iteration_counts':{k:v['spin_trace']['final_rotating_star']['spin_iterations'] for k,v in result['variants'].items()}},sort_keys=True),flush=True)

if __name__=='__main__':main()

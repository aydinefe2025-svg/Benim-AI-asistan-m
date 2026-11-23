#!/usr/bin/env python3
"""Recover real F131 native RNS C stars without rerunning: fix spherical omega=0 parser only.

Source artifact is an immutable failed-Actions run; native C outputs are verified
against F129 original stdout byte values and source-nested SHA pins, not invented.
"""
from __future__ import annotations
import argparse,hashlib,io,json,zipfile
from pathlib import Path
from f131_field_residual import (F129_SHA,EOS_SHA,RHO,sha,pin_f129_reference,
                                 parse_f131_output,compare_to_F129)

ORIGINAL_F131_SHA='17adc3695a1fb5a26f98e1cae9db9b06658feebcf5b6326fc69ce4b88f3c4412'

def replay_original_real_C(archive:bytes)->dict:
    if sha(archive)!=ORIGINAL_F131_SHA:raise ValueError('F131_ORIGINAL_C_SHA_DRIFT')
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if z.testzip() is not None:raise ValueError('F131_ORIGINAL_C_BAD_CRC')
        f129=z.read('F129_original_native_C.zip')
        if sha(f129)!=F129_SHA:raise ValueError('NESTED_F129_SOURCE_SHA_MISMATCH')
        refs=pin_f129_reference(f129)
        eos=z.read('m99.rns')
        if sha(eos)!=EOS_SHA:raise ValueError('NESTED_F99_EOS_SHA_MISMATCH')
        failed=json.loads(z.read('F131_NATIVE_METRIC_FIELD_FIXEDPOINT.json'))
        if (failed.get('status')!='FAIL_CLOSED_UNTIL_TWO_TRUE_C_RUNS'
            or failed.get('binary_sha256')!=z.read('F131_NATIVE_C_BINARY_SHA256.txt').decode().split()[0]):
            raise ValueError('F131_ORIGINAL_RUN_REPLAY_STATE_INVALID')
        stars={}
        for label,rho in RHO.items():
            prefix='F131_NATIVE_METRIC_FIELD_FIXEDPOINT_'+label
            stdout=z.read(prefix+'.stdout.txt');stderr=z.read(prefix+'.stderr.txt')
            if sha(stdout)!=failed['stars'][label]['stdout_sha256'] or sha(stderr)!=failed['stars'][label]['stderr_sha256']:
                raise ValueError('F131_RAW_OUTPUT_SHA_TAMPER_'+label)
            previous=failed['stars'][label]
            if (previous['status']!='FAIL_CLOSED' or 'BAD_F131_FIELD_VALUES' not in previous['error']):
                raise ValueError('F131_FAILED_SOURCE_REASON_UNEXPECTED')
            star=parse_f131_output(stdout.decode(),stderr.decode(),rho)
            compare_to_F129(star,refs[label])
            with zipfile.ZipFile(io.BytesIO(f129)) as reference:
                old=reference.read('F129_REAL_NATIVE_BARYON_MASS_'+label+'.stdout.txt').decode()
                if stdout.decode().splitlines()[-1]!=old.splitlines()[-1]:
                    raise ValueError('NATIVE_C_STAR_OUTPUT_WITNESS_NOT_EQUAL_'+label)
            stars[label]={'status':'REAL_ORIGINAL_RNS_C_STAR_RECOVERED','star':star,
                          'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr),
                          'original_first_parser_error':previous['error']}
        return {'schema':'J0740_F131_IMMUTABLE_NATIVE_C_THREE_GREEN_METRIC_POTENTIALS_REPLAY_V1',
                'status':'TWO_ORIGINAL_REAL_RNS_C_STARS_VALIDATED_NO_NEW_NATIVE_CALL',
                'original_F131_actions_artifact_sha256':ORIGINAL_F131_SHA,
                'nested_F129_sha256':F129_SHA,'derived_EOS_sha256':EOS_SHA,
                'field_probe_definition':'maximum absolute undamped Green iteration correction divided by maximum absolute old metric potential on same grid; NOT GRV2/GRV3',
                'stars':stars,'reference_invalid_run_state_explained':'two C stars computed; Python parser incorrectly rejected zero omega scale in spherical initialization',
                'limitations':'No independent Einstein-equation PDE or GRV2/3 virial residual. No mesh convergence, original seven EOS physical acceptance or photon-native NICER/XMM Bayes.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--original',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError('REFUSE_OVERWRITE_REPLAY_RECEIPT')
    d=replay_original_real_C(a.original.read_bytes())
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(d,indent=2,sort_keys=True,allow_nan=False)+'\n')
    for name,r in d['stars'].items():
        print('F131_RECOVERED_TRUE_C_METRIC',name,json.dumps(r['star']['metric_green_fixedpoint_residual']['last'],sort_keys=True),flush=True)
    print('F131_ORIGINAL_C_REPLAY_SUCCESS',d['status'],flush=True)

if __name__=='__main__':main()

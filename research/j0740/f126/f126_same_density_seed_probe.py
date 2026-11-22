#!/usr/bin/env python3
"""F126: one new native RNS C seed at *exactly* the F124 high-root density.

Reuse F124 verified real high-J root; compare ONE low-neighbor-ratio cold start.
Do not claim two roots if only one seed fails or is off target J.
"""
from __future__ import annotations
import argparse,hashlib,json,math,subprocess,zipfile
from pathlib import Path

F124_SHA='d82d43d5b72d9d2f7e7ee90f4163bf308905ec2dfca9d5c709885976e42fb196'
F123_SHA='923e0fb508ecb7a4733ed5cc3da62834ba4caf4b4e4ed396ad29e229874d281f'
EOS_SHA='c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
TARGET_J=4.8245626795750385e48
RHO=2622286765625000
LOW_SEED_RATIO=0.990178320198
HIGH_ROOT_RATIO=0.990179463315
STRICT_J_REL=1e-9
TIMEOUT=600

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def preflight(f124:bytes,eos:bytes):
    if sha(f124)!=F124_SHA:raise ValueError('F124_ZIP_DIGEST_CHANGED')
    if sha(eos)!=EOS_SHA:raise ValueError('F99_EOS_DIGEST_CHANGED')
    with zipfile.ZipFile(__import__('io').BytesIO(f124)) as a:
        if a.testzip() is not None:raise ValueError('F124_ARCHIVE_CRC_FAIL')
        result=json.loads(a.read('F124/F124_LOWER_HALF_BISECTION.json'))
        journal=a.read('F124/F124_LOWER_HALF_BISECTION.jsonl')
        f123=a.read('F123/F123_artifact.zip')
    if sha(f123)!=F123_SHA:raise ValueError('NESTED_F123_DIGEST_CHANGED')
    if sha(journal)!=result.get('raw_journal_sha256'):raise ValueError('F124_RAW_C_JOURNAL_CHANGED')
    rows=[json.loads(s) for s in journal.decode().splitlines() if s.strip()]
    roots=result.get('fixed_J_solutions',[])
    if result.get('status')!='F124_LOWER_HALF_BISECTION_COMPLETE' or result.get('EOS_sha256')!=EOS_SHA or result.get('mesh')!='3001x6001' or result.get('native_C_call_count')!=1 or len(rows)!=len(roots)!=1:
        raise ValueError('F124_NOT_SOURCE_PINNED')
    root=roots[0];raw=rows[0]
    if (root.get('rho_g_cm3')!=RHO or root.get('selected_r_ratio')!=HIGH_ROOT_RATIO or
        root.get('J_relative_error',1)>STRICT_J_REL or raw.get('real_native_RNS_C') is not True or
        any(root.get(x)!=raw.get(y) for x,y in [('rho_g_cm3','rho_g_cm3'),('selected_r_ratio','r_ratio_C_input'),('M_msun','M_msun'),('J_relative_error','J_relative_error')])):
        raise ValueError('F124_HIGH_FIXEDJ_ROOT_NOT_AUTHENTIC')
    return root

def parse(stdout:str):
    rows=[]
    for line in stdout.splitlines():
        p=line.split()
        if len(p)!=5:continue
        try:a=[float(x) for x in p]
        except ValueError:continue
        if all(math.isfinite(x) and x>0 for x in a):rows.append(a)
    if len(rows)!=1:raise ValueError('RNS_C_PRINT_NOT_UNIQUE')
    rho15,mass,r,spin,j=rows[0]
    if abs(rho15*1e15/RHO-1)>1e-9:raise ValueError('NATIVE_C_RHO_MISMATCH')
    return {'rho_g_cm3':RHO,'r_ratio_input':LOW_SEED_RATIO,'M_msun':mass,'R_eq_km':r,'spin_hz':spin,
            'J_cgs':j,'J_signed_relative_error':j/TARGET_J-1,'J_relative_error':abs(j/TARGET_J-1)}

def classify(low:dict,high:dict):
    if low['J_relative_error']>STRICT_J_REL:return 'OFF_TARGET_J_SINGLE_LOW_SEED_INCONCLUSIVE'
    if abs(low['M_msun']-high['M_msun'])>1e-6:return 'TWO_DISTINCT_J_MATCHED_NUMERICAL_CANDIDATES_UNCERTIFIED'
    return 'J_MATCHED_LOW_SEED_SAME_MASS_SINGLE_SEED_INCONCLUSIVE'

def run(f124_path:Path,eos:Path,rns:Path,out:Path):
    baseline=preflight(f124_path.read_bytes(),eos.read_bytes())
    if not rns.is_file():raise FileNotFoundError('PINNED_RNS_NATIVE_C_BINARY_MISSING')
    out.parent.mkdir(parents=True,exist_ok=True)
    journal=out.with_suffix('.jsonl');stdout_file=out.with_suffix('.native_stdout.txt');stderr_file=out.with_suffix('.native_stderr.txt')
    if any(p.exists() for p in (out,journal,stdout_file,stderr_file)):
        raise FileExistsError('NEVER_OVERWRITE_F126_EVIDENCE')
    cmd=[str(rns.resolve()),'-f',str(eos),'-e',f'{float(RHO):.14e}','-r',f'{LOW_SEED_RATIO:.12f}']
    status='NATIVE_C_NOT_COMPLETED';error=None;native=None;stdout='';stderr=''
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=TIMEOUT,check=False)
        stdout=p.stdout;stderr=p.stderr
        if p.returncode!=0:raise RuntimeError('NATIVE_C_NONZERO_EXIT_'+str(p.returncode))
        native=parse(stdout)
        status=classify(native,baseline)
    except subprocess.TimeoutExpired as e:
        error='NATIVE_C_TIMEOUT_600_SECONDS'
        stdout=e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else (e.stdout or '')
        stderr=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else (e.stderr or '')
    except Exception as e:error=repr(e)
    stdout_file.write_text(stdout);stderr_file.write_text(stderr)
    receipt={'schema':'J0740_F126_ONE_SAME_DENSITY_LOW_SEED_RNS_C_V1',
             'source_F124_SHA256':F124_SHA,'source_F99_EOS_SHA256':EOS_SHA,'rho_g_cm3':RHO,
             'old_confirmed_high_fixedJ_baseline':baseline,'new_low_seed_attempt':native,
             'native_C_evaluations_attempted':1,'native_C_evaluations_completed':int(native is not None),
             'status':status,'error':error,'stdout_sha256':sha(stdout.encode()),'stderr_sha256':sha(stderr.encode()),
             'scientific_limits':'At most one new cold-start seed, only printed M/R/f/J. J-target match alone does not prove a second equilibrium: virial residual, baryon mass, mesh continuation, branch identity, and photon Bayes remain untested.'}
    with journal.open('x') as f:f.write(json.dumps(receipt,sort_keys=True,allow_nan=False)+'\n')
    out.write_text(json.dumps(receipt,sort_keys=True,indent=2,allow_nan=False)+'\n')
    print('F126_NATIVE_ONE_SEED_RESULT',json.dumps({'status':status,'error':error,'new_low_seed_attempt':native},sort_keys=True),flush=True)
    if error:raise SystemExit(2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--f124',type=Path,required=True);p.add_argument('--eos',type=Path,required=True);p.add_argument('--rns',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.f124,a.eos,a.rns,a.out)

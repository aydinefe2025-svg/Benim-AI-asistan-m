#!/usr/bin/env python3
"""F129: independently measure native RNS baryonic mass at two already verified 1e-9 fixed-J stars.

Uses a *separately derived F99 EOS*, not the seven published nuclear EOSs.
Baryonic mass is an RNS output-dependent diagnostic, NOT stability/evidence certification.
"""
from __future__ import annotations
import argparse,hashlib,io,json,math,subprocess,zipfile
from pathlib import Path

ULTRA_SHA='0302770626ff730657208226e2923a5ed655e8ae39e1235580f67e9180cf9f77'
F806_SHA='0570e05e0493847aefa5c9efc045ec9e0c1c7f5d5487ff6869a6d2f957aa99ad'
EOS_SHA='c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
RNS_SHA_COMMIT='97e85d325a33e37f702306414533f6cd77812477'
TARGET_J=4.8245626795750385e48
INNER_STOP=1e-9
J_TOL=1e-9
RHO={'low':2622286757812500,'high':2622286761718750}
CALL_TIMEOUT=240


def sha(b:bytes)->str:
    return hashlib.sha256(b).hexdigest()


def patch_native_mass0(source:str)->str:
    """Change *only* RNS output line, exposing existing star.Mass_0 without changing field equations."""
    old_fmt='printf("%g \\t %4.3f \\t %4.2f \\t %4.1f \\n",'
    new_fmt='printf("%.12e \\t %.12e \\t %.12e \\t %.12e \\t %.12e \\t %.12e \\n",'
    old_args='star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI));'
    new_args='star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI), star.ang_mom, star.Mass_0/MSUN);'
    if source.count(old_fmt)!=1 or source.count(old_args)!=1 or 'star.Mass_0/MSUN);' in source:
        raise ValueError('RNS_PRINT_SOURCE_DRIFT')
    return source.replace(old_fmt,new_fmt,1).replace(old_args,new_args,1)


def load_ultra_reference(path:Path)->dict:
    raw=path.read_bytes()
    if sha(raw)!=ULTRA_SHA:raise ValueError('F128_ULTRATIGHT_SOURCE_SHA_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if z.testzip() is not None:raise ValueError('F128_ULTRATIGHT_SOURCE_CRC_FAILURE')
        x=json.loads(z.read('F128/F128_ULTRATIGHT_INNER_SAME_J_CONTROL.json'))
        f806=z.read('F806/F806_real_C_artifact.zip')
        if sha(f806)!=F806_SHA:raise ValueError('NESTED_F806_SHA_MISMATCH')
        if zipfile.ZipFile(io.BytesIO(f806)).testzip() is not None:raise ValueError('NESTED_F806_CRC_FAILURE')
        for label in ('low','high'):
            rawjournal=z.read(f'F128/F128_ULTRATIGHT_INNER_SAME_J_CONTROL_{label}.jsonl')
            if sha(rawjournal)!=x['stars'][label]['journal_SHA256']:
                raise ValueError('F128_ULTRATIGHT_JOURNAL_SHA_MISMATCH')
    if (x.get('status')!='BOTH_REAL_C_ULTRATIGHT_J_CONTROL_ROOTS_COMPUTED_NOT_PHYSICALLY_CERTIFIED'
        or x.get('eos_sha256')!=EOS_SHA or x.get('original_RNS_commit')!=RNS_SHA_COMMIT
        or x.get('mesh')!='601x1201' or x.get('target_J_cgs')!=TARGET_J
        or x.get('inner_radius_iteration_tolerance')!=INNER_STOP):
        raise ValueError('F128_ULTRATIGHT_ACCEPTANCE_INVALID')
    roots={}
    for label,rho in RHO.items():
        item=x['stars'][label]
        star=item['star']
        if (item['status']!='ACCEPTED_ULTRATIGHT_SAME_J_ROOT'
            or star['rho_g_cm3']!=rho or star['J_relative_error']>J_TOL
            or star['spin_last_dif']>INNER_STOP or star['spin_inner_accuracy']!=INNER_STOP):
            raise ValueError('F128_ULTRATIGHT_STAR_INVALID')
        roots[label]=star
    return roots


def parse_baryon_star(stdout:str,stderr:str,rho:int,ratio:float)->dict:
    found=[]
    for line in stdout.splitlines():
        cols=line.split()
        if len(cols)!=6:continue
        try:values=[float(c) for c in cols]
        except ValueError:continue
        if not all(math.isfinite(v) and v>0 for v in values):
            raise ValueError('NATIVE_C_SIX_FIELD_NONFINITE_NONPOSITIVE')
        found.append(values)
    if len(found)!=1:raise ValueError('NATIVE_C_EXACTLY_ONE_SIX_FIELD_STAR_REQUIRED')
    rho_print,M,R,f,J,M0=found[0]
    if abs(rho_print*1e15/rho-1.0)>1e-9:
        raise ValueError('NATIVE_C_RHO_MISMATCH')
    rows=[]
    for line in stderr.splitlines():
        if not line.startswith('F127_SPIN_FINAL_DIFFERENCE'):continue
        a=line.split()
        if len(a)!=8 or [a[0],a[2],a[4],a[6]]!=['F127_SPIN_FINAL_DIFFERENCE','ITERATIONS','ACCURACY','ACHECK']:
            raise ValueError('NATIVE_C_DIAG_MALFORMED')
        try:rows.append((float(a[1]),int(a[3]),float(a[5]),int(a[7])))
        except Exception as e:raise ValueError('NATIVE_C_DIAG_BAD_VALUES') from e
    if not rows:raise ValueError('NATIVE_C_DIAG_MISSING')
    dif,n,tol,check=rows[-1]
    if (not math.isfinite(dif) or n<2 or check!=0 or dif<0 or dif>INNER_STOP
            or tol!=INNER_STOP):
        raise ValueError('NATIVE_C_INNER_NOT_CONVERGED')
    deltaJ=abs(J/TARGET_J-1)
    if deltaJ>J_TOL:raise ValueError('NATIVE_C_NOT_SAME_J')
    return {'rho_g_cm3':rho,'r_ratio':ratio,'M_msun':M,'M_baryonic_msun':M0,
            'R_eq_km':R,'f_hz':f,'J_cgs':J,'J_relative_error':deltaJ,
            'last_spin_diff':dif,'spin_iterations':n,'spin_accuracy':tol,
            'binding_mass_proxy_msun':M0-M,'mass0_provenance':'RNS mass_radius Mass_0; F99 n0 calibration NOT independently certified'}


def summarize_pair(a:dict,b:dict)->dict:
    for obj in (a,b):
        for k in ('M_msun','M_baryonic_msun','J_relative_error'):
            if k not in obj or not math.isfinite(obj[k]):raise ValueError('STAR_MISSING_NUMERIC_FIELD_'+k)
        if obj['M_msun']<=0 or obj['M_baryonic_msun']<=0 or obj['J_relative_error']>J_TOL:
            raise ValueError('STAR_UNACCEPTED')
    return {'delta_M_gravitational_msun':b['M_msun']-a['M_msun'],
            'delta_M_baryonic_msun':b['M_baryonic_msun']-a['M_baryonic_msun'],
            'low_binding_mass_proxy_msun':a['M_baryonic_msun']-a['M_msun'],
            'high_binding_mass_proxy_msun':b['M_baryonic_msun']-b['M_msun'],
            'claim_limit':'Finite difference over two nearby densities only. Neither M0 slope nor delta M alone certifies dynamical stability, virial residual, continuous branch or original-seven-EOS Bayesian evidence.'}


def main():
    p=argparse.ArgumentParser()
    for k in ('ultra-zip','eos','binary','out'):
        p.add_argument('--'+k,type=Path,required=True)
    args=p.parse_args()
    if args.out.exists():raise FileExistsError('REFUSE_OVERWRITE_F129_RECEIPT')
    if sha(args.eos.read_bytes())!=EOS_SHA:raise ValueError('F99_SOURCE_EOS_SHA_MISMATCH')
    refs=load_ultra_reference(args.ultra_zip)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    result={'schema':'J0740_F129_AUTHENTIC_NATIVE_RNS_BARYON_MASS_TWO_ULTRATIGHT_FIXED_J_STARS_V1',
            'status':'FAIL_CLOSED_UNTIL_TWO_NATIVE_C_STARS',
            'F128_ultra_zip_sha256':ULTRA_SHA,'F99_EOS_sha256':EOS_SHA,'upstream_RNS_commit':RNS_SHA_COMMIT,
            'binary_sha256':sha(args.binary.read_bytes()),'mesh':'601x1201','inner_tolerance':INNER_STOP,
            'target_J_cgs':TARGET_J,'source_references':refs,'observed':{},'pair_difference':None}
    def persist():args.out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    persist()
    for label,rho in RHO.items():
        ref=refs[label]; ratio=float(f'{ref["r_ratio"]:.12f}')
        cmd=[str(args.binary.resolve()),'-f',str(args.eos.resolve()),'-e',f'{float(rho):.14e}','-r',f'{ratio:.12f}']
        stdout=stderr='';error=None;star=None
        try:
            c=subprocess.run(cmd,capture_output=True,text=True,timeout=CALL_TIMEOUT,check=False)
            stdout,stderr=c.stdout,c.stderr
            if c.returncode:raise RuntimeError('NATIVE_C_EXIT_'+str(c.returncode))
            star=parse_baryon_star(stdout,stderr,rho,ratio)
            if (abs(star['M_msun']-ref['M_msun'])>2e-8
                or abs(star['R_eq_km']-ref['R_eq_km'])>2e-7
                or abs(star['f_hz']-ref['f_hz'])>1e-5):
                raise ValueError('F129_STAR_WITNESS_CHANGED_AFTER_OUTPUT_ONLY_PATCH')
        except Exception as exc:
            error=repr(exc)
        pfx=args.out.parent/(args.out.stem+'_'+label)
        pfx.with_suffix('.stdout.txt').write_text(stdout)
        pfx.with_suffix('.stderr.txt').write_text(stderr)
        result['observed'][label]={'status':'REAL_C_ACCEPTED' if star is not None and error is None else 'FAIL_CLOSED',
                                   'star':star,'error':error,'command':cmd,'stdout_sha256':sha(stdout.encode()),
                                   'stderr_sha256':sha(stderr.encode())}
        persist()
    if all(v['status']=='REAL_C_ACCEPTED' for v in result['observed'].values()):
        result['pair_difference']=summarize_pair(result['observed']['low']['star'],result['observed']['high']['star'])
        result['status']='TWO_AUTHENTIC_RNS_MASS0_VALUES_MEASURED_DIAGNOSTIC_ONLY'
        persist()
    print('F129_RESULT',json.dumps({'status':result['status'],'pair':result['pair_difference']},sort_keys=True),flush=True)
    if result['status']!='TWO_AUTHENTIC_RNS_MASS0_VALUES_MEASURED_DIAGNOSTIC_ONLY':raise SystemExit(2)

if __name__=='__main__':main()
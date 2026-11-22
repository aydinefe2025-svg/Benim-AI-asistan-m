#!/usr/bin/env python3
"""Source-guarded F127 A/B experiment: initialize RNS a_check, then tighten spin iteration accuracy.

Only modifies a previously uninitialized control and an existing stop threshold,
plus print-only diagnostics. No EOS or Einstein-field-equation changes.
"""
from __future__ import annotations
import argparse,hashlib,io,json,math,subprocess,zipfile
from pathlib import Path

F124_SHA='d82d43d5b72d9d2f7e7ee90f4163bf308905ec2dfca9d5c709885976e42fb196'
F123_SHA='923e0fb508ecb7a4733ed5cc3da62834ba4caf4b4e4ed396ad29e229874d281f'
EOS_SHA='c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
RNS_COMMIT='97e85d325a33e37f702306414533f6cd77812477'
TARGET_RHO=2622286765625000
TARGET_RATIO=0.990179463315
TARGET_J=4.8245626795750385e48
C_TIMEOUT=600


def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def replace_exact(s:str,old:str,new:str,name:str)->str:
    if s.count(old)!=1:raise ValueError('UNEXPECTED_PINNED_RNS_SOURCE_FOR_'+name)
    return s.replace(old,new,1)

def patch_findmodel(s:str,strict:bool)->str:
    if 'int rns(double r_ratio,' not in s:raise ValueError('RNS_SOURCE_FUNCTION_MISSING')
    s=replace_exact(s,'  int a_check;','  int a_check=0;','A_CHECK_INITIALIZATION')
    if strict:
        s=replace_exact(s,'  double accuracy=1e-4;','  double accuracy=1e-7;','ACCURACY_1E7')
    else:
        if s.count('  double accuracy=1e-4;')!=1:raise ValueError('ACCURACY_SOURCE_DRIFT')
    return s

def instrument_equil(s:str)->str:
    old=' }   /* end while */'
    new=(old+'\\n   fprintf(stderr,"F127_SPIN_FINAL_DIFFERENCE %.17e ITERATIONS %d ACCURACY %.17e ACHECK %d\\\\n",'
         'dif,n_of_it,accuracy,a_check);')
    return replace_exact(s,old,new,'SPIN_END_RESIDUAL_PROBE')

def patch_rns_print(s:str)->str:
    return replace_exact(replace_exact(s,
        'printf("%g \\t %4.3f \\t %4.2f \\t %4.1f \\n",',
        'printf("%.12e \\t %.12e \\t %.12e \\t %.12e \\t %.12e \\n",',
        'RNS_STAR_PRINT_SIGNATURE'),
        'star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI));',
        'star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI), star.ang_mom);',
        'RNS_STAR_ANGMOM_PRINT')

def patch_mesh(s:str)->str:
    return replace_exact(s,'HIGHSIZE=-DMDIV=151 -DSDIV=301',
                         'HIGHSIZE=-DMDIV=3001 -DSDIV=6001','RNS_MESH_DIMENSIONS')

def check_f124(f124:bytes,eos:bytes)->dict:
    if sha(f124)!=F124_SHA:raise ValueError('F124_ZIP_SHA_MISMATCH')
    if sha(eos)!=EOS_SHA:raise ValueError('F99_EOS_SHA_MISMATCH')
    with zipfile.ZipFile(io.BytesIO(f124)) as z:
        if z.testzip() is not None:raise ValueError('F124_CRC_MISMATCH')
        old=json.loads(z.read('F124/F124_LOWER_HALF_BISECTION.json'))
        rows=[json.loads(r) for r in z.read('F124/F124_LOWER_HALF_BISECTION.jsonl').decode().splitlines() if r.strip()]
        if sha(z.read('F123/F123_artifact.zip'))!=F123_SHA:raise ValueError('NESTED_F123_SHA_MISMATCH')
    rt=old.get('fixed_J_solutions',[])
    if not old.get('status')=='F124_LOWER_HALF_BISECTION_COMPLETE' or len(rt)!=1 or len(rows)!=1 or old['EOS_sha256']!=EOS_SHA:
        raise ValueError('F124_ROOT_SHAPE_MISMATCH')
    root=rt[0];row=rows[0]
    if root['rho_g_cm3']!=TARGET_RHO or root['selected_r_ratio']!=TARGET_RATIO or root['J_relative_error']>1e-9 or root['M_msun']!=row['M_msun'] or root['J_relative_error']!=row['J_relative_error']:
        raise ValueError('F124_HIGH_ROOT_INVALID')
    return root

def parse_native(stdout:str,stderr:str)->dict:
    stars=[]
    for line in stdout.splitlines():
        try:xs=[float(x) for x in line.split()]
        except ValueError:continue
        if len(xs)==5 and all(math.isfinite(x) and x>0 for x in xs):stars.append(xs)
    if len(stars)!=1:raise ValueError('NATIVE_PRINT_NOT_UNIQUE')
    rho15,mass,radius,spin,J=stars[0]
    if abs(rho15*1e15/TARGET_RHO-1)>1e-9:raise ValueError('NATIVE_DENSITY_MISMATCH')
    diagnostics=[line for line in stderr.splitlines() if 'F127_SPIN_FINAL_DIFFERENCE' in line]
    if not diagnostics:raise ValueError('SOURCE_INSTRUMENTATION_MISSING')
    spin_calls=[]
    for line in diagnostics:
        ds=line.split()
        if len(ds)!=8 or ds[0]!='F127_SPIN_FINAL_DIFFERENCE' or ds[2]!='ITERATIONS' or ds[4]!='ACCURACY' or ds[6]!='ACHECK':
            raise ValueError('MALFORMED_SOURCE_DIAGNOSTIC')
        try:
            rec={'last_radius_relative_change':float(ds[1]),'iterations':int(ds[3]),
                 'accuracy_requested':float(ds[5]),'a_check':int(ds[7])}
        except Exception as exc:
            raise ValueError('MALFORMED_SOURCE_DIAGNOSTIC_VALUES') from exc
        if (not all(map(math.isfinite,[rec['last_radius_relative_change'],rec['accuracy_requested']]))
                or rec['last_radius_relative_change']<0 or rec['accuracy_requested']<=0
                or rec['iterations']<2):
            raise ValueError('INVALID_SOLVER_DIAGNOSTIC')
        if rec['a_check']!=0 or rec['last_radius_relative_change']>rec['accuracy_requested']:
            raise ValueError('RNS_INNER_SPIN_DIVERGED_OR_NOT_CONVERGED')
        spin_calls.append(rec)
    final=spin_calls[-1]
    return {'M_msun':mass,'R_eq_km':radius,'f_hz':spin,'J_cgs':J,'J_relative_error':abs(J/TARGET_J-1),
            'spin_last_radius_relative_change':final['last_radius_relative_change'],
            'spin_iterations':final['iterations'],'spin_accuracy_requested':final['accuracy_requested'],
            'spin_call_count':len(spin_calls),'spin_call_diagnostics':spin_calls,
            'a_check':final['a_check'],'rho_g_cm3':TARGET_RHO,'input_ratio':TARGET_RATIO}

def run(a):
    root=check_f124(a.f124.read_bytes(),a.eos.read_bytes());out=a.out;out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():raise FileExistsError('DO_NOT_OVERWRITE_F127_EVIDENCE')
    results={}
    for variant,exe in [('a_check_initialized',a.baseline),('a_check_initialized_accuracy_1e7',a.tight)]:
        cmd=[str(exe.resolve()),'-f',str(a.eos),'-e',f'{float(TARGET_RHO):.14e}','-r',f'{TARGET_RATIO:.12f}']
        if not exe.is_file():raise FileNotFoundError('MISSING_REAL_C_VARIANT_'+variant)
        textout='';texterr='';star=None;error=None
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=C_TIMEOUT,check=False)
            textout=p.stdout;texterr=p.stderr
            if p.returncode:raise RuntimeError('NATIVE_C_EXIT_'+str(p.returncode))
            star=parse_native(textout,texterr)
        except subprocess.TimeoutExpired as e:
            error='NATIVE_C_TIMEOUT_600S';textout=e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else (e.stdout or '')
            texterr=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else (e.stderr or '')
        except Exception as e:error=repr(e)
        pfx=out.with_name(out.stem+'_'+variant)
        pfx.with_suffix('.stdout.txt').write_text(textout)
        pfx.with_suffix('.stderr.txt').write_text(texterr)
        results[variant]={'status':'REAL_C_COMPLETE' if star else 'FAIL_CLOSED','star':star,'error':error,
                          'stdout_sha256':sha(textout.encode()),'stderr_sha256':sha(texterr.encode()),
                          'binary_sha256':sha(exe.read_bytes())}
        print('F127_NATIVE_VARIANT',variant,results[variant]['status'],results[variant]['star'],error,flush=True)
    a0=results['a_check_initialized']['star'];a1=results['a_check_initialized_accuracy_1e7']['star']
    delta=None if a0 is None or a1 is None else {'delta_M_msun':a1['M_msun']-a0['M_msun'],
             'delta_R_eq_cm':(a1['R_eq_km']-a0['R_eq_km'])*1e5,
             'delta_f_hz':a1['f_hz']-a0['f_hz'],'relative_J_change':a1['J_cgs']/a0['J_cgs']-1}
    receipt={'schema':'J0740_F127_SOURCE_INITIALIZATION_CONVERGENCE_AB_V1','eos_sha256':EOS_SHA,
             'upstream_RNS_commit':RNS_COMMIT,'source_F124_zip_sha256':F124_SHA,'same_rho_g_cm3':TARGET_RHO,
             'same_r_ratio_input':TARGET_RATIO,'mesh':'3001x6001','original_F124_root':root,'results':results,
             'tighter_minus_initialized':delta,'status':'BOTH_NATIVE_A_B_COMPUTED_DIAGNOSTIC_ONLY' if delta is not None else 'PARTIAL_FAIL_CLOSED',
             'claim_limit':'The a_check initialization and 1e-7 radius-difference stop criterion are controlled solver changes, not published original EOS or physical stability proof. Even 1e-7 does NOT certify Einstein-equation virial residuals. No posterior or original seven EOS accepted.'}
    out.write_text(json.dumps(receipt,indent=2,sort_keys=True,allow_nan=False)+'\n')
    if delta is None:raise SystemExit(2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--f124',type=Path,required=True);p.add_argument('--eos',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--tight',type=Path,required=True);p.add_argument('--out',type=Path,required=True);run(p.parse_args())

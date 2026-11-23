#!/usr/bin/env python3
"""F131: RNS C source-guarded Green-iteration metric fixed-point residual diagnostic.

The three reported residuals are max |Green[p](x)-p(x)| for the metric potentials
rho, gamma and omega, divided (for relative global metrics) by max |p(x)|.
This is a fixed-point update residual within RNS, NOT a GRV2/GRV3 virial identity,
local Einstein PDE residual, physical EOS acceptance, or EOS Bayesian evidence.
"""
from __future__ import annotations
import argparse,hashlib,io,json,math,subprocess,zipfile
from pathlib import Path

F129_SHA='6a2f8cfef88242e0354c843408b3055dda3c545ff7abad44df669af670ce69b1'
ULTRA_SHA='0302770626ff730657208226e2923a5ed655e8ae39e1235580f67e9180cf9f77'
EOS_SHA='c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
RNS_COMMIT='97e85d325a33e37f702306414533f6cd77812477'
TARGET_J=4.8245626795750385e48
INNER_STOP=1e-9
RHO={'low':2622286757812500,'high':2622286761718750}
TIMEOUT=240

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def replace_once(source:str,old:str,new:str,gate:str)->str:
    if source.count(old)!=1:raise ValueError('SOURCE_DRIFT_'+gate)
    return source.replace(old,new,1)

def instrument_field_residual(source:str)->str:
    """Only introduce local double accumulators and stderr writes; no equation changes."""
    declaration='''    /* F131: record genuine undamped Green operator fixed-point updates. */
    double f131_drho=0.0, f131_dgama=0.0, f131_domega=0.0;
    double f131_scale_rho=0.0, f131_scale_gama=0.0, f131_scale_omega=0.0;
'''
    source=replace_once(source,'    f2n = dmatrix(1,LMAX+1,1,SDIV);',
                        declaration+'    f2n = dmatrix(1,LMAX+1,1,SDIV);','DECL')
    reset='''  while(dif> accuracy || n_of_it<2) { 
      f131_drho=f131_dgama=f131_domega=0.0;
      f131_scale_rho=f131_scale_gama=f131_scale_omega=0.0;
'''
    source=replace_once(source,'  while(dif> accuracy || n_of_it<2) { ',reset,'LOOP_RESET')
    new_update='''            /* F131 diagnostic: raw Green fixed-point difference, before relaxation.
               Denominator max |old potential| is gathered across the same grid. */
            f131_drho=fmax(f131_drho,fabs(sum_rho-rsm));
            f131_dgama=fmax(f131_dgama,fabs(sum_gama-gsm));
            f131_domega=fmax(f131_domega,fabs(sum_omega-omsm));
            f131_scale_rho=fmax(f131_scale_rho,fabs(rsm));
            f131_scale_gama=fmax(f131_scale_gama,fabs(gsm));
            f131_scale_omega=fmax(f131_scale_omega,fabs(omsm));
            rho[s][m]=rsm + cf*(sum_rho-rsm);
            gama[s][m]=gsm + cf*(sum_gama-gsm);
            omega[s][m]=omsm + cf*(sum_omega-omsm);'''
    old_update='''            rho[s][m]=rsm + cf*(sum_rho-rsm);
            gama[s][m]=gsm + cf*(sum_gama-gsm);
            omega[s][m]=omsm + cf*(sum_omega-omsm);'''
    source=replace_once(source,old_update,new_update,'METRIC_UPDATE')
    # Insert exactly once after *the actual* spin while loop, before existing F127 probe.
    new_end=''' }   /* end while */
    fprintf(stderr,"F131_FIELD_FINAL %.17e %.17e %.17e %.17e %.17e %.17e ITERATIONS %d ACHECK %d\\n",
       f131_drho,f131_dgama,f131_domega,f131_scale_rho,f131_scale_gama,f131_scale_omega,n_of_it,a_check);'''
    source=replace_once(source,' }   /* end while */',new_end,'FINAL_PROBE')
    if source.count('F131_FIELD_FINAL')!=1:raise ValueError('SOURCE_DRIFT_DOUBLE_PROBE')
    return source

def parse_metric_probe(stderr:str)->dict:
    rows=[]
    for line in stderr.splitlines():
        if not line.startswith('F131_FIELD_FINAL'):continue
        xs=line.split()
        if len(xs)!=11 or xs[0]!='F131_FIELD_FINAL' or xs[7]!='ITERATIONS' or xs[9]!='ACHECK':
            raise ValueError('BAD_F131_FIELD_SYNTAX')
        try:
            vals=[float(v) for v in xs[1:7]];n=int(xs[8]);check=int(xs[10])
        except Exception as e:raise ValueError('BAD_F131_FIELD_VALUES') from e
        if not all(math.isfinite(x) and x>=0 for x in vals) or n<2 or check!=0:
            raise ValueError('BAD_F131_FIELD_VALUES')
        # The spherical seed has omega=0 and delta_omega=0, so its relative
        # residual is undefined (0/0); preserve that as null. Nonzero residuals
        # with zero scale remain invalid, and the final rotating call must scale all fields.
        for delta,scale in zip(vals[:3],vals[3:]):
            if scale==0.0 and delta!=0.0:
                raise ValueError('ZERO_FIELD_SCALE_WITH_NONZERO_GREEN_RESIDUAL')
        rel=[delta/scale if scale>0 else None for delta,scale in zip(vals[:3],vals[3:])]
        row={'delta_rho':vals[0],'delta_gama':vals[1],'delta_omega':vals[2],
             'scale_rho':vals[3],'scale_gama':vals[4],'scale_omega':vals[5],
             'rel_delta_rho':rel[0],'rel_delta_gama':rel[1],
             'rel_delta_omega':rel[2],
             'iterations':n,'a_check':check}
        rows.append(row)
    if not rows:raise ValueError('F131_METRIC_PROBE_MISSING')
    if len(rows)!=2:raise ValueError('F131_EXPECTED_TWO_SPIN_CALLS')
    if any(rows[-1]['scale_'+key]<=0 for key in ('rho','gama','omega')):
        raise ValueError('ROTATING_SPIN_FIELD_HAS_ZERO_SCALE')
    return {'spin_calls':rows,'last':rows[-1],
            'largest_global_field_relative_update':max(rows[-1]['rel_delta_rho'],rows[-1]['rel_delta_gama'],rows[-1]['rel_delta_omega'])}

def pin_f129_reference(artifact:bytes)->dict:
    if sha(artifact)!=F129_SHA:raise ValueError('F129_ARTIFACT_SHA_INVALID')
    with zipfile.ZipFile(io.BytesIO(artifact)) as z:
        if z.testzip() is not None:raise ValueError('F129_ZIP_CRC_INVALID')
        x=json.loads(z.read('F129_REAL_NATIVE_BARYON_MASS.json'))
        u=z.read('F128_ULTRATIGHT_SOURCE.zip')
        if sha(u)!=ULTRA_SHA:raise ValueError('F129_NESTED_F128_SHA_INVALID')
        if sha(z.read('m99.rns'))!=EOS_SHA:raise ValueError('F129_EOS_SHA_INVALID')
        if x.get('status')!='TWO_AUTHENTIC_RNS_MASS0_VALUES_MEASURED_DIAGNOSTIC_ONLY' or x.get('mesh')!='601x1201' or x.get('F99_EOS_sha256')!=EOS_SHA or x.get('upstream_RNS_commit')!=RNS_COMMIT or x.get('target_J_cgs')!=TARGET_J or x.get('inner_tolerance')!=INNER_STOP:
            raise ValueError('F129_REFERENCE_METADATA_INVALID')
        refs={}
        for label,rho in RHO.items():
            rr=x['observed'][label];star=rr['star']
            if rr['status']!='REAL_C_ACCEPTED' or star['rho_g_cm3']!=rho or star['J_relative_error']>1e-9 or star['spin_accuracy']!=INNER_STOP:
                raise ValueError('F129_ROOT_NOT_ACCEPTED')
            for channel in ('stdout','stderr'):
                member=f'F129_REAL_NATIVE_BARYON_MASS_{label}.{channel}.txt'
                if sha(z.read(member))!=rr[channel+'_sha256']:
                    raise ValueError('F129_ORIGINAL_C_'+channel.upper()+'_SHA_INVALID')
            refs[label]=star
    return refs

def parse_f131_output(stdout:str,stderr:str,rho:int)->dict:
    stars=[]
    for line in stdout.splitlines():
        try:vals=[float(v) for v in line.split()]
        except ValueError:continue
        if len(vals)==6:
            if not all(math.isfinite(x) and x>0 for x in vals):raise ValueError('F131_NATIVE_STAR_NONFINITE')
            stars.append(vals)
    if len(stars)!=1:raise ValueError('F131_NATIVE_STAR_NOT_UNIQUE')
    row=stars[0]
    if abs(row[0]*1e15/rho-1)>1e-9:raise ValueError('F131_NATIVE_WRONG_DENSITY')
    f127=[]
    for line in stderr.splitlines():
        if line.startswith('F127_SPIN_FINAL_DIFFERENCE'):
            a=line.split()
            if len(a)!=8 or a[0]!='F127_SPIN_FINAL_DIFFERENCE' or a[2]!='ITERATIONS' or a[4]!='ACCURACY' or a[6]!='ACHECK':raise ValueError('F127_DIAGNOSTIC_SYNTAX')
            try:f127.append((float(a[1]),int(a[3]),float(a[5]),int(a[7])))
            except Exception as e:raise ValueError('F127_DIAG_NONNUMERIC') from e
    if len(f127)!=2:raise ValueError('F127_DIAG_SPIN_CALL_COUNT')
    dif,it,tol,ac=f127[-1]
    if not math.isfinite(dif) or not math.isfinite(tol) or dif<0 or dif>INNER_STOP or it<2 or ac!=0 or tol!=INNER_STOP:raise ValueError('F127_INNER_NOT_ACCEPTED')
    metric=parse_metric_probe(stderr)
    if metric['last']['iterations']!=it:raise ValueError('F131_METRIC_WRONG_SPIN_ITERS')
    M,R,f,J,Mb=row[1:]
    if abs(J/TARGET_J-1)>1e-9:raise ValueError('F131_J_MISMATCH')
    return {'rho_g_cm3':rho,'M_msun':M,'R_eq_km':R,'f_hz':f,'J_cgs':J,'M_baryonic_msun':Mb,
            'signed_relative_J_residual':J/TARGET_J-1,'inner_last_dif':dif,'inner_iterations':it,
            'metric_green_fixedpoint_residual':metric,
            'measurement_definition':'undamped max|Green[p]-p|/max|p| over RNS grid for each rho/gama/omega; NOT GRV2 or GRV3'}

def compare_to_F129(star:dict,reference:dict)->None:
    for field,eps in [('M_msun',2e-8),('R_eq_km',2e-7),('f_hz',1e-5),('M_baryonic_msun',2e-8)]:
        if abs(star[field]-reference[field])>eps:raise ValueError('F131_OUTPUT_ONLY_WITNESS_CHANGE_'+field)
    if abs(star['J_cgs']/reference['J_cgs']-1)>1e-8:raise ValueError('F131_OUTPUT_ONLY_WITNESS_CHANGE_J')

def main()->None:
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--eos',type=Path,required=True)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError('F131_DO_NOT_OVERWRITE_RESULT')
    if sha(a.eos.read_bytes())!=EOS_SHA:raise ValueError('F131_EOS_SHA_INVALID')
    refs=pin_f129_reference(a.source.read_bytes())
    a.out.parent.mkdir(parents=True,exist_ok=True)
    record={'schema':'J0740_F131_TRUE_RNS_GREEN_FIXEDPOINT_FIELD_DIAGNOSTIC_V1',
            'status':'FAIL_CLOSED_UNTIL_TWO_TRUE_C_RUNS',
            'source_F129_sha256':F129_SHA,'eos_sha256':EOS_SHA,'upstream_commit':RNS_COMMIT,
            'binary_sha256':sha(a.binary.read_bytes()),'mesh':'601x1201','inner_stop':INNER_STOP,
            'target_J':TARGET_J,'stars':{},'claim_limit':'Relative Green fixed-point residuals of RNS metric potentials only. Not Einstein PDE norm, GRV2/GRV3, physical branch stability, source-7 EOS acceptance or native NICER/XMM Bayes.'}
    def save():a.out.write_text(json.dumps(record,indent=2,sort_keys=True,allow_nan=False)+'\n')
    save()
    for label,rho in RHO.items():
        ratio=refs[label]['r_ratio']
        cmd=[str(a.binary.resolve()),'-f',str(a.eos.resolve()),'-e',f'{rho:.14e}','-r',f'{ratio:.12f}']
        stdout=stderr='';star=None;err=None
        try:
            output=subprocess.run(cmd,capture_output=True,text=True,timeout=TIMEOUT,check=False)
            stdout,stderr=output.stdout,output.stderr
            if output.returncode:raise RuntimeError('F131_NATIVE_C_RETURN_'+str(output.returncode))
            star=parse_f131_output(stdout,stderr,rho)
            compare_to_F129(star,refs[label])
        except subprocess.TimeoutExpired as ex:
            stdout=ex.stdout.decode(errors='replace') if isinstance(ex.stdout,bytes) else (ex.stdout or '')
            stderr=ex.stderr.decode(errors='replace') if isinstance(ex.stderr,bytes) else (ex.stderr or '')
            err='F131_NATIVE_C_TIMEOUT_240_S'
        except Exception as ex:err=repr(ex)
        for typ,content in [('stdout',stdout),('stderr',stderr)]:
            a.out.with_name(a.out.stem+'_'+label+'.'+typ+'.txt').write_text(content)
        record['stars'][label]={'status':'REAL_C_VERIFIED' if star and not err else 'FAIL_CLOSED','star':star,'error':err,
                                'reference':refs[label],'stdout_sha256':sha(stdout.encode()),
                                'stderr_sha256':sha(stderr.encode()),'cmd':cmd}
        save()
        print('F131_REAL_NATIVE_C',label,record['stars'][label]['status'],
              star and star['metric_green_fixedpoint_residual']['last'],err,flush=True)
    if all(v['status']=='REAL_C_VERIFIED' for v in record['stars'].values()):
        record['status']='TWO_PINNED_NATIVE_C_METRIC_FIXEDPOINT_PROBES_MEASURED_DIAGNOSTIC_ONLY'
        save()
    if record['status']!='TWO_PINNED_NATIVE_C_METRIC_FIXEDPOINT_PROBES_MEASURED_DIAGNOSTIC_ONLY':raise SystemExit(2)

if __name__=='__main__':main()

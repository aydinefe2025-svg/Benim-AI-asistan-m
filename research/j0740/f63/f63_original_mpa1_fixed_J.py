"""F63: directly solve source-original MPA1 fixed-J rotating GR stars in pinned RNS C.

This is a *numerical sampled turning-point diagnostic*, NOT certification that
original LALSuite MPA1 is causal/thermodynamically stable. JESTER source contains
negative c_s^2 and a reversed epsilon(P) crust knot. Not a dynamical stability
simulation, source-native photon likelihood, original-seven-EOS Bayes, or F42 EOS.

Input lineage: exact F62 source-original MPA1 rotating reference JSON from the
successful CI artifact. Direct -s anchor J and -r fixed-J models are RNS C calls.
"""
from __future__ import annotations
import argparse, hashlib, json, math, subprocess, sys
from pathlib import Path
from scipy.optimize import brentq
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'rotating_gr'))
from jester_to_rns import from_jester_npz,write_rns

SOURCE_SHA='0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22'
F62_SHA='aca15e711f18ef7646dc5520d8874700475def17f0bcf5e57e354cfcf3cc8f84'
RNS_COMMIT='97e85d325a33e37f702306414533f6cd77812477'
FREQ=346.536369
BASE_EC=1015366308866642.6
DENSITY_E15=(.82,.90,1.01536631,1.12,1.22,1.32,1.42,1.52,1.62,1.72,1.82,1.92,2.02,2.12,2.22,2.32,2.42)
RNS_J_REL_TOL=1e-5


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def patch_output_only(c_source):
    """Exact one-site diagnostics patch; never alter model equations or solvers."""
    old_fmt=r'printf("%g \t %4.3f \t %4.2f \t %4.1f \n",'
    new_fmt=r'printf("%.10g \t %.9f \t %.9f \t %.9f \t %.12e \n",'
    old_args='star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI));'
    new_args='star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI), star.ang_mom);'
    if not (c_source.count(old_fmt)==1 and c_source.count(old_args)==1 and
            new_fmt not in c_source and new_args not in c_source):
        raise ValueError('F63_PINNED_RNS_OUTPUT_C_SIGNATURE_DRIFT')
    patched=c_source.replace(old_fmt,new_fmt).replace(old_args,new_args)
    if patched.count(new_fmt)!=1 or patched.count(new_args)!=1:
        raise ValueError('F63_UNIQUE_OUTPUT_PATCH_FAILED')
    return patched


def parse_star(stdout,ec):
    rows=[]
    for line in stdout.splitlines():
        w=line.split()
        if len(w)!=5:continue
        try:nums=[float(z) for z in w]
        except ValueError:continue
        if all(math.isfinite(z) for z in nums):rows.append(nums)
    if len(rows)!=1:raise ValueError('F63_EXPECT_SINGLE_FIVE_FLOAT_DIRECT_C_ROW')
    e15,m,r,f,j=rows[0]
    if not (math.isclose(e15,ec/1e15,rel_tol=5e-9,abs_tol=1e-8)
            and .5<m<3.5 and 7<r<25 and 0<=f<1800 and 0<=j<1e52):
        raise ValueError('F63_UNPHYSICAL_OR_WRONG_DENSITY_C_ROW')
    return {'ec_g_cm3':float(ec),'mass_msun':m,'radius_eq_km':r,'spin_hz':f,'J_cgs':j}


def c_call(binary,table,ec,*,ratio=None,frequency=None):
    if (ratio is None)==(frequency is None):raise ValueError('F63_EXACTLY_ONE_ROTATION_CONTROL_REQUIRED')
    if not (math.isfinite(ec) and .3e15<ec<2.5e15):raise ValueError('F63_INVALID_CENTRAL_DENSITY')
    path=Path(table)
    if len(('./'+path.name).encode())>=80:raise ValueError('F63_RNS_UNSAFE_FILE_ARGUMENT')
    args=[str(Path(binary).resolve()),'-f','./'+path.name,'-e',f'{ec:.12g}']
    if ratio is not None:
        if not .85<=ratio<=1.0:raise ValueError('F63_INVALID_RNS_AXIS_RATIO')
        args+=['-r',f'{ratio:.10f}']
    else:
        if not 0<=frequency<1200:raise ValueError('F63_INVALID_RNS_SPIN')
        args+=['-s',f'{frequency:.9f}']
    z=subprocess.run(args,cwd=str(path.resolve().parent),capture_output=True,text=True,timeout=130)
    if z.returncode:raise RuntimeError('F63_RNS_C_EXIT_'+str(z.returncode)+': '+z.stderr[-250:])
    row=parse_star(z.stdout,ec)
    row.update({'axis_ratio':ratio,'requested_frequency_hz':frequency})
    return row


def fixed_j_at_density(probe,ec,target_j,seed=.98):
    if not (math.isfinite(target_j) and 1e44<target_j<1e52 and .85<=seed<=1.):
        raise ValueError('F63_TARGET_J_OR_RATIO_INVALID')
    cache={};trace=[]
    def call(r):
        r=round(float(r),10)
        if r not in cache:
            try:
                x=probe(ec,r)
                j=x['J_cgs'];m=x['mass_msun']
                if not all(math.isfinite(z) for z in (j,m)) or j<0:raise ValueError('F63_BAD_C_J')
                cache[r]=(j/target_j-1.,x)
                trace.append({'axis_ratio':r,'relative_J_residual':j/target_j-1.,'mass_msun':m,'status':'DIRECT_C'})
            except (RuntimeError,ValueError,TimeoutError,subprocess.TimeoutExpired) as e:
                cache[r]=None
                trace.append({'axis_ratio':r,'status':'REJECTED','reason':type(e).__name__+': '+str(e)[:180]})
        return cache[r]
    bracket=None
    for span in (.004,.015,.035,.08,.12):
        lo,hi=max(.85,seed-span),min(1.,seed+span)
        a,b=call(lo),call(hi)
        if a is not None and b is not None and a[0]*b[0]<=0:bracket=(lo,hi);break
    if bracket is None:
        pts=sorted(set([.85,.89,.92,.94,.96,.97,.98,.985,.99,.995,.998,1.,seed]))
        good=[(r,call(r)) for r in pts]
        good=[x for x in good if x[1] is not None]
        bracket=next(((a[0],b[0]) for a,b in zip(good,good[1:]) if a[1][0]*b[1][0]<=0),None)
    if bracket is None:raise RuntimeError('F63_FIXED_J_NOT_BRACKETED_AT_EC_%.5g'%ec)
    def fn(r):
        out=call(r)
        if out is None:raise ValueError('F63_FIXED_J_C_FAILURE_INSIDE_BRACKET')
        return out[0]
    rr=brentq(fn,*bracket,xtol=2e-10,rtol=2e-10,maxiter=45)
    final=call(rr)
    if final is None or abs(final[0])>RNS_J_REL_TOL:raise ValueError('F63_FIXED_J_RESIDUAL_EXCEEDS_TOL')
    return {**final[1],'relative_J_residual':final[0],'direct_C_evaluations':len(cache),'trace':trace,
            'status':'DIRECT_C_FIXED_J_NUMERICAL_PASS_NOT_STABILITY_CERTIFICATE'}


def turning_summary(stars):
    q=sorted([x for x in stars if x.get('status','').startswith('DIRECT_C_FIXED_J')],key=lambda z:z['ec_g_cm3'])
    if len(q)<8:return {'status':'INSUFFICIENT_DIRECT_FIXED_J_SEQUENCE','passed':len(q)}
    peak=max(range(len(q)),key=lambda i:q[i]['mass_msun'])
    bracketed=(0<peak<len(q)-1 and q[peak-1]['mass_msun']<q[peak]['mass_msun']
               and q[peak+1]['mass_msun']<q[peak]['mass_msun'])
    return {'status':'SAMPLED_CONSTANT_J_TURNOVER_BRACKETED_NOT_GLOBAL_PROOF' if bracketed else 'UNBRACKETED_FIXED_J_MASS_PEAK',
            'passed':len(q),'peak_mass_msun':q[peak]['mass_msun'],
            'peak_rho_g_cm3':q[peak]['ec_g_cm3'],'peak_spin_hz':q[peak]['spin_hz'],
            'peak_radius_eq_km':q[peak]['radius_eq_km'],
            'neighbor_masses_msun':[q[peak-1]['mass_msun'] if peak else None,q[peak]['mass_msun'],q[peak+1]['mass_msun'] if peak<len(q)-1 else None],
            'neighbor_densities_g_cm3':[q[peak-1]['ec_g_cm3'] if peak else None,q[peak]['ec_g_cm3'],q[peak+1]['ec_g_cm3'] if peak<len(q)-1 else None],
            'global_dynamical_stability':'NOT_ESTABLISHED','original_source_microphysics_causal':'NO'}


def run(npz,f62,binary,out,*,coarse_grid=DENSITY_E15):
    if sha(npz)!=SOURCE_SHA or sha(f62)!=F62_SHA:
        raise ValueError('F63_SOURCE_OR_F62_ORIGINAL_ARTIFACT_SHA_DRIFT')
    previous=json.loads(Path(f62).read_text())
    if not (previous.get('status')=='DIRECT_SOURCE_DERIVED_MPA1_RNS_ROTATING_4_MASSES_TWO_MESHES_PASS_NOT_PHYSICAL_EOS_BAYES'
            and previous.get('original_JESTER_source_MPA1_npz_SHA256')==SOURCE_SHA
            and previous.get('pinned_RNS_commit')==RNS_COMMIT
            and previous.get('source_EOS_physical_acceptance','').startswith('NOT_ESTABLISHED')):
        raise ValueError('F63_ORIGINAL_F62_PHYSICS_LINEAGE_INVALID')
    with np.load(npz,allow_pickle=False) as z:
        p,e,cs2=(np.asarray(z[k],float) for k in ('p','e','cs2'))
    bad=np.flatnonzero(cs2<=0);de=np.flatnonzero(np.diff(e)<=0)
    if len(bad)!=1 or bad[0]!=254 or len(de)!=1:raise ValueError('F63_SOURCE_CRUST_BAD_NODE_DRIFT')
    tab,conv=from_jester_npz(npz,points=196)
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    table=out.parent/'MPA1_F63_sourceoriginal_196knots.rns'
    write_rns(table,tab)
    current_table_sha=sha(table)
    original_f62_table_sha=previous['mesh_runs']['196']['RNS_source_table_sha256']
    # F62 and F63 jobs may emit different last-decimal np.savetxt text bytes
    # for the identical hash-pinned physical source due to libm/NumPy resampling.
    # A byte mismatch is NOT silent acceptance: require independently direct
    # C-RNS anchor M, R, f to reproduce below, record both file hashes.
    byte_identical=(current_table_sha==original_f62_table_sha)
    anchor_ref=previous['mesh_runs']['196']['targets']['2.073']['rotating']['star']
    anchor_ec=float(anchor_ref['central_energy_density_g_cm3'])
    anchor=c_call(binary,table,anchor_ec,frequency=FREQ)
    if (abs(anchor['mass_msun']-anchor_ref['mass_msun'])>5e-6
            or abs(anchor['radius_eq_km']-anchor_ref['radius_eq_km'])>.00005
            or abs(anchor['spin_hz']-anchor_ref['spin_hz_reported'])>.015):
        raise ValueError('F63_DID_NOT_REPRODUCE_F62_C_ANCHOR')
    J=anchor['J_cgs']
    if not 1e44<J<1e52:raise ValueError('F63_TARGET_ANGULAR_MOMENTUM_INVALID')
    report={'schema':'J0740_F63_ORIGINAL_MPA1_PINNED_RNS_CONSTANT_J_V1',
        'F62_table_sha256':original_f62_table_sha,
        'F63_recomputed_196pt_table_sha256':current_table_sha,
        'table_bytes_identical':byte_identical,
        'table_change_assessment':'SOURCE_SHA_LOCKED_AND_DIRECT_F62_C_ANCHOR_NUMERICALLY_REPRODUCED; BYTE_DRIFT_IS_NOT_PHYSICAL_IDENTITY' if not byte_identical else 'BYTE_IDENTICAL',
        'status':'IN_PROGRESS','source_npz_sha256':SOURCE_SHA,'F62_source_json_sha256':F62_SHA,
        'RNS_commit':RNS_COMMIT,'RNS_binary_sha256':sha(binary),'source_196pt_table_sha256':sha(table),
        'RNS_C_printf_J_from':'star.ang_mom','target_J_cgs':J,'anchor_direct_C_at_original_F62_ec':anchor,
        'F62_anchor_original':anchor_ref,'physical_EOS_acceptance':'NOT_ESTABLISHED_SOURCE_NEGATIVE_CS2',
        'source_crust_bad_node':{'index':254,'P_geom_m_minus_2':float(p[254]),'rho_g_cm3':float(e[254]*(299792458.0**2/6.67430e-11)*.001),
                                 'cs2_over_c2':float(cs2[254]),'source_energy_reversal_edge':int(de[0])},
        'original_n_e_over_mavg_proxy_firstlaw_certified':False,
        'RNS_global_angular_momentum_turning_diagnostic':'NOT_RUN',
        'XPSI_photon_source_likelihood':'NOT_RUN','original_7EOS_Bayes':'NOT_RUN',
        'direct_C_constant_J_stars':[],'failed_density_attempts':[]}
    def save():out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    save()
    guess=.98
    def run_node(ec,stage):
        nonlocal guess
        try:
            row=fixed_j_at_density(lambda ec,r:c_call(binary,table,ec,ratio=r),ec,J,seed=guess)
            row['stage']=stage;guess=row['axis_ratio']
            print('F63',round(ec/1e15,5),'M',round(row['mass_msun'],9),'r',round(row['radius_eq_km'],7),'spin',round(row['spin_hz'],4),'Jerr',f'{row["relative_J_residual"]:.1e}',flush=True)
        except (RuntimeError,ValueError) as e:
            row={'status':'DIRECT_C_FIXED_J_FAILED','ec_g_cm3':float(ec),'stage':stage,'failure':type(e).__name__+': '+str(e)[:220]}
            report['failed_density_attempts'].append(row)
            print('F63',round(ec/1e15,5),'FAILED',row['failure'],flush=True)
        report['direct_C_constant_J_stars'].append(row);save()
    for ec15 in coarse_grid:
        ec=anchor_ec if abs(ec15-1.01536631)<1e-6 else ec15*1e15
        run_node(ec,'coarse')
    # Only refine around a peak that actually has both direct C neighbors.
    q=[x for x in report['direct_C_constant_J_stars'] if x['status'].startswith('DIRECT_C_FIXED_J') and 'mass_msun' in x]
    if len(q)>=8:
        peak=max(q,key=lambda x:x['mass_msun'])['ec_g_cm3']/1e15
        existing={round(x['ec_g_cm3']/1e15,5) for x in q}
        for k in range(-5,6):
            ec15=round(peak+k*.018,5)
            if .82<=ec15<=2.46 and round(ec15,5) not in existing:
                run_node(ec15*1e15,'peak-refinement')
    turn=turning_summary(report['direct_C_constant_J_stars'])
    report['fixed_J_turning_summary']=turn
    report['sampled_anchor_is_below_peak']=(anchor['mass_msun']<turn.get('peak_mass_msun',0.) and anchor_ec<turn.get('peak_rho_g_cm3',0.))
    report['status']='SOURCE_ORIGINAL_MPA1_FIXED_J_TURNOVER_NUMERICAL_DIAGNOSTIC_NOT_PHYSICAL_CERTIFICATION' if turn['status'].startswith('SAMPLED_') else 'FIXED_J_STARS_SAMPLED_BUT_TURNOVER_UNBRACKETED'
    save()
    return report


def main():
    ap=argparse.ArgumentParser()
    for k in ('source','f62','rns','out'):ap.add_argument('--'+k,type=Path,required=True)
    a=ap.parse_args();r=run(a.source,a.f62,a.rns,a.out)
    print(json.dumps({'status':r['status'],'turn':r['fixed_J_turning_summary'],'successful':len([x for x in r['direct_C_constant_J_stars'] if x['status'].startswith('DIRECT_C_FIXED_J') and 'mass_msun' in x])},sort_keys=True),flush=True)
    if r['status'].startswith('FIXED_J_STARS_SAMPLED_BUT'):
        raise SystemExit('Turning point not bracketed: no stability proof')

if __name__=='__main__':main()
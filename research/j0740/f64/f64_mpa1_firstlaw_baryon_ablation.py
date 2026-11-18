"""F64: exact F63 196-knot EOS baryon-density *ablation*, not EOS repair.

Uses unchanged source p, epsilon, H. Replaces only the RNS number-density
proxy with a first-law integrated n(P) with arbitrarily anchored n at the
lowest pressure. Prints direct original-C RNS mass, R, f, J, M0 comparisons.
Does NOT prove LALSuite original low-P derivative is admissible or true M0.
"""
from __future__ import annotations
import argparse,hashlib,json,math,re,subprocess
from pathlib import Path
import numpy as np

SOURCE_RNS_SHA='15cd0e83830635fe46264ff5e5c52f97f4b8846dc73c1a64768e1237417d9e51'
JESTER_NPZ_SHA='0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22'
C=2.99792458e10 # cm/s
SOURCE_CENTER=1015366308866642.6 # g/cm3 direct F62 original MPA1
SOURCE_SPIN=346.536369
SOURCE_J=6.104310398721e48

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_rns_table(source):
    source=Path(source)
    if digest(source)!=SOURCE_RNS_SHA:raise ValueError('F64_F63_ORIGINAL_RNS_SOURCE_SHA_DRIFT')
    nstr=source.read_text('ascii').splitlines()[0].strip()
    if nstr!='196':raise ValueError('F64_196_NODES_REQUIRED')
    a=np.loadtxt(source,skiprows=1)
    if a.shape!=(196,4) or not np.isfinite(a).all() or np.any(a<=0):
        raise ValueError('F64_INVALID_RNS_TABLE')
    if not all((np.diff(a[:,i])>0).all() for i in range(4)):
        raise ValueError('F64_RNS_TABLE_NOT_STRICTLY_MONOTONE')
    return a

def integrate_baryons(rows,gauss_nodes=64):
    """32+ point Gauss-Legendre of cold first law for LOG-LINEAR epsilon(P).

    e,P both ergs/cm3; d ln n = d e/(e+P), e(P) locally exponential
    in log-pressure. Anchor n at lowest input source row (unknown mu_0).
    """
    arr=np.asarray(rows,float)
    if arr.ndim!=2 or arr.shape[1]!=4 or len(arr)<10 or not np.isfinite(arr).all():
        raise ValueError('F64_BAD_THERMODYNAMIC_INPUT')
    rho,p,h,n=arr.T
    if (np.any(arr<=0) or not all((np.diff(q)>0).all() for q in (rho,p,h,n))
        or gauss_nodes not in (16,32,64,128)):
        raise ValueError('F64_INVALID_OR_NONMONOTONE_ROWS')
    E=rho*C*C
    lnP=np.log(p); lnE=np.log(E);dlnP=np.diff(lnP)
    alpha=np.diff(lnE)/dlnP
    x,w=np.polynomial.legendre.leggauss(gauss_nodes)
    t=.5*dlnP[:,None]*(x[None,:]+1)
    ee=np.exp(lnE[:-1,None]+alpha[:,None]*t)
    pp=np.exp(lnP[:-1,None]+t)
    dlnn=.5*dlnP*np.sum(w[None,:]*alpha[:,None]*ee/(ee+pp),axis=1)
    dHdimensionless=.5*dlnP*np.sum(w[None,:]*pp/(ee+pp),axis=1)
    if not (np.isfinite(dlnn).all() and (dlnn>0).all()):
        raise ValueError('F64_FIRSTLAW_RECONSTRUCTION_FAILED')
    n_rebuilt=np.exp(np.log(n[0])+np.r_[0,np.cumsum(dlnn)])
    if not (n_rebuilt>0).all() or not np.isfinite(n_rebuilt).all():
        raise ValueError('F64_NONFINITE_FIRSTLAW_N')
    H_rebuilt=h[0]+C*C*np.r_[0,np.cumsum(dHdimensionless)]
    deviation=n/n_rebuilt-1
    return n_rebuilt,H_rebuilt,deviation

def write_rns(dst,rows):
    a=np.asarray(rows,float)
    dst=Path(dst);dst.parent.mkdir(parents=True,exist_ok=True)
    with dst.open('w',encoding='ascii',newline='\n') as f:
        f.write(str(len(a))+'\n')
        np.savetxt(f,a,fmt='%.15e')

C_OLD_FMT=r'printf("%g \t %4.3f \t %4.2f \t %4.1f \n",'
C_OLD_ARGS='star.Omega/(2.0*PI));'
C_NEW_FMT=r'printf("%.10g \t %.9f \t %.9f \t %.9f \t %.9f \t %.12g \n",'
C_NEW_ARGS='star.Omega/(2.0*PI),star.Mass_0/MSUN,star.ang_mom);'

def patch_C_output(original):
    if (original.count(C_OLD_FMT)!=1 or original.count(C_OLD_ARGS)!=1
        or C_NEW_FMT in original or C_NEW_ARGS in original):
        raise ValueError('F64_PINNED_UPSTREAM_RNS_C_PRINTF_DRIFT')
    out=original.replace(C_OLD_FMT,C_NEW_FMT).replace(C_OLD_ARGS,C_NEW_ARGS)
    if out.count(C_NEW_FMT)!=1 or out.count(C_NEW_ARGS)!=1:
        raise ValueError('F64_UNIQUE_C_DIAGNOSTIC_PATCH_FAILED')
    return out

def parse_C(stdout):
    rows=[]
    for line in stdout.splitlines():
        xx=line.split()
        if len(xx)!=6:continue
        try: y=[float(t) for t in xx]
        except ValueError:continue
        if (np.isfinite(y).all() and .2<y[0]<6 and .1<y[1]<4 and 6<y[2]<30 and 0<=y[3]<2000 and .1<y[4]<5 and 1e43<y[5]<1e53):
            rows.append(y)
    if len(rows)!=1:raise ValueError('F64_AMBIGUOUS_DIRECT_RNS_C_ROW:'+str(len(rows)))
    dens,mass,radius,f,m0,J=rows[0]
    return {'central_density_e15_echo':dens,'mass_msun':mass,'radius_km':radius,'spin_hz':f,'rns_M0_msun_UNCERTIFIED':m0,'J_cgs':J}

def one_C_model(binary,table,central_density=SOURCE_CENTER,spin=SOURCE_SPIN):
    result=subprocess.run([str(Path(binary).resolve()),'-f','./'+Path(table).name,
        '-e',f'{central_density:.11g}','-s',f'{spin:.9f}'],cwd=Path(table).parent,
        capture_output=True,text=True,timeout=135)
    if result.returncode!=0:raise RuntimeError('F64_RNS_EXIT_'+str(result.returncode)+':'+result.stderr[-500:])
    d=parse_C(result.stdout)
    if abs(d['central_density_e15_echo']-central_density/1e15)>5e-8:
        raise ValueError('F64_C_SOURCE_DENSITY_ECHO_DRIFT')
    if abs(d['mass_msun']-2.073)>0.005 or abs(d['spin_hz']-spin)>0.4:
        raise ValueError('F64_F62_DIRECT_C_REFERENCE_MASS_SPIN_DRIFT')
    return d

def run(original_rns,binary,outdir):
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    a=load_rns_table(original_rns)
    nb,Hfl,dev=integrate_baryons(a,64)
    n32,_,dev32=integrate_baryons(a,32)
    n128,_,dev128=integrate_baryons(a,128)
    if max(np.max(abs(nb/n32-1)),np.max(abs(nb/n128-1)))>5e-12:
        raise ValueError('F64_INDEPENDENT_QUADRATURE_NOT_CONVERGED')
    if not np.allclose(a[:,3]/a[:,0],a[0,3]/a[0,0],rtol=2e-12):
        raise ValueError('F64_EXPECTED_SOURCE_N_IS_ENERGY_PROXY_DRIFT')
    firstlaw=a.copy();firstlaw[:,3]=nb
    if not np.array_equal(firstlaw[:,:3],a[:,:3]):
        raise ValueError('F64_MODIFIED_ENERGY_PRESSURE_OR_ENTHALPY')
    raw=outdir/'MPA1_F64_original_n_proxy.rns';new=outdir/'MPA1_F64_firstlaw_n_ONLY.rns'
    write_rns(raw,a);write_rns(new,firstlaw)
    # Avoid any input from an altered source table in the root reproducer.
    old_model=one_C_model(binary,raw)
    new_model=one_C_model(binary,new)
    delta={k: new_model[k]-old_model[k] for k in old_model if k!='central_density_e15_echo'}
    if any(abs(delta[k])>tol for k,tol in [('mass_msun',1e-8),('radius_km',1e-8),('spin_hz',1e-7),('J_cgs',1e42)]):
        raise ValueError('F64_CHANGING_N_ALTERED_GRAVITATIONAL_SOLUTION')
    if abs(delta['rns_M0_msun_UNCERTIFIED'])<0.001:
        raise ValueError('F64_EXPECTED_M0_SENSITIVITY_ABSENT')
    center_logrho=np.log(SOURCE_CENTER)
    at_center=float(np.interp(center_logrho,np.log(a[:,0]),dev))
    peak_rho=2.102e15
    at_peak=float(np.interp(np.log(peak_rho),np.log(a[:,0]),dev))
    report={
        'schema':'J0740_F64_ORIGINAL_MPA1_F63_EXACT_RNS_FIRSTLAW_N_ONLY_ABLATION_v1',
        'status':'DIRECT_C_RNS_TWO_REAL_MODELS_N_ONLY_ABLATION_PASS_NOT_PHYSICAL_EOS',
        'source_F63_exact_196point_EOS_SHA256':SOURCE_RNS_SHA,
        'source_JESTER_NPZ_sha256_from_F63_provenance':JESTER_NPZ_SHA,
        'model':'ORIGINAL_MPA1_UNMODIFIED_PRESSURE_ENERGY_ENTHALPY_SOURCE_DERIVED_EOS',
        'source_mavg_number_density_proxy':True,
        'n_reconstructed_from_cold_firstlaw_LOG_LINEAR_E_of_P':True,
        'n_firstlaw_normalization':'ANCHOR_TO_SOURCE_N_AT_LOWEST_PRESSURE_NOT_PHYSICAL_MU0',
        'n_source_divided_by_firstlaw_minus1_at_firstnode':float(dev[0]),
        'n_source_divided_by_firstlaw_minus1_at_F62_center':at_center,
        'n_source_divided_by_firstlaw_minus1_at_F63_peak':at_peak,
        'n_source_divided_by_firstlaw_minus1_at_lastnode':float(dev[-1]),
        'independent_32_64_128_gauss_n_max_relative':float(max(np.max(abs(nb/n32-1)),np.max(abs(nb/n128-1)))),
        'source_H_terminal_vs_loglinear_E_P_firstlaw_H_terminal_fraction':float((a[-1,2]-Hfl[-1])/Hfl[-1]),
        'unchanged_columns':['rho_g_cm3','pressure_dyn_cm2','enthalpy_cm2_s2'],
        'altered_column':'RNS baryon number density n_cm_minus3 ONLY',
        'original_proxy_RNS_C':old_model,
        'firstlaw_n_RNS_C':new_model,
        'firstlaw_minus_proxy_RNS_C':delta,
        'original_and_n_only_same_direct_GR_solution':True,
        'original_RNS_file_reprinted_SHA256':digest(raw),'n_rebuilt_RNS_file_sha256':digest(new),
        'rns_executable_sha256':digest(binary),
        'warnings':[
            'n(P) depends on arbitrary reference anchor; first-law consistency is not physical rest-mass normalization nor a native original nuclear EOS repair',
            'RNS source input E,P,H retains original low-pressure source negative cs2 knot in the upstream NPZ, which its 196-knot resampling may skip; physically uncertified',
            'Replacing n does not repair original H(P) mismatch or establish first-law consistency of full upstream LAL EOS',
            'RNS M0 sensitivity under this ablation must not be interpreted as observed baryonic mass correction; normalization to physical rest-mass chemical potential not independently fixed',
            'Direct RNS gravitating properties at one central density and spin are not independent rotating global nonlinear stability or seven-EOS Bayes',
            'Source-native X-PSI photon nuisance-marginal likelihood is NOT_RUN',
        ],
        'global_microphysical_certification':'NOT_ESTABLISHED',
        'rotating_MPA1_fixed_J_F63_peak':'PREEXISTING_F63_NOT_RERUN',
        'XPSI_Bayes':'NOT_RUN',
    }
    (outdir/'F64_original_MPA1_n_only_ablation.json').write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ['status','n_source_divided_by_firstlaw_minus1_at_F62_center','n_source_divided_by_firstlaw_minus1_at_F63_peak','n_source_divided_by_firstlaw_minus1_at_lastnode','firstlaw_minus_proxy_RNS_C']}))
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--binary',type=Path,required=True)
    ap.add_argument('--outdir',type=Path,required=True)
    args=ap.parse_args();run(args.source,args.binary,args.outdir)

if __name__=='__main__':main()
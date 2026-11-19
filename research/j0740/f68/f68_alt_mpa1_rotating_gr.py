"""F68: Direct full-GR RNS C stars for separately named F67 MPA1_PCHIP_COLD_V1.

Not original MPA1, not F42, NOT physical n0/M0 certificate or X-PSI inference.
An unmodified SHA-locked F67 thermo table is resampled for the RNS solver.
Coarse 151x301 spacetime mesh and fine 201x401 use BYTE-IDENTICAL EOS table.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
import numpy as np

G=6.67430e-11;C=299792458.;M_BARYON_G=1.66053906660e-24
MODEL='MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL'
F67_THERMO_SHA='d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22'
F67_ROOT_SHA='811b6b9e3763e77df0e300f54cae0301cdac1cb1c285b09da8f32e23c0aa0dc8'
F61_SHA='7b2cbcf6df2dc55d33046d9af587dba179dcb2ec77bad0395e628742479cce0a'
RNS_UPSTREAM_SHA='97e85d325a33e37f702306414533f6cd77812477'
TARGET_SPIN=346.536369
TARGETS=(2.073,2.175,2.200,2.250)
EOS_POINTS=196


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_f67(table_path,root_path):
    if sha(table_path)!=F67_THERMO_SHA:raise ValueError('F68_F67_THERMO_SOURCE_SHA_DRIFT')
    if sha(root_path)!=F67_ROOT_SHA:raise ValueError('F68_F67_TOV_SOURCE_SHA_DRIFT')
    obj=json.loads(Path(root_path).read_text())
    if obj.get('model_label')!=MODEL or obj.get('not_original_MPA1') is not True or obj.get('physically_admissible_full_EOS')!='NOT_ESTABLISHED' or obj.get('alternate_firstlaw_table_sha256')!=F67_THERMO_SHA:
        raise ValueError('F68_FALSE_ORIGINAL_MODEL_OR_F67_STATUS')
    x=np.loadtxt(table_path,dtype=float)
    if x.ndim!=2 or x.shape!=(2425,4) or not np.isfinite(x).all() or (x[:,[0,1,3]]<=0).any() or (x[:,2]<0).any():
        raise ValueError('F68_BAD_TABLE_SHAPE_OR_VALUES')
    if not np.isclose(x[0,2],0,atol=1e-12) or not np.isclose(x[0,3],1,rtol=1e-12):raise ValueError('F68_BAD_H_N_REFERENCE')
    if (np.diff(x[:,0])<=0).any() or (np.diff(x[:,1])<=0).any() or (np.diff(x[:,2])<=0).any() or (np.diff(x[:,3])<=0).any():
        raise ValueError('F68_FIRSTLAW_EOS_MONOTONICITY_DRIFT')
    return x,obj

def to_rns_196(x,points=EOS_POINTS):
    if points!=EOS_POINTS:raise ValueError('F68_REQUIRE_EXACT_196_EOS_POINTS')
    y=np.linspace(math.log(x[0,0]),math.log(x[-1,0]),points)
    p=np.exp(y)
    e=np.exp(np.interp(y,np.log(x[:,0]),np.log(x[:,1])))
    h=np.interp(y,np.log(x[:,0]),x[:,2])
    n_rel=np.exp(np.interp(y,np.log(x[:,0]),np.log(x[:,3])))
    # Explicit arbitrary n0 choice, NEVER interpret baryonic M0 physically.
    # Existing RNS file format needs a positive baryon-number column.
    n0_proxy=x[0,1]*(C*C/G*1e-3)/M_BARYON_G
    n_cm3=n0_proxy*n_rel
    rows=np.column_stack([e*C*C/G*1e-3,p*C**4/G*10,h*(C*100)**2+1,n_cm3])
    if not np.isfinite(rows).all() or (rows<=0).any() or any((np.diff(rows[:,j])<=0).any() for j in range(4)):
        raise ValueError('F68_BAD_RNS_THERMO_RESAMPLING')
    return rows,{'source_model_label':MODEL,'source_F67_thermo_sha256':F67_THERMO_SHA,'source_rows':len(x),'rns_rows':len(rows),
        'arbitrary_n0_reference_cm_minus3':n0_proxy,'baryonic_M0_physical_calibration':'NOT_ESTABLISHED',
        'thermo_loglinear_resampling_of_explicit_F67_PCHIP_table':True}

def write_rns_table(path,rows):
    if Path(path).name!='ALT196.rns':raise ValueError('F68_RNS_SOURCE_BASENAME_PIN')
    with Path(path).open('w',encoding='ascii',newline='\n') as stream:
        stream.write(f'{len(rows)}\n')
        np.savetxt(stream,rows,fmt='%.15e')

def verify_rns_identity(path,expected):
    if sha(path)!=expected:raise ValueError('F68_SPACETIME_GRIDS_NOT_BYTE_IDENTICAL_EOS')
    lines=Path(path).read_text().splitlines()
    if lines[0]!='196' or len(lines)!=197:raise ValueError('F68_RNS_TABLE_LENGTH_DRIFT')
    return True

def load_f61(f61):
    if sha(f61)!=F61_SHA:raise ValueError('F68_F61_SOURCE_DRIFT')
    d=json.loads(Path(f61).read_text())
    if d['status']!='DIRECT_NATIVE_STATIC_TOV_ONLY_NOT_ROTATING_OR_EOS_POSTERIOR' or d['EOS_original_not_F42_modified'] is not True:
        raise ValueError('F68_F61_IS_NOT_ORIGINAL_SOURCE')
    return d['results']['MPA1']['stars']

def seed_for_mass(x,f61,mass):
    pc=float(f61[f'{mass:.3f}']['central_pressure_si_pa'])*G/C**4
    if not x[0,0]<pc<x[-1,0]:raise ValueError('F68_OLD_SOURCE_CENTRAL_PRESSURE_OUTSIDE_NEW_EOS')
    return float(np.exp(np.interp(math.log(pc),np.log(x[:,0]),np.log(x[:,1])))*C*C/G*1e-3)

def physical_output_gate(star,target,spin):
    if not isinstance(star,dict):raise ValueError('F68_NO_ACTUAL_RNS_MODEL')
    if abs(star['mass_msun']-target)>.0015 or abs(star['spin_hz_reported']-spin)>.25:
        raise ValueError('F68_BAD_DIRECT_RNS_MASS_OR_FREQUENCY')
    if not 7<star['radius_eq_km']<24 or not 2e14<star['central_energy_density_g_cm3']<4e15:
        raise ValueError('F68_RNS_NUMERICAL_BOUNDS_FAIL')

def direct_sequence(binary,table,x,f61,result_file,*,targets=TARGETS,grid='151x301',same_eos_sha=None):
    if grid not in ('151x301','201x401'):raise ValueError('F68_UNKNOWN_C_GR_GRID')
    if same_eos_sha is not None:verify_rns_identity(table,same_eos_sha)
    from pathlib import Path as _Path
    sys.path.insert(0,str(_Path(__file__).resolve().parents[1]/'f62'))
    from f62_native_mpa1_rotating import trial_root
    work={'schema':'F68_ALTERNATE_MPA1_PCHIP_COLD_DIRECT_FULL_RNS_C_ROTATING_GR_V1',
        'model':MODEL,'not_original_MPA1':True,'not_F42':True,'grid':grid,'rns_derived_table_sha256':sha(table),
        'same_EOS_table_byte_sha256':same_eos_sha,'target_spin_hz':TARGET_SPIN,'direct_C_stars':{},
        'source_n0_physical_calibration':'NOT_ESTABLISHED','rotating_Stability':'NOT_ESTABLISHED',
        'global_Causality':'NOT_ESTABLISHED','true_zero_P_crust_surface':'NOT_ESTABLISHED',
        'source_native_NICER_XMM_XPSI_likelihood':'NOT_RUN','original_seven_EOS_Bayes':'NOT_RUN',
        'status':'IN_PROGRESS','rns_c_binary_sha256':sha(binary),
        'limitations':['Mathematically separate F67 PCHIP cold EOS, not original MPA1 nuclear EOS',
           'F67 H(P) is sourced from positive minimum pressure, not a physical P=0 crust surface',
           'EOS table has 196 new resampled points; this is a discretized representation sensitivity test',
           'n0 is arbitrarily set by mass-density proxy, so do not interpret RNS M0 as physical',
           'Single-spin GR roots, not global stability or microphysical EOS proof',
           'No source-native photon nuisance likelihood or Bayes posterior']}
    result_file.parent.mkdir(parents=True,exist_ok=True)
    def save():result_file.write_text(json.dumps(work,sort_keys=True,indent=2,allow_nan=False)+'\n')
    save()
    for mass in targets:
        key=f'{mass:.3f}'
        seed=seed_for_mass(x,f61,mass)
        block={'static_anchor_from_F61_original_not_same_model_gcm3':seed,'status':'IN_PROGRESS'}
        work['direct_C_stars'][key]=block;save()
        try:
            spinning=trial_root(binary,table,mass,seed,TARGET_SPIN)
            static=trial_root(binary,table,mass,seed,0.)
            physical_output_gate(spinning['star'],mass,TARGET_SPIN)
            physical_output_gate(static['star'],mass,0.)
            dr=spinning['star']['radius_eq_km']-static['star']['radius_eq_km']
            if not 0<dr<.8:raise ValueError('F68_ROTATING_RADIUS_NOT_LARGER_THAN_STATIC')
            block.update({'status':'DIRECT_RNS_C_SPIN_AND_STATIC_ROOTS_PASS_NUMERICAL_ONLY',
                 'rotating':spinning,'static':static,
                 'spin_minus_static_eq_radius_km':dr,
                 'C_evaluations_rotating':spinning['actual_direct_C_calls'],
                 'C_evaluations_static':static['actual_direct_C_calls']})
        except Exception as exc:
            block['status']='FAILED_NOT_A_PHYSICAL_RESULT';block['error']=type(exc).__name__+': '+str(exc)[:1300]
            save();raise
        save();print('F68',grid,key,'DIRECT_C_STAR_PASS',flush=True)
    work['status']='DIRECT_RNS_C_ALTERNATE_PCHIP_COLD_GRID_DIAGNOSTIC_PASS_NO_EOS_BAYES'
    save();return work

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--f67-thermo',type=Path,required=True);ap.add_argument('--f67-tov',type=Path,required=True)
    ap.add_argument('--f61',type=Path,required=True);ap.add_argument('--rns-binary',type=Path,required=True)
    ap.add_argument('--rns-table',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--grid',choices=('151x301','201x401'),required=True)
    ap.add_argument('--eos-identity-sha');ap.add_argument('--targets',nargs='+',type=float,default=list(TARGETS))
    args=ap.parse_args()
    x,tov=load_f67(args.f67_thermo,args.f67_tov)
    f61=load_f61(args.f61)
    if args.grid=='151x301':
        rows,metadata=to_rns_196(x)
        args.rns_table.parent.mkdir(parents=True,exist_ok=True);write_rns_table(args.rns_table,rows)
        (args.rns_table.parent/'F68_EOS_conversion_provenance.json').write_text(json.dumps(metadata,sort_keys=True,indent=2)+'\n')
    elif not args.eos_identity_sha:raise ValueError('F68_FINE_GRID_REQUIRES_PREVIOUS_COARSE_EOS_SHA')
    if args.eos_identity_sha:verify_rns_identity(args.rns_table,args.eos_identity_sha)
    d=direct_sequence(args.rns_binary,args.rns_table,x,f61,args.output,targets=tuple(args.targets),grid=args.grid,same_eos_sha=args.eos_identity_sha)
    if args.grid=='151x301':
        ref=float(tov['new_M2p073_PCHIP_root']['R_km'])
        result=d['direct_C_stars']['2.073']['static']['star']['radius_eq_km']
        difference=result-ref
        d['direct_RNS_static_minus_independent_F67_TOV_km']=difference
        if abs(difference)>.20:raise ValueError(f'F68_ALTERNATE_RNS_VS_F67_TOV_NOT_CONSISTENT_{difference}')
        args.output.write_text(json.dumps(d,sort_keys=True,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'result':d['status'],'grid':args.grid,'mass_targets':list(args.targets),
     'eos_sha':d['rns_derived_table_sha256']},sort_keys=True),flush=True)

if __name__=='__main__':main()
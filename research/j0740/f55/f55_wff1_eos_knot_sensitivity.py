"""F55 WFF1 original-source EOS table knot-count sensitivity at fixed real J.

Reconstruct same F42 *candidate* from SHA-pinned original JESTER WFF1 NPZ,
not by stripping nodes off the 200-row reference. Lock the existing F44
200-row source table and reuse genuinely computed F53 201x401 constant-J stars.
Run only NEW 160-, 180-, and 196-row tables at three matched central densities,
using unmodified C-RNS solver arithmetic and a diagnostic J print patch.

Tests address EOS table discrete first-law consistency / causality under
resampling; no global nonlinear/dynamical stability or original nuclear WFF1
microphysics is inferred. A 200-node rebuilt table is a reproducibility check
only: its stellar roots are NOT re-run.
"""
from __future__ import annotations
import argparse,hashlib,io,json,math,sys,zipfile
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'f42'))
sys.path.insert(0,str(HERE.parent/'f53'))
from f42_causal_firstlaw_candidates import Candidate,MB,C,G
from f53_wff1_constant_j import solve_at_J,run_one

PINNED_JESTER_SOURCE_SHA='119b8a25435faeddf00f5d3638f3ff2ff00283ce60caacc24cc37c6e2e030ed3'
F44_ARTIFACT_SHA='b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98'
F53_ARTIFACT_SHA='e35a52b02745d596cdea93427e15d5f7eb1e52c6f591fb21eb61501d57de2ae7'
RNS_COMMIT='97e85d325a33e37f702306414533f6cd77812477'
VARIANT_KNOTS=(160,180,196)
MATCHED_E15=(2.875,2.900,2.925)
TOL_SOURCE_200_REBUILD_MAX_REL=2e-12
TOL_MASS_DELTA_MSUN=.012
TOL_RADIUS_DELTA_KM=.150
TOL_MAX_CANDIDATE_SECANT_CS2=.9900001
TOL_N_FIRSTLAW_REL=2e-10


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def load_inputs(original_npz,f44,f53,work):
    if (sha(original_npz)!=PINNED_JESTER_SOURCE_SHA or sha(f44)!=F44_ARTIFACT_SHA
            or sha(f53)!=F53_ARTIFACT_SHA):
        raise ValueError('F55_ORIGINAL_WFF1_SOURCE_OR_EXPERIMENT_SHA_DRIFT')
    with zipfile.ZipFile(f44) as z:
        if z.testzip() is not None:raise ValueError('F55_F44_ZIP_CRC_FAIL')
        meta=json.loads(z.read('F44_direct_RNS_seven_candidates.json'))['eos']['WFF1']
        table_name=meta['model_label']+'.rns'
        orig=z.read('eos_tables/'+table_name)
        if hashlib.sha256(orig).hexdigest()!=meta['model_table_sha256']:
            raise ValueError('F55_ORIGINAL_F44_C_TABLE_SHA_MISMATCH')
        original=np.loadtxt(io.BytesIO(orig),skiprows=1)
    with zipfile.ZipFile(f53) as z:
        if z.testzip() is not None:raise ValueError('F55_F53_ZIP_CRC_FAIL')
        fine=json.loads(z.read('F53_WFF1_direct_C_constant_J_stars.json'))
        if (fine['status']!='PASS_SAMPLED_CONSTANT_J_TURNING_DIAGNOSTIC_NOT_GLOBAL_STABILITY'
            or fine['WFF1_EOS_table_sha256']!=meta['model_table_sha256']
            or fine['RNS_upstream_commit']!=RNS_COMMIT):
            raise ValueError('F55_F53_FIXED_J_PHYSICS_SOURCE_DRIFT')
    good={}
    for ec in MATCHED_E15:
        entries=[s for s in fine['direct_C_constant_J_stars'] if
                 s['status']=='DIRECT_C_FIXED_J_PASS' and
                 abs(s['ec_g_cm3']/1e15-ec)<1e-7]
        if len(entries)!=1:raise ValueError('F55_FINE_MATCHED_DIRECT_C_STAR_MISSING')
        if abs(entries[0]['relative_J_residual'])>1e-5:
            raise ValueError('F55_FINE_J_RESIDUAL_BAD')
        good[str(ec)]=entries[0]
    with np.load(original_npz,allow_pickle=False) as z:
        p=np.array(z['p'],dtype=float);e=np.array(z['e'],dtype=float)
    candidate=Candidate(p,e,cap=.99,alpha=.6)
    work.mkdir(parents=True,exist_ok=True)
    return candidate,original,orig,meta,fine,good,table_name


def table_thermodynamic_diagnostic(rows):
    data=np.asarray(rows,dtype=float)
    if (data.ndim!=2 or data.shape[1]!=4 or len(data)<40 or len(data)>200
        or not np.isfinite(data).all() or not np.all(data>0)
        or any(np.any(np.diff(data[:,i])<=0) for i in range(4))):
        raise ValueError('F55_TABLE_NONPOSITIVE_OR_NONMONOTONE_FOUR_THERMO_COLUMNS')
    rho,p,H,n=[data[:,i] for i in range(4)]
    sound=np.diff(p)/(np.diff(rho)*(C*100)**2)
    if not np.isfinite(sound).all() or np.any(sound<=0):
        raise ValueError('F55_TABLE_CANDIDATE_SOUND_SPEED_UNDEFINED')
    egeo=rho*G*1e3/C**2
    pgeo=p*G/(C**4*10.0)
    hgeo=H/(C*100)**2
    n_expected=(egeo+pgeo)*np.exp(-hgeo)*C*C/(G*MB)/1e6
    rel=float(np.max(np.abs(n_expected/n-1)))
    out={'rows':len(data),'max_secant_dp_de':float(np.max(sound)),
         'min_secant_dp_de':float(np.min(sound)),
         'firstlaw_n_max_rel_error':rel,
         'four_columns_monotone':True,
         'physical_mu0_is_model_assumption':'single assumed bare baryon rest mass, not validated nuclear microphysics',
         'detailed_RNS_C_eos_interpolant_derivative':'NOT_DIRECTLY_MEASURED'}
    if out['max_secant_dp_de']>TOL_MAX_CANDIDATE_SECANT_CS2 or rel>TOL_N_FIRSTLAW_REL:
        raise ValueError('F55_RESAMPLED_CANDIDATE_CAUSALITY_OR_FIRSTLAW_GATE_FAIL')
    return out


def write_table(path,rows):
    with Path(path).open('w',encoding='ascii',newline='\n') as f:
        f.write(str(len(rows))+'\n')
        np.savetxt(f,rows,fmt='%.15e')


def summarize_variants(variants):
    results={}
    for points,entry in variants.items():
        rows=entry['matched_rows']
        if len(rows)!=len(MATCHED_E15) or any(r['status']!='DIRECT_C_FIXED_J_PASS' for r in rows):
            results[points]={'status':'INCOMPLETE_DIRECT_C_VARIANT'}
            continue
        max_dm=max(abs(r['delta_mass_msun']) for r in rows)
        max_dr=max(abs(r['delta_radius_km']) for r in rows)
        max_dj=max(abs(r['variant']['relative_J_residual']) for r in rows)
        masses=[r['variant']['mass_msun'] for r in rows]
        imax=max(range(len(rows)),key=lambda i:masses[i])
        brack=(imax==1 and masses[1]>masses[0] and masses[1]>masses[2])
        accepted=max_dm<=TOL_MASS_DELTA_MSUN and max_dr<=TOL_RADIUS_DELTA_KM and max_dj<1e-5 and brack
        results[points]={'status':'PASS_CANDIDATE_EOS_KNOT_LOCAL_SENSITIVITY' if accepted
                          else 'EOS_KNOT_SENSITIVITY_NOT_ACCEPTED',
                         'max_abs_delta_mass_msun':max_dm,
                         'max_abs_delta_eqradius_km':max_dr,
                         'max_abs_relative_J_residual':max_dj,
                         'variant_sampled_peak_msun':masses[imax],
                         'variant_sampled_peak_center_e15':rows[imax]['density_e15'],
                         'variant_peak_bracketed_on_3_points':brack}
    complete=(len(results)==len(VARIANT_KNOTS) and
              all(r['status']=='PASS_CANDIDATE_EOS_KNOT_LOCAL_SENSITIVITY'
                  for r in results.values()))
    return {'status':'PASS_THREE_EOS_KNOT_SENSITIVITIES_NOT_PHYSICAL_EOS' if complete
            else 'PARTIAL_OR_FAILED_CANDIDATE_KNOT_SENSITIVITY',
            'per_variant':results,'predeclared_mass_delta_gate_msun':TOL_MASS_DELTA_MSUN,
            'predeclared_radius_delta_gate_km':TOL_RADIUS_DELTA_KM,
            'constant_J_required':True,
            'EOS_physics_validated':False,'global_dynamical_stability':'NOT_ESTABLISHED'}


def run(npz,f44,f53,binary,patch,work,out):
    candidate,original,original_bytes,meta,fine,matched,filename=load_inputs(npz,f44,f53,work)
    patchrec=json.loads(Path(patch).read_text())
    if patchrec.get('replacements')!=1 or patchrec.get('printed_J_cgs_symbol')!='star.ang_mom':
        raise ValueError('F55_PINNED_J_PRINT_PATCH_INCORRECT')
    rebuilt,rebuilt_meta=candidate.rns_table(points=200,surface_depth=12)
    if rebuilt.shape!=original.shape:raise ValueError('F55_SOURCE_REGENERATED_200_ROWS_SHAPE_DRIFT')
    rel=float(np.max(np.abs(rebuilt/original-1)))
    if rel>TOL_SOURCE_200_REBUILD_MAX_REL:
        raise ValueError('F55_200NODE_ORIGINAL_TABLE_SOURCE_MISMATCH')
    original_diag=table_thermodynamic_diagnostic(original)
    source_cs2_max=float(np.max(candidate.cs2))
    if source_cs2_max>.990000001:raise ValueError('F55_SOURCE_CAUSAL_CAP_DRIFT')
    result={'schema':'J0740_F55_PINNED_JESTER_WFF1_CANDIDATE_EOS_KNOT_CGR_v1',
            'status':'STARTED','source_original_WFF1_npz_sha256':sha(npz),
            'F44_source_artifact_sha256':sha(f44),
            'F53_real_201x401_reference_artifact_sha256':sha(f53),
            'original_200row_RNS_table_sha256':hashlib.sha256(original_bytes).hexdigest(),
            'regen_200_source_max_relative_table_difference':rel,
            '200row_table_mathematically_regenerated_not_recomputed_stars':True,
            'original_200row_thermodynamic_diagnostic':original_diag,
            'source_original_max_causal_candidate_cs2':source_cs2_max,
            'source_original_max_energy_lift_fraction':float(np.max((candidate.e-candidate.source_e)/candidate.source_e)),
            'fixed_reference_J_cgs':fine['constant_target_J_cgs'],
            'original_F53_201x401_spatial_grid':'ALREADY_SAVED_AND_REUSED',
            'RNS_fine_C_binary_sha256':sha(binary),
            'original_C_patch':patchrec,
            'candidate_EOS_is_new_F42_lift_not_original_nuclear_WFF1':True,
            'baryon_mass_absolute_physics':'NOT_CERTIFIED',
            'XPSI_fifteen_dimensional_native_posterior':'NOT_RUN',
            'variants':{},'source_star_match_center_e15':list(MATCHED_E15)}
    out.parent.mkdir(parents=True,exist_ok=True)
    def save():out.write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+'\n')
    save()
    for points in VARIANT_KNOTS:
        rows,meta_variant=candidate.rns_table(points=points,surface_depth=12)
        diag=table_thermodynamic_diagnostic(rows)
        table=work/filename
        write_table(table,rows)
        variant={'points':points,'table_sha256':sha(table),
                 'thermodynamic_diagnostic':diag,
                 'matched_rows':[],'model_details':meta_variant}
        result['variants'][str(points)]=variant
        save()
        for e15 in MATCHED_E15:
            prior=matched[str(e15)]
            entry={'density_e15':e15,'F53_fine_reference':{k:prior[k] for k in
                   ('mass_msun','radius_eq_km','spin_hz','J_cgs','ec_g_cm3','axis_ratio')}}
            trace=[]
            try:
                star,trace=solve_at_J(lambda e,r:run_one(binary,table,e,r),
                                      e15*1e15,fine['constant_target_J_cgs'],
                                      prior['axis_ratio'],trace)
                entry['variant']=star
                entry['status']='DIRECT_C_FIXED_J_PASS'
                entry['delta_mass_msun']=star['mass_msun']-prior['mass_msun']
                entry['delta_radius_km']=star['radius_eq_km']-prior['radius_eq_km']
                print(f"F55 points={points} ec={e15} dM={entry['delta_mass_msun']:.9g} dR={entry['delta_radius_km']:.8g}",flush=True)
            except Exception as exc:
                entry['status']='DIRECT_C_VARIANT_FAILED'
                entry['error']=type(exc).__name__+': '+str(exc)[:260]
                print(f"F55 points={points} ec={e15} FAILED: {entry['error']}",flush=True)
            entry['trace']=trace
            variant['matched_rows'].append(entry)
            save()
        (work/f'WFF1_candidate_{points}_nodes.rns').write_bytes(table.read_bytes())
    result['knot_sensitivity']=summarize_variants(result['variants'])
    result['status']=result['knot_sensitivity']['status']
    save()
    return result


def main():
    p=argparse.ArgumentParser()
    for field in ('npz','f44','f53','binary','patch','work','out'):
        p.add_argument('--'+field,type=Path,required=True)
    a=p.parse_args()
    result=run(a.npz,a.f44,a.f53,a.binary,a.patch,a.work,a.out)
    print(json.dumps(result['knot_sensitivity'],sort_keys=True),flush=True)
    if not result['status'].startswith('PASS_'):raise SystemExit(2)

if __name__=='__main__':main()

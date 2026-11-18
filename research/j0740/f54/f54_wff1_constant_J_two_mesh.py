"""F54 genuine WFF1 constant-J two-spatial-mesh convergence check.

Reuse F53's existing 201x401 direct C-RNS stars; independently compute
151x301 direct C-RNS stars at identical central densities and identical
angular momentum. EOS table is byte-identical F44. Not a rerun of the
27 fine-mesh stars, and not a global dynamical stability certification.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys,zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'f53'))
from f53_wff1_constant_j import solve_at_J,run_one

F44_SHA='b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98'
F53_SHA='e35a52b02745d596cdea93427e15d5f7eb1e52c6f591fb21eb61501d57de2ae7'
RNS_SHA='97e85d325a33e37f702306414533f6cd77812477'
MATCHED_E15=(2.80,2.85,2.875,2.900,2.925,2.950,3.000)
MAX_ABS_MASS_DELTA_Msun=.003
MAX_ABS_RADIUS_DELTA_km=.080
MAX_PEAK_EC_DIFFERENCE_E15=.075


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def lock_inputs(f44,f53,work):
    if sha(f44)!=F44_SHA or sha(f53)!=F53_SHA:
        raise ValueError('F54_F44_OR_F53_ARTIFACT_SHA_DRIFT')
    with zipfile.ZipFile(f44) as z:
        if z.testzip() is not None:raise ValueError('F54_F44_ZIP_BAD_CRC')
        record=json.loads(z.read('F44_direct_RNS_seven_candidates.json'))
        eos=record['eos']['WFF1']
        table_name=eos['model_label']+'.rns'
        payload=z.read('eos_tables/'+table_name)
        table_sha=hashlib.sha256(payload).hexdigest()
        if table_sha!=eos['model_table_sha256']:
            raise ValueError('F54_WFF1_TABLE_SOURCE_DRIFT')
    with zipfile.ZipFile(f53) as z:
        if z.testzip() is not None:raise ValueError('F54_F53_ZIP_BAD_CRC')
        fine=json.loads(z.read('F53_WFF1_direct_C_constant_J_stars.json'))
        if (fine['status']!='PASS_SAMPLED_CONSTANT_J_TURNING_DIAGNOSTIC_NOT_GLOBAL_STABILITY'
                or fine['WFF1_EOS_table_sha256']!=table_sha
                or len(fine['direct_C_constant_J_stars'])!=27
                or fine['RNS_upstream_commit']!=RNS_SHA):
            raise ValueError('F54_FINE_SOURCE_FAIL_OR_DRIFT')
    target_j=fine['constant_target_J_cgs']
    matched={}
    for density in MATCHED_E15:
        candidates=[s for s in fine['direct_C_constant_J_stars'] if
                    s['status']=='DIRECT_C_FIXED_J_PASS' and
                    abs(s['ec_g_cm3']/1e15-density)<1e-7]
        if len(candidates)!=1:raise ValueError('F54_MATCHED_FINE_STAR_MISSING_OR_DUPLICATE')
        if abs(candidates[0]['J_cgs']/target_j-1)>1e-5:
            raise ValueError('F54_FINE_SOURCE_ANGULAR_MOMENTUM_DRIFT')
        matched[str(density)]=candidates[0]
    work.mkdir(parents=True,exist_ok=True)
    table=work/table_name
    table.write_bytes(payload)
    return table,fine,matched


def summarize_pairs(rows):
    if len(rows)!=len(MATCHED_E15) or any(s['status']!='MATCHED_BOTH_REAL_C_STARS' for s in rows):
        return {'status':'INCOMPLETE_MATCHED_MESH_STARS'}
    masses=[abs(s['coarse_minus_fine_mass_Msun']) for s in rows]
    radii=[abs(s['coarse_minus_fine_radius_km']) for s in rows]
    Jerr=[abs(s['coarse']['relative_J_residual']) for s in rows]
    fine_peak=max(rows,key=lambda s:s['fine']['mass_msun'])
    coarse_peak=max(rows,key=lambda s:s['coarse']['mass_msun'])
    fine_i=rows.index(fine_peak);coarse_i=rows.index(coarse_peak)
    valid_peak=(0<fine_i<len(rows)-1 and 0<coarse_i<len(rows)-1
                and rows[fine_i-1]['fine']['mass_msun']<fine_peak['fine']['mass_msun']
                and rows[fine_i+1]['fine']['mass_msun']<fine_peak['fine']['mass_msun']
                and rows[coarse_i-1]['coarse']['mass_msun']<coarse_peak['coarse']['mass_msun']
                and rows[coarse_i+1]['coarse']['mass_msun']<coarse_peak['coarse']['mass_msun'])
    acceptance=(max(masses)<=MAX_ABS_MASS_DELTA_Msun
                and max(radii)<=MAX_ABS_RADIUS_DELTA_km
                and max(Jerr)<1e-5 and valid_peak
                and abs(fine_peak['ec_e15']-coarse_peak['ec_e15'])<=MAX_PEAK_EC_DIFFERENCE_E15)
    return {
        'status':'PASS_LOCAL_TWO_SPATIAL_MESH_SENSITIVITY_NOT_PHYSICAL_STABILITY'
                 if acceptance else 'NOT_ACCEPTED_MESH_DIFFERENCE_OR_TURNOVER',
        'compared_direct_pairs':len(rows),
        'max_abs_coarse_fine_mass_delta_Msun':max(masses),
        'max_abs_coarse_fine_radius_delta_km':max(radii),
        'max_abs_coarse_fixed_J_relative_error':max(Jerr),
        'coarse_sample_peak_M_msun':coarse_peak['coarse']['mass_msun'],
        'coarse_sample_peak_ec_e15':coarse_peak['ec_e15'],
        'fine_sample_peak_M_msun':fine_peak['fine']['mass_msun'],
        'fine_sample_peak_ec_e15':fine_peak['ec_e15'],
        'coarse_peak_neighbor_bracket':valid_peak,
        'M_delta_acceptance_Msun':MAX_ABS_MASS_DELTA_Msun,
        'R_delta_acceptance_km':MAX_ABS_RADIUS_DELTA_km,
        'peak_ec_delta_acceptance_e15':MAX_PEAK_EC_DIFFERENCE_E15,
        'global_stability':'NOT_ESTABLISHED',
        'F42_WFF1_microphysics_certified':False,
        'EOS_table_knot_convergence':'NOT_TESTED'
    }


def run(f44,f53,binary,patch,work,out):
    table,fine,matched=lock_inputs(f44,f53,work)
    check=json.loads(Path(patch).read_text())
    if check.get('replacements')!=1 or check.get('printed_J_cgs_symbol')!='star.ang_mom':
        raise ValueError('F54_COARSE_RNS_C_PRINT_NOT_SOURCE_LOCKED')
    target_j=fine['constant_target_J_cgs']
    report={
        'schema':'J0740_F54_WFF1_SOURCE_PINNED_CONSTANT_J_151v201_SPATIAL_MESH_V1',
        'status':'STARTED',
        'RNS_source_commit':RNS_SHA,
        'F44_source_SHA256':sha(f44),'F53_fine_source_SHA256':sha(f53),
        'WFF1_EOS_table_SHA256':sha(table),
        'coarse_RNS_C_binary_SHA256':sha(binary),
        'coarse_C_J_print_patch':check,
        'coarse_mesh':'MDIV=151,SDIV=301',
        'fine_mesh':'MDIV=201,SDIV=401_SOURCE_REUSED_NOT_RECOMPUTED',
        'fixed_target_J_cgs':target_j,
        'EOS_source':'NEW_F42_CAUSAL_LIFT_GAS_WFF1_HYPOTHESIS_NOT_ORIGINAL_NUCLEAR_EOS',
        'physical_M0':'NOT_ESTABLISHED',
        'global_dynamical_stability':'NOT_ESTABLISHED',
        'matching_rows':[]}
    out.parent.mkdir(parents=True,exist_ok=True)
    def save():out.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    save()
    for density in MATCHED_E15:
        fine_star=matched[str(density)]
        ec=density*1e15
        trace=[]
        item={'ec_e15':density,'fine':{k:fine_star[k] for k in
              ('ec_g_cm3','mass_msun','radius_eq_km','spin_hz','axis_ratio','J_cgs','relative_J_residual')},
              'coarse_C_trace':trace}
        try:
            coarse,trace=solve_at_J(lambda e,r:run_one(binary,table,e,r),
                                    ec,target_j,fine_star['axis_ratio'],trace)
            if abs(coarse['ec_g_cm3']-fine_star['ec_g_cm3'])>1e6:
                raise ValueError('COARSE_RNS_CENTER_DENSITY_DIFFERS_FROM_FINE')
            item.update({
                'coarse':coarse,'status':'MATCHED_BOTH_REAL_C_STARS',
                'coarse_minus_fine_mass_Msun':coarse['mass_msun']-fine_star['mass_msun'],
                'coarse_minus_fine_radius_km':coarse['radius_eq_km']-fine_star['radius_eq_km'],
                'coarse_minus_fine_spin_hz':coarse['spin_hz']-fine_star['spin_hz']})
            print(f"F54 rho={density:.4f} dM={item['coarse_minus_fine_mass_Msun']:.9g} dR={item['coarse_minus_fine_radius_km']:.9g}",flush=True)
        except Exception as exc:
            item.update({'status':'COARSE_MESH_DIRECT_C_STAR_FAILED','error':type(exc).__name__+': '+str(exc)[:250]})
            print(f"F54 rho={density:.4f} FAILED {item['error']}",flush=True)
        report['matching_rows'].append(item)
        save()
    result=summarize_pairs(report['matching_rows'])
    report['mesh_diagnostic']=result
    report['status']=result['status']
    save()
    return report


def main():
    p=argparse.ArgumentParser()
    for name in ('f44','f53','binary','patch','work','out'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    outcome=run(a.f44,a.f53,a.binary,a.patch,a.work,a.out)
    print(json.dumps(outcome['mesh_diagnostic'],sort_keys=True),flush=True)
    if not outcome['status'].startswith('PASS_'):raise SystemExit(2)


if __name__=='__main__':main()

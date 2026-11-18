"""F63 second independent C/RNS 201x401 spacetime grid for original MPA1 fixed-J.

Same original JESTER NPZ and fixed target J, identical central densities as F63
151x301; two grids with distinct direct C equilibrium models. This does not
validate low-pressure source microphysics or source-native X-PSI/Bayes.
"""
from __future__ import annotations
import argparse,json,hashlib,math,sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'rotating_gr'))
from jester_to_rns import from_jester_npz,write_rns
from f63_original_mpa1_fixed_J import sha,SOURCE_SHA,F62_SHA,RNS_COMMIT,fixed_j_at_density,c_call

NEAR_PEAK_E15=(2.048,2.066,2.084,2.102,2.120,2.138,2.156)
MAX_ABS_MASS_DIFF_MSUN=.006
MAX_ABS_RADIUS_DIFF_KM=.09


def pair_gate(a,b):
    if (not all(k in a and k in b for k in ('ec_g_cm3','mass_msun','radius_eq_km','J_cgs','relative_J_residual'))
            or not math.isclose(a['ec_g_cm3'],b['ec_g_cm3'],rel_tol=2e-10)
            or any(not math.isfinite(float(s[k])) for s in (a,b) for k in ('mass_msun','radius_eq_km','J_cgs','relative_J_residual'))):
        raise ValueError('F63_SPATIAL_SOURCE_OR_C_MODEL_INVALID')
    dm=b['mass_msun']-a['mass_msun'];dr=b['radius_eq_km']-a['radius_eq_km']
    passed=(abs(dm)<=MAX_ABS_MASS_DIFF_MSUN and abs(dr)<=MAX_ABS_RADIUS_DIFF_KM
            and abs(b['relative_J_residual'])<1e-5 and abs(a['relative_J_residual'])<1e-5)
    return {'coarse_M_msun':a['mass_msun'],'fine_M_msun':b['mass_msun'],
            'coarse_radius_km':a['radius_eq_km'],'fine_radius_km':b['radius_eq_km'],
            'fine_minus_coarse_mass_msun':dm,'fine_minus_coarse_radius_km':dr,
            'same_rho_c_g_cm3':a['ec_g_cm3'],'fine_J_relative_residual':b['relative_J_residual'],
            'mesh_acceptance':passed}


def fine_turning(rows):
    if len(rows)<5:return {'status':'INSUFFICIENT_FINE_SPATIAL_GRID_STARS'}
    q=sorted(rows,key=lambda v:v['ec_e15']);i=max(range(len(q)),key=lambda j:q[j]['fine']['mass_msun'])
    ok=0<i<len(q)-1 and q[i-1]['fine']['mass_msun']<q[i]['fine']['mass_msun'] and q[i+1]['fine']['mass_msun']<q[i]['fine']['mass_msun']
    return {'status':'FINE_201x401_SAMPLED_FIXED_J_PEAK_BRACKETED' if ok else 'FINE_MESH_TURNING_NOT_RESOLVED',
            'fine_peak_ec_e15':q[i]['ec_e15'],'fine_peak_M_msun':q[i]['fine']['mass_msun'],
            'fine_neighbor_masses':[q[i-1]['fine']['mass_msun'] if i else None,q[i]['fine']['mass_msun'],q[i+1]['fine']['mass_msun'] if i<len(q)-1 else None],
            'physical_dynamic_stability':'NOT_ESTABLISHED'}


def run(source,f63_json,rns,out):
    if sha(source)!=SOURCE_SHA:raise ValueError('F63_FINE_MPA1_SOURCE_SHA_DRIFT')
    base=json.loads(Path(f63_json).read_text())
    if not (base['schema']=='J0740_F63_ORIGINAL_MPA1_PINNED_RNS_CONSTANT_J_V1'
            and base['status']=='SOURCE_ORIGINAL_MPA1_FIXED_J_TURNOVER_NUMERICAL_DIAGNOSTIC_NOT_PHYSICAL_CERTIFICATION'
            and base['source_npz_sha256']==SOURCE_SHA and base['F62_source_json_sha256']==F62_SHA
            and base['fixed_J_turning_summary']['status'].startswith('SAMPLED_CONSTANT_J_TURNOVER')
            and base['physical_EOS_acceptance'].startswith('NOT_ESTABLISHED')
            and base['RNS_commit']==RNS_COMMIT):
        raise ValueError('F63_FINE_SOURCE_C_RNS_ROOT_OR_PHYSICS_LINEAGE_MISMATCH')
    source_stars=[x for x in base['direct_C_constant_J_stars'] if x.get('status','').startswith('DIRECT_C_FIXED_J') and 'mass_msun' in x]
    matches={}
    for ec15 in NEAR_PEAK_E15:
        match=[x for x in source_stars if abs(x['ec_g_cm3']/1e15-ec15)<1e-8]
        if len(match)!=1:raise ValueError('F63_FINE_MISSING_OR_DUPLICATE_COARSE_DENSITY')
        matches[ec15]=match[0]
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    tab,conv=from_jester_npz(source,points=196)
    table=out.parent/'MPA1_F63_fine_grid_original_196.rns'
    write_rns(table,tab)
    report={'schema':'F63_original_MPA1_fixed_J_151x301_vs_201x401_real_C_v1',
           'status':'IN_PROGRESS','source_npz_sha256':SOURCE_SHA,'F63_fixed_J_JSON_sha256':sha(f63_json),
           'fine_RNS_C_binary_sha256':sha(rns),'F63_J_anchor_cgs':base['target_J_cgs'],
           'original_MPA1_crust_physical_validation':'NOT_ESTABLISHED_NEGATIVE_CS2',
           'photon_level_likelihood':'NOT_RUN','seven_original_EOS_Bayes':'NOT_RUN',
           'EOS_table_knot_count_both':196,'coarse_spatial_grid':'151x301','fine_spatial_grid':'201x401',
           'source_RNS_table_sha256':sha(table),'pairs':[]}
    def save():out.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    save()
    for ec15 in NEAR_PEAK_E15:
        orig=matches[ec15]
        fine=fixed_j_at_density(lambda ec,ratio:c_call(rns,table,ec,ratio=ratio),orig['ec_g_cm3'],base['target_J_cgs'],seed=orig['axis_ratio'])
        p=pair_gate(orig,fine)
        row={'ec_e15':ec15,'coarse':{k:orig[k] for k in ('ec_g_cm3','mass_msun','radius_eq_km','J_cgs','spin_hz','relative_J_residual','axis_ratio')},
             'fine':{k:fine[k] for k in ('ec_g_cm3','mass_msun','radius_eq_km','J_cgs','spin_hz','relative_J_residual','axis_ratio','direct_C_evaluations')},
             'comparison':p}
        report['pairs'].append(row);save()
        print('F63 FINE',ec15,'delta M',p['fine_minus_coarse_mass_msun'],'delta R(km)',p['fine_minus_coarse_radius_km'],'pass',p['mesh_acceptance'],flush=True)
    report['fine_fixed_J_turning_summary']=fine_turning(report['pairs'])
    report['max_abs_spatial_mass_sensitivity_msun']=max(abs(x['comparison']['fine_minus_coarse_mass_msun']) for x in report['pairs'])
    report['max_abs_spatial_radius_sensitivity_km']=max(abs(x['comparison']['fine_minus_coarse_radius_km']) for x in report['pairs'])
    report['status']='TWO_REAL_RNS_SPATIAL_GRIDS_FIXED_J_PEAK_BRACKETED_NOT_PHYSICAL_EOS_CERT' if (
        all(x['comparison']['mesh_acceptance'] for x in report['pairs']) and
        report['fine_fixed_J_turning_summary']['status']=='FINE_201x401_SAMPLED_FIXED_J_PEAK_BRACKETED') else 'SPATIAL_GRID_OR_FIXED_J_TURNOVER_NOT_ACCEPTED'
    save()
    return report

def main():
    p=argparse.ArgumentParser()
    for k in ('source','f63','rns','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();r=run(a.source,a.f63,a.rns,a.out)
    print(json.dumps({'status':r['status'],'fine_turning':r['fine_fixed_J_turning_summary']},sort_keys=True),flush=True)
    if not r['status'].startswith('TWO_REAL_'):raise SystemExit('F63 fine spatial independent physics not accepted')

if __name__=='__main__':main()
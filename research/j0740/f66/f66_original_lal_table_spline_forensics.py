"""F66: distinguish source-node reversal from cubic-spline overshoot on ORIGINAL EOS.

Use F65 directly measured LALSuite 7.26.4 E(P), dE/dP and the exact
installed LALSuite .dat source tables, not historical tables alone.  Independently
reconstruct the non-shape-preserving natural cubic interpolation with SciPy,
then contrast with monotone PCHIP as a DIAGNOSTIC ONLY.  Does not alter any
of the 7 original EOS or certify an alternative EOS/star.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, sys
from pathlib import Path
import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator

EOS = ('APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2')
BAD = set(EOS)-{'APR4_EPP'}
F65_SHA = '6e35cd5ea33d3f3e9e3d0fb7cee585f809638e4b8507804bd7c0789148cd6e74'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_rows(path):
    raw=Path(path).read_text('utf-8')
    lines=[l.strip() for l in raw.splitlines() if l.strip() and not l.lstrip().startswith('#')]
    cols=[l.split() for l in lines]
    if not cols or not all(len(c)==2 for c in cols):
        raise ValueError('F66_NOT_TWO_COLUMN_NATIVE_LAL_EOS_SOURCE_'+str(path))
    tab=np.asarray([[float(t) for t in c] for c in cols],dtype=np.float64)
    if (len(tab)<20 or not np.isfinite(tab).all() or (tab<=0).any()
        or (np.diff(tab[:,0])<=0).any()):
        raise ValueError('F66_INVALID_RAW_TABULAR_PRESSURE_OR_VALUES_'+str(path))
    return tab


def find_installed_sources(root:Path):
    """Find current pip-install LALSuite .dat, never use unpinned archive as proxy."""
    if not root.exists() or not root.is_dir():raise ValueError('F66_INVALID_INSTALLED_ROOT')
    hits=[]
    marker='LALSimNeutronStarEOS_MPA1.dat'
    for base,dirs,files in os.walk(root):
        dirs[:]=[d for d in dirs if d not in {'.git','__pycache__','node_modules','.cache','test','tests'}]
        if marker in files: hits.append(Path(base))
    candidate=[]
    for d in hits:
        if all((d/('LALSimNeutronStarEOS_'+n+'.dat')).is_file() for n in EOS):
            candidate.append(d)
    if not candidate:
        raise ValueError('F66_CURRENT_NATIVE_LAL_TABLE_SET_MISSING')
    # Multiple identical package installations are acceptable; conflicting data are not.
    candidate.sort(key=str)
    if len(candidate)>1:
        reference={n:digest(candidate[0]/('LALSimNeutronStarEOS_'+n+'.dat')) for n in EOS}
        for d in candidate[1:]:
            if any(digest(d/('LALSimNeutronStarEOS_'+n+'.dat'))!=reference[n] for n in EOS):
                raise ValueError('F66_CONFLICTING_INSTALLED_LAL_SOURCE_TABLES')
    return candidate[0]


def evaluate_interpolants(tab,p):
    """Same raw pressure and epsilon; no source EOS repair."""
    rawp,rawe=np.asarray(tab,float).T
    p=np.asarray(p,float)
    if (np.any(p<=rawp[0]) or np.any(p>=rawp[-1]) or
        np.any(np.diff(p)<=0)):
        raise ValueError('F66_PRESSURES_OUTSIDE_NATIVE_RAW_TABLE')
    p_scale=1e15; e_scale=1e13
    natural=CubicSpline(rawp*p_scale,rawe*e_scale,bc_type='natural')
    monotone=PchipInterpolator(rawp*p_scale,rawe*e_scale)
    cubic_e=natural(p*p_scale)/e_scale
    cubic_der=natural(p*p_scale,1)*p_scale/e_scale
    pchip_e=monotone(p*p_scale)/e_scale
    pchip_der=monotone(p*p_scale,1)*p_scale/e_scale
    if not all(np.isfinite(t).all() for t in [cubic_e,cubic_der,pchip_e,pchip_der]):
        raise ValueError('F66_INVALID_SPLINE_OUTPUT')
    return cubic_e,cubic_der,pchip_e,pchip_der


def compare_sources(f65,raw_tables):
    if f65.get('status')!='F65_DIRECT_LAL_CRUST_SIX_OF_SEVEN_NEGATIVE_LOCALIZED_FINITE_SCAN_NOT_PHYSICAL_CERT':
        raise ValueError('F66_F65_SOURCE_BAD_STATUS')
    if set(f65.get('eos',{}))!=set(EOS):raise ValueError('F66_F65_EOS_SET_DRIFT')
    out={'schema':'J0740_F66_ORIGINAL_LAL_TABULAR_SPLINE_FORENSICS_V1',
         'status':'IN_PROGRESS', 'source_original_not_F42':True,
         'scientific_scope':'installed LALSuite raw table vs direct F65 LAL C E(P),dE/dP, GSL-natural spline reconstruction and PCHIP diagnostic only',
         'original_physical_source_EOS_modified':False,
         'source_native_XPSI_photon_likelihood':'NOT_RUN',
         'original_seven_EOS_Bayes':'NOT_RUN',
         'full_physical_EOS_admission':'NOT_ESTABLISHED',
         'continuous_causality_certification':'NOT_RUN','eos':{}}
    common=[]
    for name in EOS:
        d=f65['eos'][name]
        p=np.asarray(d['diagnostic_p_grid_geom'],float)
        e=np.asarray(d['diagnostic_e_grid_geom'],float)
        dedp=np.asarray(d['diagnostic_dedp_grid'],float)
        if len(p)!=1201 or e.shape!=p.shape or dedp.shape!=p.shape:
            raise ValueError('F66_F65_DIRECT_GRID_DRIFT_'+name)
        tab=raw_tables[name]
        ce,cd,pe,pd=evaluate_interpolants(tab,p)
        rel_e=float(np.max(np.abs(ce-e)/np.maximum(abs(e),1e-300)))
        norm_d=float(np.max(np.abs(cd-dedp)/np.maximum(abs(dedp),1.0)))
        native_neg=(dedp<0)
        cubic_neg=(cd<0)
        pchip_neg=(pd<0)
        all_source_increasing=bool(np.all(np.diff(tab[:,1])>0))
        shared_low=[(float(a),float(b)) for a,b in tab if 1e-17<=a<=5e-16]
        common.append(shared_low)
        out['eos'][name]={
            'raw_lal_data_sha256':None,'raw_lal_data_row_count':int(len(tab)),
            'raw_source_energy_nonincreasing_edges':int(np.count_nonzero(np.diff(tab[:,1])<=0)),
            'raw_source_pressure_nonincreasing_edges':int(np.count_nonzero(np.diff(tab[:,0])<=0)),
            'source_tabular_all_energy_monotone':all_source_increasing,
            'raw_local_2_column_tabular_rows':[[float(a),float(b)] for a,b in tab if 3e-16<a<8e-16],
            'LAL_F65_direct_negative_samples':int(native_neg.sum()),
            'natural_cubic_negative_derivative_samples':int(cubic_neg.sum()),
            'PCHIP_diagnostic_negative_derivative_samples':int(pchip_neg.sum()),
            'cubic_vs_F65_derivative_sign_disagreements':int(np.count_nonzero(native_neg!=cubic_neg)),
            'max_relative_cubic_vs_F65_energy_discrepancy':rel_e,
            'max_scale_1_cubic_vs_F65_dedp_discrepancy':norm_d,
            'cubic_reproduced_F65_native_C_to_tolerance':bool(rel_e<=1e-7 and norm_d<=1e-5 and not np.any(native_neg!=cubic_neg)),
            'PCHIP_only_a_mathematical_sensitivity_test_NOT_PHYSICAL_EOS':True
        }
    exact_same_low=all(common[0]==v for v in common[1:])
    out['six_common_lowpressure_source_rows_equal']=all(common[1]==v for v in common[2:])
    out['six_common_lowpressure_row_count']=len(common[1])
    out['APR4_same_raw_lowP_as_six']=exact_same_low
    out['all_seven_cubic_reproduce_LAL_F65']=all(v['cubic_reproduced_F65_native_C_to_tolerance'] for v in out['eos'].values())
    out['raw_source_all_positive_secants']=all(v['source_tabular_all_energy_monotone'] for v in out['eos'].values())
    out['six_negative_cubic_reproduced']=all(out['eos'][n]['LAL_F65_direct_negative_samples']==205 and out['eos'][n]['natural_cubic_negative_derivative_samples']==205 for n in BAD)
    out['PCHIP_six_no_negative_derivative']=all(out['eos'][n]['PCHIP_diagnostic_negative_derivative_samples']==0 for n in BAD)
    out['apparent_common_negative_crust_origin']='UNRESOLVED_UNTIL_REPRODUCTION'
    if out['all_seven_cubic_reproduce_LAL_F65'] and out['raw_source_all_positive_secants'] and out['six_negative_cubic_reproduced'] and out['PCHIP_six_no_negative_derivative'] and out['six_common_lowpressure_source_rows_equal']:
        out['status']='ORIGINAL_RAW_TABLE_POSITIVE_SECANTS_GSL_NATURAL_CUBIC_OVERSHOOT_REPRODUCED_NOT_EOS_REPAIRED'
        out['apparent_common_negative_crust_origin']='REPRODUCED_FROM_NON_SHAPE_PRESERVING_NATURAL_CUBIC_INTERPOLATION_OF_MONOTONE_RAW_EOS'
    else:
        out['status']='SOURCE_LEVEL_MECHANISM_NOT_YET_FULLY_REPRODUCED'
    return out


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--f65',type=Path,required=True); a.add_argument('--installed-root',type=Path,default=Path(sys.prefix))
    a.add_argument('--out',type=Path,required=True)
    cfg=a.parse_args()
    if digest(cfg.f65)!=F65_SHA:raise ValueError('F66_F65_FULL_RAW_SOURCE_HASH_CHANGED')
    f65=json.loads(cfg.f65.read_text())
    source=find_installed_sources(cfg.installed_root)
    original={name:source/('LALSimNeutronStarEOS_'+name+'.dat') for name in EOS}
    tables={name:source_rows(f) for name,f in original.items()}
    d=compare_sources(f65,tables)
    d['installed_lalsuite_source_dir']=str(source)
    d['installed_wheel_source_file_sha256']={name:digest(f) for name,f in original.items()}
    d['f65_direct_LAL_781016bytes_sha256']=F65_SHA
    for name in EOS:d['eos'][name]['raw_lal_data_sha256']=digest(original[name])
    cfg.out.parent.mkdir(parents=True,exist_ok=True)
    cfg.out.write_text(json.dumps(d,sort_keys=True,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':d['status'],'six_common_raw_rows':d['six_common_lowpressure_row_count'],
        'cubic_reproduced':d['all_seven_cubic_reproduce_LAL_F65'],
        'raw_monotone':d['raw_source_all_positive_secants'],
        'signs':{n:[x['LAL_F65_direct_negative_samples'],x['natural_cubic_negative_derivative_samples'],x['PCHIP_diagnostic_negative_derivative_samples']] for n,x in d['eos'].items()}},sort_keys=True))
    if d['status']!='ORIGINAL_RAW_TABLE_POSITIVE_SECANTS_GSL_NATURAL_CUBIC_OVERSHOOT_REPRODUCED_NOT_EOS_REPAIRED':
        raise SystemExit('F66_SOURCE_CAUSE_NOT_FULLY_REPRODUCED_DO_NOT_CLAIM_SUCCESS')
if __name__=='__main__':main()
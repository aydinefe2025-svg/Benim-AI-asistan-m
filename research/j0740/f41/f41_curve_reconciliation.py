"""F41: reproducible F39 (25-point) vs independently archived 165-root RNS
cross-check and F38 relative-likelihood restriction, without re-running RNS.

Never interprets this as seven-EOS posterior. Source table hashes differ, thus
geometric agreement does not establish source-EOS identity or native physics.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.integrate import simpson
from scipy.stats import norm

F39_HASH = '6402c4fd97baf1b0766e1f1d5ccb3642b5b50de2d87789f50277b916896033c2'
F38_HASH = '4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307'
ROOT165_HASH = '2c12790459c62c3d758dcbe8e3a425cec6f8328dec3c6701af28e1ca13a96d5c'
SOURCE_NATIVE_PIN = 'e6768650ce992abfd1153a6833857572fe5cd230'
SOURCE_NAMES = ('APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2')
M_MU, M_SIG = 2.082, 0.0703


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def validate_source_files(p39,p38,p165):
    for path,expected in [(p39,F39_HASH),(p38,F38_HASH),(p165,ROOT165_HASH)]:
        if sha256(path)!=expected: raise ValueError('SOURCE_ARCHIVE_SHA_MISMATCH:'+str(path))
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None: raise ValueError('SOURCE_ZIP_CRC_INVALID')


def ascending_domain(roots):
    """Use only the strictly increasing M(rho_c) prefix, no mass sorting.

    A small numerical near-peak backtrack is excluded rather than folded onto
    the same M grid. This is a numerical branch, *not a dynamical stability test*.
    """
    a=np.asarray([x['central_energy_density_g_cm3'] for x in roots],float)
    m=np.asarray([x['mass_msun'] for x in roots],float)
    r=np.asarray([x['radius_eq_km'] for x in roots],float)
    f=np.asarray([x['spin_hz'] for x in roots],float)
    if not (len(a)>=50 and all(x.shape==a.shape for x in [m,r,f])
            and np.isfinite(np.concatenate([a,m,r,f])).all() and np.all(np.diff(a)>0)
            and np.all((m>0)&(m<4)) and np.all((r>4)&(r<30))
            and np.all(abs(f-346.536369)<.1)):
        raise ValueError('165_ROOT_PHYSICS_OR_GRID_FAILED')
    bad=np.where(np.diff(m)<=0)[0]
    end=int(bad[0]+1) if len(bad) else len(m)
    if end<60:raise ValueError('UNUSABLY_SHORT_RISING_BRANCH')
    mass,radius=m[:end],r[:end]
    if np.any(np.diff(mass)<=0):raise AssertionError('INTERNAL_MONOTONE_BRANCH')
    return mass,radius, {'sampled_full_sweep_nodes':len(m),'first_mass_reversal_after_index':end-1,
                          'usable_rising_prefix_nodes':end,
                          'usable_rising_prefix_mass_range_msun':[float(mass[0]),float(mass[-1])],
                          'sampled_turning_point_not_global_stability':True}


def compare_at_same_masses(f39_curve,mass,radius):
    target=np.asarray([row['target_mass_msun'] for row in f39_curve],dtype=float)
    r39=np.asarray([row['radius_eq_km'] for row in f39_curve],dtype=float)
    if not (len(target)==25 and np.all(np.diff(target)>0) and mass[0]<=target[0] and mass[-1]>=target[-1]):
        raise ValueError('F39_TARGET_MASS_OUTSIDE_165_RISING_DOMAIN')
    r165=np.interp(target,mass,radius)
    delta_m=1000*(r165-r39)
    return target,r165,{'count':len(target),'max_abs_delta_m':float(np.max(abs(delta_m))),
      'median_abs_delta_m':float(np.median(abs(delta_m))),
      'rms_delta_m':float(np.sqrt(np.mean(delta_m**2))),
      'all_point_differences_m':[float(x) for x in delta_m],
      'source_table_identity_inferred':False}


def window_pdf(m,lo,hi):
    z=(norm.cdf((hi-M_MU)/M_SIG)-norm.cdf((lo-M_MU)/M_SIG))
    if not(lo<hi and z>0):raise ValueError('BAD_MASS_WINDOW')
    return norm.pdf((m-M_MU)/M_SIG)/(M_SIG*z)


def evaluate_f38_grid(zipped_grid,curve_masses,r39,r165):
    with np.load(io.BytesIO(zipped_grid),allow_pickle=False) as z:
        masses=z['mass_centres']
        radii=z['radius_centres_km']
        L=z['relative_likelihood_L_over_Z'].astype(float)
        support=z['hard_source_support'].astype(bool)
    if (masses.shape!=(401,) or radii.shape!=(581,) or L.shape!=(401,581)
            or np.any(~np.isfinite(L)) or np.any(L<0)):
        raise ValueError('F38_GRID_INVALID')
    results={}
    interp=RegularGridInterpolator((masses,radii),L,method='linear',bounds_error=True)
    lo,hi=curve_masses[0],curve_masses[-1]
    pdf=window_pdf(curve_masses,lo,hi)
    integral_q=float(simpson(pdf,x=curve_masses))
    if abs(integral_q-1)>1e-4:raise ValueError('F39_MASS_NORMALIZATION_NOT_REPRODUCED')
    for label,rr in [('F39_25_direct',r39),('sweep165_interpolated',r165)]:
        mi=np.searchsorted(masses,curve_masses,side='right')-1
        ri=np.searchsorted(radii,rr,side='right')-1
        if (np.any(mi<0) or np.any(mi>=400) or np.any(ri<0) or np.any(ri>=580)):
            raise ValueError('F38_GRID_OUT_OF_BOUNDS_'+label)
        if not (support[mi,ri] & support[mi+1,ri] & support[mi,ri+1] & support[mi+1,ri+1]).all():
            raise ValueError('F38_SOURCE_PRIOR_MASK_'+label)
        likelihood=interp(np.column_stack([curve_masses,rr]))
        val=float(simpson(pdf*likelihood,x=curve_masses))
        if not (math.isfinite(val) and val>=0):raise ValueError('NONFINITE_EVIDENCE_'+label)
        results[label]=val
    results['cross_curve_relative_difference_percent']=100*(results['sweep165_interpolated']/results['F39_25_direct']-1)
    results['same_explicit_mass_window_msun']=[float(lo),float(hi)]
    return results


def physical_admissibility(source_eos):
    """Classify exact JESTER TABLES, not theoretical EOS families or physical stars."""
    if set(source_eos)!=set(SOURCE_NAMES):raise ValueError('NOT_EXACT_PINNED_SEVEN_EOS')
    entries={}
    for name in SOURCE_NAMES:
        x=source_eos[name]
        onstar=x['sampled_source_screen']=='SAMPLED_PASS_NOT_GLOBAL_PROOF'
        counts={key:int(x[key]) for key in ['negative_native_cs2_below_center','superluminal_native_cs2_below_center',
            'negative_secants_below_center','superluminal_secants_below_center',
            'native_cs2_nonpositive_nodes_global','native_cs2_superluminal_nodes_global',
            'source_energy_nonincreasing_edges_global']}
        # Must also see globally zero sampled sound-speed failures (neither
        # continuous physical proof nor permission to infer model evidence).
        table_global_clean=all(counts[k]==0 for k in ['native_cs2_nonpositive_nodes_global',
            'native_cs2_superluminal_nodes_global','source_energy_nonincreasing_edges_global'])
        entries[name]={'source_sampled_onstar_pass':onstar,
          'source_whole_tabulation_node_causality_pass':table_global_clean,
          'global_physical_model_acceptance':'NOT_ESTABLISHED', 'source_counts':counts}
    return {'per_eos':entries,'onstar_sampled_screen_pass_count':sum(v['source_sampled_onstar_pass'] for v in entries.values()),
      'raw_whole_table_node_screen_pass_count':sum(v['source_whole_tabulation_node_causality_pass'] for v in entries.values()),
      'fully_physically_admissible_seven_model_count':'NOT_ESTABLISHED',
      'interpretation':'Unmodified JESTER NPZ data only; original nuclear EOS theory is not excluded by table artifacts. No source EOS family becomes validated by passing a finite-node screen.'}


def audit(p39,p38,p165,source_gate):
    validate_source_files(p39,p38,p165)
    if source_gate['source_commit']!=SOURCE_NATIVE_PIN:raise ValueError('SOURCE_GATE_PIN_MISMATCH')
    with zipfile.ZipFile(p39) as z:a=json.loads(z.read('F39_direct_RNS_fixed_spin_apr4_conditional_likelihood.json'))
    with zipfile.ZipFile(p165) as z:b=json.loads(z.read('J0740_APR4_FIXED_FREQUENCY_CURVE_F38_INTEGRAL.json'))
    if a['status']!='PASS_CONDITIONAL_APR4_SOURCE_MARGINALIZED_CURVE_PROBE_NOT_SEVEN_EOS_BAYES':raise ValueError('F39_STATUS_UNEXPECTED')
    if b['status']!='PASS_CONDITIONAL_APPROXIMATE_F38_CURVE_INTEGRAL':raise ValueError('SWEEP_STATUS_UNEXPECTED')
    if a['source_RNS_EOS_sha256']==b['inputs']['rns_table_sha256']:
        same_sha=True
    else:
        same_sha=False
    mass,radius,branch=ascending_domain(b['central_density_sweep'])
    f39mass=np.asarray([x['target_mass_msun'] for x in a['curve']])
    f39r=np.asarray([x['radius_eq_km'] for x in a['curve']])
    target,r165,geom=compare_at_same_masses(a['curve'],mass,radius)
    if not np.allclose(target,f39mass,atol=1e-12,rtol=0):raise AssertionError('internal target mass')
    comparisons={}
    with zipfile.ZipFile(p38) as z:
        files=[x for x in z.namelist() if x.startswith('posterior_prior_ratio_') and x.endswith('.npz')]
        if len(files)!=6:raise ValueError('MISSING_F38_SIX_KDE_GRIDS')
        for f in sorted(files):
            comparisons[f]=evaluate_f38_grid(z.read(f),target,f39r,r165)
            old=a['likelihood_grids'][f]['curve_conditional_L_over_Z']
            if abs(comparisons[f]['F39_25_direct']-old)>1e-10:
                raise AssertionError('F39_OLD_INTEGRAL_NOT_REPRODUCED:'+f)
    return {'schema':'J0740_F41_two_source_curve_reconciliation_v1','status':'PASS_NUMERICAL_CROSS_CHECK_NOT_SEVEN_EOS_BAYES',
      'archive_sha256':{'F39':F39_HASH,'F38':F38_HASH,'independent_165_RNS':ROOT165_HASH},
      'model_labels':{'F39':a['experimental_eos'],'165':b['model']},
      'source_EOS_table_sha256':{'F39_table':a['source_RNS_EOS_sha256'],'165_table':b['inputs']['rns_table_sha256']},
      'identical_table_sha256':same_sha,
      'explicit_guard':'Different table SHA: no EOS object identity. Geometrical agreement is not thermodynamic model proof.',
      'branch':branch,'geom_cross_check':geom,
      'F38_six_grids_common_window_cross_check':comparisons,
      'max_abs_F38_integral_percent_difference':max(abs(v['cross_curve_relative_difference_percent']) for v in comparisons.values()),
      'physical_source_7EOS_gate':physical_admissibility(source_gate['eos']),
      'limitations':['No native X-PSI photon model re-evaluation','No physical six-EOS repairs or TOV/RNS reruns','Different EOS table hashes: numerical MR agreement not a source-physics certificate','No physical stability proof','NO final 7-EOS posterior or Bayes factors'],
      'final_seven_EOS_Bayes':'NOT_RUN'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--f39',type=Path,required=True);p.add_argument('--f38',type=Path,required=True)
    p.add_argument('--roots165',type=Path,required=True);p.add_argument('--source-gate',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    gate=json.loads(a.source_gate.read_text())
    output=audit(a.f39,a.f38,a.roots165,gate)
    a.out.write_text(json.dumps(output,indent=2,ensure_ascii=False,sort_keys=True)+'\n')
    print(json.dumps({'status':output['status'],'max_delta_m':output['geom_cross_check']['max_abs_delta_m'],
      'max_likelihood_percent':output['max_abs_F38_integral_percent_difference'],
      'onstar_source_screen_pass':output['physical_source_7EOS_gate']['onstar_sampled_screen_pass_count'],
      'full_table_node_screen_pass':output['physical_source_7EOS_gate']['raw_whole_table_node_screen_pass_count']}))
if __name__=='__main__': main()

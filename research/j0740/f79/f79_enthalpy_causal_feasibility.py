#!/usr/bin/env python3
"""F79: interpolant-independent necessary enthalpy gates on 7 native JESTER EOS.

For a differentiable cold causal barotrope dE/dP>=1, on each exact knot
(P0,E0,H0),(P1,E1,H1), let d=P1-P0>0, e=E1-E0>=d. Since
E0+(P-P0) <= E(P) <= E1-(P1-P), the pseudoenthalpy increment
H1-H0=integral dP/(E(P)+P) MUST lie between:
  .5*log1p(2*d/(E1+P0-d)) and .5*log1p(2*d/(E0+P0)).
For a merely monotone E(P), the weaker bounds are
  log1p(d/(E1+P0)) and log1p(d/(E0+P0)).
These are NECESSARY, not sufficient conditions. They do not certify physics.

Loads unchanged original byte-pinned JESTER NPZ and original RNS C artifacts.
No new stars, EOS repair, TOV, X-PSI photons, or EOS inference.
"""
from __future__ import annotations
import argparse, hashlib, io, json, math, sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
if (HERE.parent/'f75').is_dir():
    sys.path.insert(0,str(HERE.parent/'f75'))
from f75_original_eos_causality_gate import (EOS, load_original_stars,
                                        require_sha, GEOM_E_TO_G_CM3)
SCHEMA='J0740_F79_NATIVE_P_E_H_CAUSAL_INTERVAL_NECESSITY_V1'
RTOL=1.e-8
ATOL=5.e-15


def _fails(actual, lower, upper, *, rtol=RTOL, atol=ATOL):
    # Avoid false physical claims from rounding around thin envelopes.
    scale=np.maximum(np.maximum(abs(lower),abs(upper)),abs(actual))
    tol=atol+rtol*scale
    low=actual<lower-tol
    high=actual>upper+tol
    return low,high,np.maximum(np.maximum(lower-actual,actual-upper),0.0)


def inspect_knots(p,e,h, *, rtol=RTOL,atol=ATOL):
    p,e,h=[np.asarray(a,dtype=np.float64) for a in (p,e,h)]
    if not (p.ndim==e.ndim==h.ndim==1 and len(p)==len(e)==len(h) and len(p)>=3):
        raise ValueError('INVALID_SOURCE_KNOT_SHAPES')
    if any(not np.isfinite(a).all() for a in (p,e,h)):
        raise ValueError('NONFINITE_SOURCE_KNOT')
    if np.any(p<=0) or np.any(e<=0) or np.any(np.diff(p)<=0):
        raise ValueError('NONPOSITIVE_NONMONOTONE_PRESSURE_ENERGY')
    if np.any(np.diff(h)<=0):
        raise ValueError('NONINCREASING_NATIVE_H')
    if not (0<=rtol<=1e-5 and 0<=atol<=1e-11):
        raise ValueError('INVALID_FAIL_CLOSED_TOLERANCE')
    p0=p[:-1];e0=e[:-1];p1=p[1:];e1=e[1:]
    dp=p1-p0; de=e1-e0;dh=np.diff(h)
    existing_bad_de=(de<=0)
    existing_superluminal=(de>0)&(de < dp*(1-1e-10))
    eligible=(de >= dp*(1-1e-10))&(de>0)
    # Exact integrated lower/upper enthalpy envelopes for causal dE/dP>=1.
    if np.any((e1+p0-dp)<=0): raise ValueError('INVALID_CAUSAL_ENVELOPE_DENOM')
    causal_lo=.5*np.log1p(2*dp/(e1+p0-dp))
    causal_hi=.5*np.log1p(2*dp/(e0+p0))
    if np.any(causal_lo[eligible]>causal_hi[eligible]+1e-12):
        raise ValueError('INVERTED_CAUSAL_ENVELOPE')
    c_low,c_high,c_gap=_fails(dh,causal_lo,causal_hi,rtol=rtol,atol=atol)
    c_low &= eligible;c_high &= eligible
    c_bad=c_low|c_high
    # Weaker monotone E(P) gate even when c_s^2<1 is not imposed.
    mono=de>0
    mono_lo=np.log1p(dp/(e1+p0));mono_hi=np.log1p(dp/(e0+p0))
    m_low,m_high,m_gap=_fails(dh,mono_lo,mono_hi,rtol=rtol,atol=atol)
    m_low &= mono;m_high &= mono
    m_bad=m_low|m_high
    return {'de_nonpositive':existing_bad_de,
            'secant_superluminal':existing_superluminal,
            'causal_envelope_eligible':eligible,
            'causal_enthalpy_below':c_low,'causal_enthalpy_above':c_high,
            'causal_enthalpy_violation':c_bad,
            'monotone_enthalpy_below':m_low,'monotone_enthalpy_above':m_high,
            'monotone_enthalpy_violation':m_bad,
            'causal_enthalpy_bound_min':causal_lo,
            'causal_enthalpy_bound_max':causal_hi,
            'monotone_enthalpy_bound_min':mono_lo,
            'monotone_enthalpy_bound_max':mono_hi,
            'source_enthalpy_increment':dh,
            'causal_enthalpy_max_pointwise_abs_gap':float(np.max(c_gap[c_bad])) if np.any(c_bad) else 0.,
            'monotone_enthalpy_max_pointwise_abs_gap':float(np.max(m_gap[m_bad])) if np.any(m_bad) else 0.,
            'source_upper_density_for_interval_g_cm3':np.maximum(e0,e1)*GEOM_E_TO_G_CM3}


def summary_for_real_centres(source_dir, artifacts_dir, source_manifest, artifact_manifest):
    mf=json.loads(Path(source_manifest).read_text())
    af=json.loads(Path(artifact_manifest).read_text())
    if mf['pinned_commit']!=af['original_JESTER_commit'] or set(mf['records'])!=set(EOS):
        raise ValueError('SOURCE_COMMIT_OR_EOS_IDENTITY')
    out={'schema':SCHEMA,'source_commit':mf['pinned_commit'],
         'original_RNS_commit':af['original_RNS_commit'],
         'theorem':'For any smooth cold causal E(P), dE/dP>=1 and dH/dP=1/(E+P). Between exact source knots, necessary integrated enthalpy lies between causal envelopes calculated from endpoint E and P. Weaker monotone-only envelopes also tested.',
         'enthalpy_convention':'native JESTER h treated as LALSuite pseudoenthalpy; any inconsistency is of the sampled numerical representation, not direct raw microscopic physics',
         'numeric_tolerance':{'relative':RTOL,'absolute':ATOL},
         'original_star_count':0,'original_numerical_source_rejected_stars':0,
         'candidate_without_endpoint_obstruction':0,
         'models':{},'continuous_physical_EOS_admissibility':'NOT_ESTABLISHED',
         'native_XPSI_photon_inference':'NOT_RUN','BPS_core_phase_match':'NOT_RUN',
         'new_RNS_rotating_solver':'NOT_RUN','physical_seven_EOS_Bayes':'NOT_RUN'}
    for name in EOS:
        data=(Path(source_dir)/(name+'.npz')).read_bytes()
        require_sha(data,mf['records'][name]['sha256'],'ORIGINAL_NATIVE_JESTER_'+name)
        a=np.load(io.BytesIO(data),allow_pickle=False)
        if str(a['eos_name'])!=name or str(a['source'])!='LALSimulation':
            raise ValueError('ORIGINAL_LAL_SOURCE_LABEL_CHANGED')
        p,e,h=(a[k] for k in ('p','e','h'))
        gate=inspect_knots(p,e,h)
        stars, origin=load_original_stars(Path(artifacts_dir),af,name)
        if origin['source_original_npz_sha256']!=mf['records'][name]['sha256']:
            raise ValueError('RNS_SOURCE_EOS_SHA_MISMATCH')
        own={k:gate[k] for k in ('de_nonpositive','secant_superluminal','causal_enthalpy_violation','monotone_enthalpy_violation')}
        per_star=[]
        for index,s in enumerate(stars):
            if abs(s['spin_residual_hz'])>s['allowed_spin_residual_hz']+1e-9:
                raise ValueError('ORIGINAL_C_STAR_SPIN_TOLERANCE_DRIFT')
            ec=s['central_energy_density_g_cm3']
            if not np.isfinite(ec) or ec<=0: raise ValueError('BAD_REAL_C_STAR_CENTRE')
            enclosed=gate['source_upper_density_for_interval_g_cm3']<=ec*(1+1e-14)
            if not np.any(enclosed): raise ValueError('NO_AUTHENTIC_SOURCE_INTERVALS_BELOW_STAR_CENTRE')
            sub={k:int(np.count_nonzero(v&enclosed)) for k,v in own.items()}
            baseline=(sub['de_nonpositive']>0 or sub['secant_superluminal']>0)
            anybad=(baseline or sub['causal_enthalpy_violation']>0)
            per_star.append({'original_C_star_index':index,'mass_msun':float(s['mass_msun']),
                             'central_density_g_cm3':float(ec),
                             'fully_enclosed_interval_count':int(enclosed.sum()),
                             **sub,
                             'F77_secant_gate_fail':bool(baseline),
                             'F79_enthalpy_gate_additional_fail':bool(sub['causal_enthalpy_violation']>0 and not baseline),
                             'combined_source_representation_needed_conditions_fail':bool(anybad),
                             'source_numerical_model_physical_certified':False})
        keys=['de_nonpositive','secant_superluminal','causal_enthalpy_violation','monotone_enthalpy_violation']
        col={key:int(np.count_nonzero(gate[key])) for key in keys}
        bad=[s for s in per_star if s['combined_source_representation_needed_conditions_fail']]
        adds=[s for s in per_star if s['F79_enthalpy_gate_additional_fail']]
        un=[s for s in per_star if not s['combined_source_representation_needed_conditions_fail']]
        ivs=[]
        for i in range(len(p)-1):
            if not (gate['causal_enthalpy_violation'][i] or gate['monotone_enthalpy_violation'][i]
                    or gate['de_nonpositive'][i] or gate['secant_superluminal'][i]):
                continue
            ivs.append({'i':i,'p0':float(p[i]),'p1':float(p[i+1]),
               'e0':float(e[i]),'e1':float(e[i+1]),
               'upper_energy_density_g_cm3':float(gate['source_upper_density_for_interval_g_cm3'][i]),
               'de_nonpositive':bool(gate['de_nonpositive'][i]),
               'secant_superluminal':bool(gate['secant_superluminal'][i]),
               'causal_enthalpy_violation':bool(gate['causal_enthalpy_violation'][i]),
               'monotone_enthalpy_violation':bool(gate['monotone_enthalpy_violation'][i]),
               'native_delta_h':float(gate['source_enthalpy_increment'][i]),
               'causal_lower':float(gate['causal_enthalpy_bound_min'][i]),
               'causal_upper':float(gate['causal_enthalpy_bound_max'][i]),
               'monotone_lower':float(gate['monotone_enthalpy_bound_min'][i]),
               'monotone_upper':float(gate['monotone_enthalpy_bound_max'][i])})
        out['models'][name]={
            'native_source_sha256':mf['records'][name]['sha256'],
            'original_RNS_JSON_sha256':af['artifacts'][name]['json_sha256'],
            'source_knot_count':len(p),'source_intervals':len(p)-1,
            'source_interval_violation_counts':col,
            'first_causal_h_bad_upper_density_g_cm3':float(np.min(gate['source_upper_density_for_interval_g_cm3'][gate['causal_enthalpy_violation']])) if col['causal_enthalpy_violation'] else None,
            'max_native_enthalpy_interval_outside_causal_bound_abs':gate['causal_enthalpy_max_pointwise_abs_gap'],
            'max_native_enthalpy_interval_outside_monotone_bound_abs':gate['monotone_enthalpy_max_pointwise_abs_gap'],
            'original_C_star_count':len(per_star),
            'F77_secant_failed_C_star_count':sum(x['F77_secant_gate_fail'] for x in per_star),
            'F79_C_star_count_with_enthalpy_bound_violation':sum(x['causal_enthalpy_violation']>0 for x in per_star),
            'F79_additional_C_star_count_not_already_F77':len(adds),
            'combined_necessary_condition_C_star_fail_count':len(bad),
            'C_stars_with_no_source_knot_gate_violation_count':len(un),
            'source_problem_intervals':ivs,
            'all_real_C_stars':per_star,
            'physical_model_acceptance':'NOT_ESTABLISHED'}
        out['original_star_count']+=len(per_star)
        out['original_numerical_source_rejected_stars']+=len(bad)
        out['candidate_without_endpoint_obstruction']+=len(un)
    if out['original_star_count']!=323:raise ValueError('NOT_323_ORIGINAL_REAL_STARS')
    return out


def main():
    ap=argparse.ArgumentParser()
    for x in ('source-dir','artifacts-dir','source-manifest','artifact-manifest','out'):
        ap.add_argument('--'+x,required=True,type=Path)
    ar=ap.parse_args()
    out=summary_for_real_centres(ar.source_dir,ar.artifacts_dir,ar.source_manifest,ar.artifact_manifest)
    ar.out.parent.mkdir(exist_ok=True,parents=True)
    ar.out.write_text(json.dumps(out,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print('F79 original stars',out['original_star_count'],'necessary input-model rejected',out['original_numerical_source_rejected_stars'])
    for n,x in out['models'].items():
        print(n,'native-H causal bad edges',x['source_interval_violation_counts']['causal_enthalpy_violation'],
              'native-H monotone bad',x['source_interval_violation_counts']['monotone_enthalpy_violation'],
              'H affected stars',x['F79_C_star_count_with_enthalpy_bound_violation'],
              'additional stars beyond F77',x['F79_additional_C_star_count_not_already_F77'])
    print('NO physical certification; source native photons NOT RUN')
if __name__=='__main__':main()

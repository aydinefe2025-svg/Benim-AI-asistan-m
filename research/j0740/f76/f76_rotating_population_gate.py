#!/usr/bin/env python3
"""F76: 323 original RNS stars vs source-byte-pinned *sampled* EOS causality.

This proves failures of the sampled *original numerical representation* only.
A no-violation result does not certify causality between knots or the physics.
It does not generate/replace EOS tables or claim photon-level likelihood.
"""
from __future__ import annotations
import argparse
import io
import json
import sys
from pathlib import Path
import numpy as np

_THIS = Path(__file__).resolve().parent
# The GitHub science branch keeps F75 in its own directory. A bundled offline
# copy can keep the two modules beside each other without changing the imports.
_F75 = _THIS.parent / 'f75'
if _F75.is_dir():
    sys.path.insert(0, str(_F75))
from f75_original_eos_causality_gate import (EOS, digest, load_original_stars,
    require_sha, GEOM_E_TO_G_CM3)


def classify_one_star(densities: np.ndarray, cs2: np.ndarray,
                      central_g_cm3: float) -> dict:
    """Count actual original EOS source knots below a real GR star center.

    Do not interpolate a missing physical star, silently extrapolate an EOS,
    or promote source *knot* evidence into a continuum physical proof.
    """
    d = np.asarray(densities, dtype=np.float64)
    c = np.asarray(cs2, dtype=np.float64)
    if d.ndim != 1 or c.shape != d.shape or len(d) < 10 or not (np.isfinite(d).all() and np.isfinite(c).all()):
        raise ValueError('malformed source knot arrays')
    # F66 found an authentic low-pressure nonmonotone E(P) edge in six
    # LALSuite-spline outputs. This is evidence to REPORT, not a reason to
    # discard those original models before detecting the physical violation.
    if np.any(d <= 0):
        raise ValueError('nonpositive source energy density')
    if not np.isfinite(central_g_cm3) or central_g_cm3 < d[0]:
        raise ValueError('no authenticated source knot before star center')
    below = d <= central_g_cm3
    n_neg = int(np.count_nonzero((c < 0) & below))
    n_super = int(np.count_nonzero((c > 1) & below))
    bad_e_edges = (np.diff(d) <= 0) & (np.maximum(d[:-1],d[1:]) <= central_g_cm3)
    n_nonmono = int(np.count_nonzero(bad_e_edges))
    coverage = central_g_cm3 <= float(d.max())
    status = ('SOURCE_KNOT_CAUSALITY_VIOLATED' if n_neg + n_super + n_nonmono else
              'PASS_KNOTS_ONLY_UNCERTIFIED' if coverage else
              'UNRESOLVED_OUTSIDE_SOURCE_TABLE')
    return {'status':status, 'negative_source_knots_below_core':n_neg,
            'superluminal_source_knots_below_core':n_super,
            'sampled_source_knots_below_core':int(below.sum()),
            'nonmonotone_source_energy_edges_below_core':n_nonmono,
            'source_table_covers_center':bool(coverage)}


def analyze(source_dir:Path, artifact_dir:Path, source_manifest:Path, artifact_manifest:Path) -> dict:
    sf = json.loads(Path(source_manifest).read_text())
    af = json.loads(Path(artifact_manifest).read_text())
    if sf['pinned_commit'] != af['original_JESTER_commit'] or set(sf['records']) != set(EOS):
        raise ValueError('source identity / seven-model selection changed')
    output = {'schema':'J0740_F76_323_ORIGINAL_SPIN_C_SOURCE_KNOT_DOMINANCE_V1',
              'scientific_scope':'actual source-native EOS knot violations in the entire 323 saved GR RNS C sample, NOT continuous physical admissibility',
              'reference_mass_msun':2.073,
              'source_JESTER_commit':sf['pinned_commit'],
              'source_original_RNS_commit':af['original_RNS_commit'],
              'source_photon_XPSI_Bayes':'NOT_RUN',
              'physical_EOS_certification':'NOT_ESTABLISHED',
              'all_seven_source_models_posterior':'NOT_COMPUTED',
              'source_original_sampled_RNS_C_stars':0,
              'source_knot_violating_RNS_C_stars':0,
              'source_knot_no_violation_RNS_C_stars':0,
              'unresolved_outside_source':0,
              'models':{}}
    for name in EOS:
        info=sf['records'][name]
        blob=(Path(source_dir)/(name+'.npz')).read_bytes()
        require_sha(blob,info['sha256'],'SOURCE_NPZ_'+name)
        data=np.load(io.BytesIO(blob),allow_pickle=False)
        if str(data['eos_name']) != name or str(data['source']) != 'LALSimulation':
            raise ValueError('unexpected EOS identity')
        p,e,cs=[np.asarray(data[k],dtype=np.float64) for k in ('p','e','cs2')]
        if p.ndim!=1 or len(e)!=len(p) or len(cs)!=len(p) or (p <= 0).any() or not np.isfinite(p).all() or (np.diff(p)<=0).any():
            raise ValueError('EOS pressure not well formed')
        density=e*GEOM_E_TO_G_CM3
        stars,raw=load_original_stars(Path(artifact_dir),af,name)
        if raw['source_original_npz_sha256'] != info['sha256']:
            raise ValueError('RNS star source mismatch')
        if len(stars) != af['artifacts'][name]['original_C_star_count']:
            raise ValueError('original star count mismatch')
        outcomes=[]
        for index,star in enumerate(stars):
            if abs(float(star['spin_residual_hz'])) > float(star['allowed_spin_residual_hz']) + 1e-9:
                raise ValueError('original RNS spin tolerance exceeded')
            c=classify_one_star(density,cs,float(star['central_energy_density_g_cm3']))
            outcomes.append({'original_star_index':index,'mass_msun':star['mass_msun'],
                             'central_energy_density_g_cm3':star['central_energy_density_g_cm3'],
                             'spin_reported_hz':star['spin_hz_reported'],
                             **c})
        bad=[x for x in outcomes if x['status']=='SOURCE_KNOT_CAUSALITY_VIOLATED']
        good=[x for x in outcomes if x['status']=='PASS_KNOTS_ONLY_UNCERTIFIED']
        unknown=[x for x in outcomes if x['status']=='UNRESOLVED_OUTSIDE_SOURCE_TABLE']
        output['source_original_sampled_RNS_C_stars'] += len(outcomes)
        output['source_knot_violating_RNS_C_stars'] += len(bad)
        output['source_knot_no_violation_RNS_C_stars'] += len(good)
        output['unresolved_outside_source'] += len(unknown)
        def first_causal_knots(mask):
            return float(density[np.flatnonzero(mask)[0]]) if np.any(mask) else None
        output['models'][name]={
            'source_original_C_star_count':len(outcomes),
            'star_count_with_source_knot_violation':len(bad),
            'star_count_with_no_sampled_knot_violation':len(good),
            'star_count_outside_source_table':len(unknown),
            'original_source_negative_knot_count':int(np.count_nonzero(cs<0)),
            'original_source_superluminal_knot_count':int(np.count_nonzero(cs>1)),
            'original_source_energy_nonincreasing_edges':int(np.count_nonzero(np.diff(density)<=0)),
            'first_negative_source_knot_density_g_cm3':first_causal_knots(cs<0),
            'first_superluminal_source_knot_density_g_cm3':first_causal_knots(cs>1),
            'max_mass_no_sampled_knot_violation_msun':max((x['mass_msun'] for x in good),default=None),
            'min_mass_with_sampled_superluminal_knot_msun':min((x['mass_msun'] for x in outcomes if x['superluminal_source_knots_below_core']>0),default=None),
            'source_npz_sha256':info['sha256'],
            'original_RNS_json_sha256':af['artifacts'][name]['json_sha256'],
            'stars':outcomes,
            'physics_certification':'NOT_ESTABLISHED',
        }
    if output['source_original_sampled_RNS_C_stars'] != 323:
        raise ValueError('baseline 323 authentic C star accounting changed')
    if output['source_original_sampled_RNS_C_stars'] != sum(af['artifacts'][n]['original_C_star_count'] for n in EOS):
        raise ValueError('star aggregation mismatch')
    if output['source_original_sampled_RNS_C_stars'] != (output['source_knot_violating_RNS_C_stars']+
                 output['source_knot_no_violation_RNS_C_stars']+output['unresolved_outside_source']):
        raise ValueError('star accounting failed')
    return output


def main():
    p=argparse.ArgumentParser()
    for opt in ('source-dir','artifacts-dir','source-manifest','artifact-manifest','out'):
        p.add_argument('--'+opt,type=Path,required=True)
    a=p.parse_args()
    obj=analyze(a.source_dir,a.artifacts_dir,a.source_manifest,a.artifact_manifest)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False,ensure_ascii=False)+'\n',encoding='utf8')
    print('F76', json.dumps({k:obj[k] for k in ('source_original_sampled_RNS_C_stars','source_knot_violating_RNS_C_stars','source_knot_no_violation_RNS_C_stars','unresolved_outside_source')}))
    for n,v in obj['models'].items():print(n,v['star_count_with_source_knot_violation'],v['star_count_with_no_sampled_knot_violation'])
    print('SOURCE_SAMPLED_KNOTS_ONLY_NOT_CONTINUUM_PHYSICS')

if __name__=='__main__':main()
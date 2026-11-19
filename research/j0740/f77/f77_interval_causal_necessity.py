#!/usr/bin/env python3
"""F77: exact piecewise EOS source-node causal *necessity* audit.

For a differentiable barotropic EOS E(P) with 0<c_s^2=dP/dE<=1,
we must have Delta E >= Delta P > 0 on *every* fully sampled
pressure interval (in the same geometrized units). Failing this
necessary condition proves no causal smooth interpolation through
those same source knots. Satisfying it is NOT sufficient to certify
continuum causality, global thermodynamics, or stable stars.

Inputs are source SHA-pinned original JESTER/LALSimulation NPZ EOS knots
and 323 source SHA-pinned original 346.536369-Hz GR RNS C stars.
No EOS modifications, photon fits, extrapolated stars or posterior claims.
"""
import argparse, hashlib, io, json, sys
from pathlib import Path
import numpy as np

_HERE = Path(__file__).resolve().parent
if (_HERE.parent / 'f75').is_dir():
    sys.path.insert(0, str(_HERE.parent / 'f75'))
from f75_original_eos_causality_gate import EOS, load_original_stars, require_sha, GEOM_E_TO_G_CM3

# Gap relative to delta P; a near-floating-point-equality delta does not
# justify a physically strong superluminal claim. In these source data the
# actual violations exceed this small numerical comparison tolerance.
RELATIVE_MARGIN = 1e-10

def audit_source_segments(p, e, *, rel_margin=RELATIVE_MARGIN):
    """Returns a necessary causal inequality and segment density upper edges.

    No derivative or interpolator is evaluated. The mean value theorem alone
    yields impossibility if Delta E<Delta P on a fully covered interval.
    """
    p=np.asarray(p, dtype=np.float64); e=np.asarray(e, dtype=np.float64)
    if (p.ndim!=1 or e.ndim!=1 or p.shape!=e.shape or p.size<10 or
        not np.isfinite(p).all() or not np.isfinite(e).all() or
        np.any(p<=0) or np.any(e<=0) or np.any(np.diff(p)<=0)):
        raise ValueError('invalid original geometrized source pressure/energy arrays')
    if not (0<=rel_margin<1e-5):
        raise ValueError('invalid relative tolerance')
    dp=np.diff(p); de=np.diff(e)
    bad_energy=de<=0.0
    # Clearly superluminal *average* speed squared, not just local spline sample.
    bad_super=(de>0.0)&(de<dp*(1-rel_margin))
    ambiguous=(de>0.0)&(de>=dp*(1-rel_margin))&(de<dp*(1+rel_margin))
    edges=np.maximum(e[:-1],e[1:])*GEOM_E_TO_G_CM3
    return {'bad_energy':bad_energy, 'bad_super':bad_super,
            'ambiguous_near_boundary':ambiguous, 'upper_densities':edges,
            'dp':dp, 'de':de, 'p':p, 'e':e}


def classify_star_segments(segments, central_density_g_cm3):
    edges=segments['upper_densities']
    central=float(central_density_g_cm3)
    emin=float(np.min(segments['e'])*GEOM_E_TO_G_CM3)
    emax=float(np.max(segments['e'])*GEOM_E_TO_G_CM3)
    if not np.isfinite(central) or central < emin:
        raise ValueError('real star core below source EOS support')
    if central > emax:
        return {'status':'UNRESOLVED_SOURCE_COVERAGE','fully_inside_segments':0,
                'negative_delta_energy_segments':0,'superluminal_secant_segments':0,
                'borderline_segments':0,'source_covers_center':False}
    included=edges<=central
    n_neg=int(np.count_nonzero(included & segments['bad_energy']))
    n_super=int(np.count_nonzero(included & segments['bad_super']))
    n_border=int(np.count_nonzero(included & segments['ambiguous_near_boundary']))
    # We do NOT declare physical success, only absence of this necessary-condition failure.
    status=('REFUTED_BY_SOURCE_SEGMENT' if n_neg or n_super else
            'NECESSARY_CONDITION_ONLY_UNCERTIFIED')
    return {'status':status,'fully_inside_segments':int(included.sum()),
            'negative_delta_energy_segments':n_neg,'superluminal_secant_segments':n_super,
            'borderline_segments':n_border,'source_covers_center':True}


def analyze(source_dir, artifacts_dir, source_manifest, artifact_manifest):
    source_dir=Path(source_dir); artifacts_dir=Path(artifacts_dir)
    sf=json.loads(Path(source_manifest).read_text());af=json.loads(Path(artifact_manifest).read_text())
    if sf['pinned_commit']!=af['original_JESTER_commit'] or set(sf['records'])!=set(EOS):
        raise ValueError('unrecognized EOS original source lineage')
    out={'schema':'J0740_F77_ORIGINAL_SOURCE_SEGMENT_MEAN_VALUE_CAUSAL_NECESSITY_V1',
         'method':'For every fully interior original NPZ source segment: Delta E >= Delta P>0 is NECESSARY for any 0<c_s^2<=1 smooth EOS through same nodes',
         'original_JESTER_commit':sf['pinned_commit'],
         'original_RNS_commit':af['original_RNS_commit'],
         'source_original_346Hz_RNS_C_stars':0,
         'source_segment_refuted_stars':0,
         'source_segment_necessary_only_stars':0,
         'source_coverage_unknown_stars':0,
         'source_photon_XPSI':'NOT_RUN',
         'physical_EOS_approval':'NOT_ESTABLISHED',
         'seven_model_physical_Bayes':'NOT_RUN',
         'notes':['EOS source NPZ arrays are *derived* from original LALSuite table/spline, not independent microscopic raw EOS',
                  'A failing source NPZ interval cannot be repaired by an interpolant alone without changing at least one of those two source-node values',
                  'F66: original low-P raw LAL source tables are monotonic, whereas source log-log spline generated negative derivative; do not infer the raw nuclear EOS itself is invalid',
                  'Passing all sampled segments does NOT prove continuous causality or rotating-star stability'],
         'models':{}}
    for name in EOS:
        blob=(source_dir/(name+'.npz')).read_bytes()
        require_sha(blob,sf['records'][name]['sha256'],'JESTER_'+name)
        f=np.load(io.BytesIO(blob),allow_pickle=False)
        if str(f['eos_name'])!=name or str(f['source'])!='LALSimulation':
            raise ValueError('EOS identity mismatch')
        segments=audit_source_segments(f['p'],f['e'])
        stars, source=load_original_stars(artifacts_dir,af,name)
        if source['source_original_npz_sha256']!=sf['records'][name]['sha256']:
            raise ValueError('RNS source and EOS source differ')
        each=[]
        for index, star in enumerate(stars):
            if abs(float(star['spin_residual_hz']))>float(star['allowed_spin_residual_hz'])+1e-9:
                raise ValueError('invalid authentic spin tolerance')
            st=classify_star_segments(segments,star['central_energy_density_g_cm3'])
            each.append({'index':index,'mass_msun':float(star['mass_msun']),
                         'center_g_cm3':float(star['central_energy_density_g_cm3']),**st})
        bad=[x for x in each if x['status']=='REFUTED_BY_SOURCE_SEGMENT']
        possible=[x for x in each if x['status']=='NECESSARY_CONDITION_ONLY_UNCERTIFIED']
        unknown=[x for x in each if x['status']=='UNRESOLVED_SOURCE_COVERAGE']
        neg=sum(x['negative_delta_energy_segments']>0 for x in each)
        superlum=sum(x['superluminal_secant_segments']>0 for x in each)
        overlap=sum(x['negative_delta_energy_segments']>0 and x['superluminal_secant_segments']>0 for x in each)
        out['models'][name]={
             'actual_original_RNS_C_star_count':len(each),
             'NPZ_source_segment_count':len(segments['dp']),
             'NPZ_negative_energy_segments':int(segments['bad_energy'].sum()),
             'NPZ_superluminal_average_segments':int(segments['bad_super'].sum()),
             'NPZ_ambiguous_near_equality_segments':int(segments['ambiguous_near_boundary'].sum()),
             'first_negative_energy_upper_density_g_cm3':(float(np.min(segments['upper_densities'][segments['bad_energy']])) if np.any(segments['bad_energy']) else None),
             'first_superluminal_average_upper_density_g_cm3':(float(np.min(segments['upper_densities'][segments['bad_super']])) if np.any(segments['bad_super']) else None),
             'stars_with_nonmonotonic_source_NPZ_segments':neg,
             'stars_with_superluminal_source_NPZ_secants':superlum,
             'stars_with_both_types':overlap,
             'stars_refuted_on_source_NPZ_necessary_condition':len(bad),
             'stars_no_source_NPZ_segment_violation_only':len(possible),
             'stars_unknown_source_coverage':len(unknown),
             'source_NPZ_sha256':sf['records'][name]['sha256'],
             'original_RNS_artifact_SHA256':af['artifacts'][name]['zip_sha256'],
             'real_stars':each,
             'physical_EOS_certification':'NOT_ESTABLISHED'}
        out['source_original_346Hz_RNS_C_stars']+=len(each)
        out['source_segment_refuted_stars']+=len(bad)
        out['source_segment_necessary_only_stars']+=len(possible)
        out['source_coverage_unknown_stars']+=len(unknown)
    if out['source_original_346Hz_RNS_C_stars']!=323 or (out['source_segment_refuted_stars']+out['source_segment_necessary_only_stars']+out['source_coverage_unknown_stars'])!=323:
        raise ValueError('original 323-source star population invariant violated')
    return out


def main():
    ap=argparse.ArgumentParser()
    for p in ['source-dir','artifacts-dir','source-manifest','artifact-manifest','out']:
        ap.add_argument('--'+p,type=Path,required=True)
    a=ap.parse_args();z=analyze(a.source_dir,a.artifacts_dir,a.source_manifest,a.artifact_manifest)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(z,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')
    print('F77',json.dumps({k:z[k] for k in ('source_original_346Hz_RNS_C_stars','source_segment_refuted_stars','source_segment_necessary_only_stars','source_coverage_unknown_stars')}))
    for name,s in z['models'].items():
        print(name,'stars',s['stars_refuted_on_source_NPZ_necessary_condition'],'low_nonmonotonic',s['stars_with_nonmonotonic_source_NPZ_segments'],'high_superluminal',s['stars_with_superluminal_source_NPZ_secants'])
    print('F77_NECESSARY_ONLY_NO_PHYSICAL_EOS_CERTIFICATION')
if __name__=='__main__':main()
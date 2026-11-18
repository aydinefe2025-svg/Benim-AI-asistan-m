"""F65 — NEW direct original LALSuite 7-EOS crust sound-speed localization.

Scientific scope: 1201 direct LAL analytic (E(P), dE/dP) evaluations PER
original, unmodified EOS over the fixed low-pressure neighborhood containing
JESTER source node #254. Source NPZ hashes are validated against the pinned
original seven-EOS fixture. Nothing is repaired or interpolated into a star.
This establishes a LAL-derived finite scan, NOT continuous physical stability,
identification of a specific shared crust prescription, nor a photon Bayes result.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np

EOS = ('APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2')
PIN_JESTER = 'e6768650ce992abfd1153a6833857572fe5cd230'
SOURCE_INDEX = 254
GRID_N=1201
P_LEFT = 4.919236321850677e-16 * 0.96
P_RIGHT = 5.444296018918085e-16 * 1.04
G=6.67430e-11; C=299792458.
SHARED_BAD = frozenset(EOS) - {'APR4_EPP'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_original(npz,expected_sha,expected_n):
    if sha(npz) != expected_sha:
        raise ValueError('F65_SOURCE_NPZ_SHA_MISMATCH_'+Path(npz).stem)
    with np.load(npz,allow_pickle=False) as src:
        keys={'p','e','cs2','dloge_dlogp','h'}
        if not keys.issubset(src.files):raise ValueError('F65_INCOMPLETE_SOURCE')
        arr={k:np.asarray(src[k],float) for k in keys}
    p,e,cs,d,hh=(arr[k] for k in ('p','e','cs2','dloge_dlogp','h'))
    if any(v.ndim!=1 or len(v)!=expected_n for v in arr.values()):
        raise ValueError('F65_SOURCE_ROW_DRIFT')
    if (not all(np.isfinite(v).all() for v in arr.values()) or not (p>0).all()
            or not (e>0).all() or not (np.diff(p)>0).all() or not (np.diff(hh)>0).all()):
        raise ValueError('F65_BAD_NATIVE_SOURCE')
    if not np.allclose(cs,p/(e*d),atol=5e-12,rtol=5e-9):
        raise ValueError('F65_NATIVE_ANALYTIC_DERIVATIVE_IDENTITY')
    return arr


def evaluate_lal(p,eos,lalsim):
    """Two direct native LALSuite C library calls, not finite-difference fit."""
    energy=float(lalsim.SimNeutronStarEOSEnergyDensityOfPressureGeometerized(float(p),eos))
    dedp=float(lalsim.SimNeutronStarEOSEnergyDensityDerivOfPressureGeometerized(float(p),eos))
    if not (math.isfinite(energy) and math.isfinite(dedp) and energy>0 and dedp!=0):
        raise ValueError('F65_NONFINITE_OR_ZERO_LAL_ENERGY_DERIVATIVE')
    return energy,dedp


def source_analytic_bridge(source,eos,lalsim,indices=(252,253,254,255,256)):
    rows=[]
    for idx in indices:
        p=float(source['p'][idx]); e_source=float(source['e'][idx]); cs=float(source['cs2'][idx])
        en,der=evaluate_lal(p,eos,lalsim)
        rel=abs(en-e_source)/e_source
        cs_direct=1/der
        # The original pinned generator queried the same LAL analytic source.
        if rel>2e-5 or abs(cs_direct-cs)>max(1e-6,5e-4*abs(cs)):
            raise ValueError(f'F65_LAL_VS_JESTER_SOURCE_VALUE_DRIFT_IDX_{idx}_REL_{rel}_CS_{cs_direct}_{cs}')
        rows.append(dict(index=idx,p_geom=p,e_geom_direct=en,e_geom_native=e_source,
                         cs2_direct=cs_direct,cs2_source=cs,
                         native_e_agreement_fraction=rel,energy_density_g_cm3=en*C*C/G*1e-3))
    return rows


def classify_scan(p,e,dedp,*,source_idx,source_negative):
    """No physically misleading continuous proof from finite pressure scans."""
    p,e,dedp=map(lambda x:np.asarray(x,dtype=float),(p,e,dedp))
    if any(v.ndim!=1 or len(v)<101 for v in (p,e,dedp)) or len(p)!=len(e) or len(e)!=len(dedp):
        raise ValueError('F65_BAD_SCAN_ARRAYS')
    if (not all(np.isfinite(v).all() for v in (p,e,dedp)) or (p<=0).any()
            or (e<=0).any() or (np.diff(p)<=0).any() or (dedp==0).any()):
        raise ValueError('F65_PHYSICS_GUARD')
    bad=dedp<0
    energy_reversal=np.diff(e)<0
    pressure_bins_bad=int(np.count_nonzero(bad))
    signboundaries=np.flatnonzero(np.diff(bad.astype(int))!=0)
    # A scan-bracket is not a mathematically proven zero of derivative:
    # interpolation can have discontinuities at table knots.
    brackets=[dict(p_lo=float(p[i]),p_hi=float(p[i+1]),
                   dedp_lo=float(dedp[i]),dedp_hi=float(dedp[i+1])) for i in signboundaries]
    intervals=[]
    if np.any(bad):
        indices=np.flatnonzero(bad)
        partitions=np.split(indices,np.where(np.diff(indices)!=1)[0]+1)
        for part in partitions:
            i0,i1=int(part[0]),int(part[-1])
            intervals.append(dict(p_sample_low=float(p[i0]),p_sample_high=float(p[i1]),
                 n_points=len(part),width_sample_geom=float(p[i1]-p[i0]),
                 min_inverse_sound_speed=float(dedp[part].min()),
                 min_cs2_over_c2=float(np.min(1/dedp[part])),
                 max_native_e_relative_drop=float(np.min(np.diff(e[max(i0-1,0):min(i1+2,len(e))]))/max(e[i0],1e-30))))
    return dict(negative_inverse_cs2_sample_nodes=pressure_bins_bad,
       negative_energy_secant_bins=int(np.count_nonzero(energy_reversal)),
       negative_derivative_intervals_sampled=intervals,
       analytic_derivative_sign_change_brackets=brackets,
       source_node_index=source_idx,source_negative_cs2=bool(source_negative),
       classification=('NEGATIVE_LAL_ANALYTIC_CS2_FINITE_INTERVAL_SAMPLED_NOT_GLOBAL_STABILITY'
                       if pressure_bins_bad else 'NO_NEGATIVE_LAL_ANALYTIC_CS2_IN_SCAN'),
       finite_scan_is_not_continuous_physical_certificate=True)


def audit(source_dir,fixture,lalsim,*,n=GRID_N):
    if fixture.get('source_commit')!=PIN_JESTER or set(fixture.get('eos',{}))!=set(EOS):
        raise ValueError('F65_PINNED_JESTER_FIXTURE_DRIFT')
    if n<1000:raise ValueError('F65_INSUFFICIENT_DIRECT_LAL_SAMPLES')
    scan_p=np.geomspace(P_LEFT,P_RIGHT,n)
    result={'schema':'J0740_F65_ORIGINAL_SEVEN_DIRECT_LAL_CRUST_LOCALIZATION_V1',
        'status':'IN_PROGRESS', 'jester_original_commit':PIN_JESTER,
        'original_source_not_F42_lift':True,'original_EOS_names':list(EOS),
        'source_scan_pressure_geom':[P_LEFT,P_RIGHT],
        'direct_LAL_samples_per_EOS':n,'native_lalsimulation_analytic_derivative':True,
        'source_EOS_globally_physically_accepted':'NOT_ESTABLISHED',
        'exact_source_photon_XPSI_likelihood':'NOT_RUN',
        'seven_original_EOS_Bayesian_evidence':'NOT_RUN',
        'global_rotation_stability':'NOT_PROVEN','eos':{},
        'limitations':['Local 1201 point finite scan only, no continuous bound or branch phase-transition identity',
         'A shared negative-pressure band across six EOS is compatible with shared source crust behavior but does not uniquely establish the crust implementation',
         'Original seven source EOS tables unchanged; no physically certified EOS repair',
         'No 12.9 GB photon archive read or reprocessed; no source-native X-PSI likelihood or Bayes']}
    for name in EOS:
        info=fixture['eos'][name]
        original=Path(source_dir)/(name+'.npz')
        a=validate_original(original,info['expected_source_sha256'],info['expected_source_rows'])
        eos=lalsim.SimNeutronStarEOSByName(name)
        bridge=source_analytic_bridge(a,eos,lalsim)
        e,d=[],[]
        for p in scan_p:
            en,der=evaluate_lal(float(p),eos,lalsim);e.append(en);d.append(der)
        s=classify_scan(scan_p,e,d,source_idx=SOURCE_INDEX,source_negative=bool(a['cs2'][SOURCE_INDEX]<0))
        s.update(source_npz_sha256=sha(original),source_row_count=len(a['p']),
                 original_knot_253_254_negative_energy_secant=bool(a['e'][254]-a['e'][253]<0),
                 source_negative_cs2_node_count=int(np.count_nonzero(a['cs2']<=0)),
                 original_source_bridge=bridge,
                 diagnostic_p_grid_geom=[float(x) for x in scan_p],
                 diagnostic_e_grid_geom=[float(x) for x in e],
                 diagnostic_dedp_grid=[float(x) for x in d])
        result['eos'][name]=s
        print(name,s['classification'],'neg',s['negative_inverse_cs2_sample_nodes'],
             'intervals',len(s['negative_derivative_intervals_sampled']),flush=True)
    negative={k for k,v in result['eos'].items() if v['negative_inverse_cs2_sample_nodes']>0}
    result['negative_direct_LAL_EOS_in_crust_scan']=sorted(negative)
    result['same_as_source_expected_six_classification']=bool(negative==SHARED_BAD)
    if negative!=SHARED_BAD:
        result['status']='F65_FAIL_OR_UNEXPECTED_LAL_CRUST_SOURCE_CLASSIFICATION';
        raise ValueError('F65_DIRECT_LAL_RESULT_DISAGREES_WITH_PINNED_SOURCE_NEGATIVE_SIX')
    result['status']='F65_DIRECT_LAL_CRUST_SIX_OF_SEVEN_NEGATIVE_LOCALIZED_FINITE_SCAN_NOT_PHYSICAL_CERT'
    return result


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source-dir',type=Path,required=True)
    ap.add_argument('--fixture',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    import lalsimulation
    fixture=json.loads(a.fixture.read_text())
    out=audit(a.source_dir,fixture,lalsimulation)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(out,sort_keys=True,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':out['status'],'negative':out['negative_direct_LAL_EOS_in_crust_scan'],
        'scan_per_EOS':out['direct_LAL_samples_per_EOS']},sort_keys=True))
if __name__=='__main__': main()
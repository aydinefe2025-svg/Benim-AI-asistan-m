#!/usr/bin/env python3
"""F139: genuine LAL C-backed fine-pressure scan of the shared six-EOS crust anomaly.

Distinct from F132 single-node source audit: resolves a native negative derivative
across each pressure interval near pressure index 254. Diagnostic ONLY: no repaired
EOS, no general-relativistic stellar stability or photon Bayesian likelihood.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path
import numpy as np

JESTER_COMMIT='e6768650ce992abfd1153a6833857572fe5cd230'
SOURCE_SHAS={
 'APR4_EPP':'639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88',
 'ENG':'702da3ddf7c10b0091af5d8c0d576a9e9a85a85726849a2860bdd8ef3643f953',
 'MPA1':'0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22',
 'MS1':'531530be6253984622f667f454f825ccd13fa4e8960a1411aefe5dd7ea5ff3ad',
 'MS1B':'7a3302e8f2541469fc9ba26dbe52f97b1c8696b71864a208ca43ca7f5cde984c',
 'WFF1':'119b8a25435faeddf00f5d3638f3ff2ff00283ce60caacc24cc37c6e2e030ed3',
 'WFF2':'eb08edc3723fc32d428b3dc3b21aa612dad8a3bdb5da6246faedbb7ed65683ae'}
KNOT=254
G_SI=6.67430e-11;C_SI=299792458.0

def sha(b):return hashlib.sha256(b).hexdigest()

def source_gate(path,name):
    if name not in SOURCE_SHAS:raise ValueError('UNKNOWN_ORIGINAL_EOS')
    raw=Path(path).read_bytes()
    if sha(raw)!=SOURCE_SHAS[name]:raise ValueError('SOURCE_SHA_MISMATCH:'+name)
    with np.load(path,allow_pickle=False) as f:
        if str(f['eos_name'])!=name or str(f['source'])!='LALSimulation':
            raise ValueError('ORIGINAL_EOS_LABEL_INVALID')
        p,e,cs2=[np.asarray(f[k],float) for k in ('p','e','cs2')]
    if p.ndim!=1 or len(p)<300 or any(len(a)!=len(p) for a in [e,cs2]):
        raise ValueError('INVALID_SOURCE_SHAPE')
    if not all(np.all(np.isfinite(a)) for a in (p,e,cs2)) or np.any(p<=0) or np.any(e<=0):
        raise ValueError('NONFINITE_SOURCE')
    if not np.all(np.diff(p)>0):raise ValueError('INVALID_SOURCE_PRESSURE')
    if (cs2[KNOT] < 0) == (name=='APR4_EPP'):
        raise ValueError('SHARED_CRUST_ANOMALY_SOURCE_DRIFT')
    return p,e,cs2

def native_api(lalsim,name):
    x=getattr(lalsim,name,None)
    if x is None:x=getattr(lalsim,name.replace('Geometrized','Geometerized'),None)
    if x is None:raise RuntimeError('LAL_NATIVE_API_MISSING:'+name)
    return x

def probe_model(lalsim,name,p,e,step=KNOT,neighbors=3,per_interval=65):
    p,e=[np.asarray(x,float) for x in (p,e)]
    if not (p.ndim==e.ndim==1 and len(p)==len(e)>step+neighbors and step-neighbors>=0):
        raise ValueError('INVALID_SOURCE_SHAPE')
    if np.any(~np.isfinite(p)) or np.any(~np.isfinite(e)) or np.any(p<=0) or np.any(e<=0) or np.any(np.diff(p)<=0):
        raise ValueError('INVALID_SOURCE_PRESSURE')
    if not 3<=per_interval<=2049 or not 1<=neighbors<=20:
        raise ValueError('INVALID_NATIVE_SAMPLING')
    de=native_api(lalsim,'SimNeutronStarEOSEnergyDensityDerivOfPressureGeometrized')
    en=native_api(lalsim,'SimNeutronStarEOSEnergyDensityOfPressureGeometrized')
    eos=lalsim.SimNeutronStarEOSByName(name)
    left=step-neighbors;right=step+neighbors
    logs=np.linspace(math.log(float(p[left])),math.log(float(p[right])),2) # used to enforce finite boundaries
    if not np.isfinite(logs).all():raise ValueError('NONFINITE_NATIVE_INTERVAL')
    arr=[]
    for i in range(left,right):
        for k in range(per_interval):
            if i!=left and k==0:continue
            q=float(math.exp(math.log(float(p[i]))+(math.log(float(p[i+1]))-math.log(float(p[i])))*k/(per_interval-1)))
            dd=float(de(q,eos));ee=float(en(q,eos))
            if not (math.isfinite(dd) and math.isfinite(ee) and ee>0 and dd!=0):
                raise ValueError('NONFINITE_OR_SINGULAR_LAL_EOS_DERIVATIVE:'+name+':'+str(i)+':'+str(k))
            arr.append({'segment_index':int(i),'fraction_index':int(k),'pressure_geom_m_minus2':q,
                        'energy_geom_m_minus2':ee,'de_dp_native':dd,'cs2':1/dd})
    flags=np.array([x['cs2']<0 for x in arr],bool)
    bad=np.flatnonzero(flags)
    consecutive=bool(np.any(flags[:-1] & flags[1:])) if len(flags)>1 else False
    bracket=[]
    for i in range(len(flags)-1):
        if flags[i]!=flags[i+1]:bracket.append({'lower_pressure':arr[i]['pressure_geom_m_minus2'],
            'upper_pressure':arr[i+1]['pressure_geom_m_minus2'],
            'negative_on_lower':bool(flags[i]),'negative_on_upper':bool(flags[i+1])})
    out={'eos':name,'source_shared_crust_index':step,'scan_start_interval':left,'scan_end_interval':right-1,
         'source_grid_p254':float(p[step]),'source_grid_e254':float(e[step]),
         'source_grid_e254_g_cm3':float(e[step]*C_SI*C_SI/G_SI/1000),
         'native_calls':len(arr),'negative_cs2_sample_count':len(bad),
         'native_negative_pressure_span_exists':consecutive,
         'negative_cs2_min_pressure':float(arr[bad[0]]['pressure_geom_m_minus2']) if len(bad) else None,
         'negative_cs2_max_pressure':float(arr[bad[-1]]['pressure_geom_m_minus2']) if len(bad) else None,
         'min_cs2':float(min(x['cs2'] for x in arr)),
         'max_cs2':float(max(x['cs2'] for x in arr)),
         'negative_sign_change_brackets':bracket,
         'positive_sample_count':int(sum(x['cs2']>0 for x in arr)),
         'source_sha256':SOURCE_SHAS[name]}
    if len(arr)!=(right-left)*(per_interval-1)+1:
        raise AssertionError('NATIVE_SAMPLE_COUNT_INVARIANT')
    return out,arr

def check_original_star_reachability(record, expected_sha, native_e_knot):
    """Ground the seam in already archived genuine 346Hz RNS C stellar centres."""
    if record.get('original_npz_sha256') != expected_sha:
        raise ValueError('STAR_REFERENCE_EOS_SHA_MISMATCH')
    mass=float(record['mass_msun']); rho=float(record['central_density_g_cm3'])
    n=int(record['n_original_C_stars'])
    if not (math.isfinite(mass) and 1.7<mass<2.4 and math.isfinite(rho)
            and rho>0 and 40<=n<=50 and float(native_e_knot)>0):
        raise ValueError('INVALID_GENUINE_RNS_STAR_REFERENCE')
    seam=float(native_e_knot)*C_SI*C_SI/G_SI/1000
    if not rho>seam:
        raise ValueError('STAR_CENTER_NOT_REACHING_SEAM')
    return {'nearest_original_C_mass_msun':mass,
            'original_C_central_density_g_cm3':rho,
            'source_low_pressure_energy_density_g_cm3':seam,
            'seam_inside_star_density_range':True,
            'source_C_population_n':n,
            'scope':'CENTRAL_DENSITY_VS_EOS_PRESSURE_DOMAIN_ONLY_NOT_RADIAL_STABILITY'}

def compare_seam(source_arrays,step=KNOT):
    out={};names=sorted(source_arrays)
    for ia,a in enumerate(names):
        pa,ea=source_arrays[a]
        for b in names[ia+1:]:
            pb,eb=source_arrays[b]
            if len(pa)<=step or len(pb)<=step:raise ValueError('SHORT_SOURCE_COMPARE')
            out[f'{a}__{b}']={
                'common_pressure_knot':bool(float(pa[step])==float(pb[step])),
                'same_energy_to_1e-7':bool(abs(float(ea[step]/eb[step]-1))<=1e-7),
                'relative_e_difference_at_knot':float(ea[step]/eb[step]-1),
                'source_indices':step}
    return out

def run(source_dir,out_dir,per_interval=65,star_ref=None):
    import lal,lalsimulation as ls
    source_dir=Path(source_dir);out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    report={'schema':'J0740_F139_SEVEN_NATIVE_LAL_SHARED_CRUST_SEAM_V1','source_JESTER_commit':JESTER_COMMIT,
        'native_LALSWIG_version':str(getattr(lal,'__version__','unknown')),
        'sampling':'65 geometric pressure samples per original input interval, 6 adjacent intervals centred on knot 254; finite numerical scan',
        'source_index':KNOT,'status':'IN_PROGRESS','models':{},
        'source_arrays':'ORIGINAL_SOURCE_PINNED_NOT_MODIFIED',
        'scientific_limit':'This detects finite native C API derivative anomalies at low-pressure crust seam. It does not repair source EPS/n, prove continuum negativity width, global physical EOS, rotating stability or source X-PSI photon Bayes.',
        'physical_seven_EOS_posterior':'NOT_COMPUTED'}
    def persist(): (out_dir/'F139_REAL_LAL_COMMON_CRUST_SEAM.json').write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    persist();inputs={}
    refs=None
    if star_ref is not None:
        refs=json.loads(Path(star_ref).read_text())
        if refs.get('schema')!='F139_NEAREST_ORIGINAL_C_STAR_CENTRAL_DENSITIES_FROM_F79_V1' or refs.get('source_jester_commit')!=JESTER_COMMIT or set(refs.get('models',{}))!=set(SOURCE_SHAS):
            raise ValueError('F79_GENUINE_STAR_REFERENCE_SOURCE_DRIFT')
        report['original_F79_stellar_centres_provenance_SHA256']=refs['upstream_source_sha256']
    for name in SOURCE_SHAS:
        p,e,cs2=source_gate(source_dir/(name+'.npz'),name)
        inputs[name]=(p,e)
        star_scope=check_original_star_reachability(refs['models'][name],SOURCE_SHAS[name],e[KNOT]) if refs else None
        try:
            summary,rows=probe_model(ls,name,p,e,KNOT,3,per_interval)
            summary['source_cs2_at_index254']=float(cs2[KNOT]);summary['status']='AUTHENTIC_NATIVE_LAL_MEASURED'
            if star_scope is not None:summary['original_C_reference_star_scope']=star_scope
            with (out_dir/(name+'_F139_REAL_NATIVE_C_SEAM.csv')).open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        except Exception as err:
            summary={'eos':name,'status':'FAIL_CLOSED','error':str(err)}
        report['models'][name]=summary;persist()
        print('F139_MODEL',name,json.dumps({k:summary.get(k) for k in ('status','native_calls','negative_cs2_sample_count','native_negative_pressure_span_exists','min_cs2')}),flush=True)
    report['shared_seam_pairs']=compare_seam(inputs)
    report['all_original_EOS_native_measured']=all(x['status']=='AUTHENTIC_NATIVE_LAL_MEASURED' for x in report['models'].values())
    report['total_native_calls']=sum(x.get('native_calls',0) for x in report['models'].values())
    report['status']='SEVEN_NATIVE_LAL_SEAM_SCANS_COMPLETED_DIAGNOSTIC_ONLY' if report['all_original_EOS_native_measured'] else 'PARTIAL_FAIL_CLOSED'
    persist()
    files=[p for p in out_dir.iterdir() if p.is_file()]
    (out_dir/'F139_SHA256_LEDGER.json').write_text(json.dumps({p.name:sha(p.read_bytes()) for p in files},indent=2,sort_keys=True)+'\n')
    print('F139_RESULT',report['status'],'total_calls',report['total_native_calls'],flush=True)
    return 0 if report['all_original_EOS_native_measured'] else 2

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--source-dir',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,required=True);ap.add_argument('--per-interval',type=int,default=65);ap.add_argument('--star-ref',type=Path)
    ar=ap.parse_args();raise SystemExit(run(ar.source_dir,ar.out_dir,ar.per_interval,ar.star_ref))
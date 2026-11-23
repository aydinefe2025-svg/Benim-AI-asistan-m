#!/usr/bin/env python3
"""F142: compare original vs F140 derived native LAL C acausality at F141 static-star pressure range."""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f139'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f141'))
from f139_shared_crust_seam import SOURCE_SHAS,source_gate,native_api,JESTER_COMMIT
from f141_real_static_tov import verify_f140,read_candidate
BAD=('ENG','WFF1','WFF2')
PREVIOUS_F141_SHA='0cfdf960fdb833a758086aa675de3de90a8ff73c398b4c716d4d62b80b97ed86'
F141_RUN=45260071899
F140_RUN=45259419081
C=299792458.0;G=6.67430e-11
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bracket_source(p,e,q):
    if not (len(p)==len(e) and len(p)>3 and np.all(np.diff(p)>0)):raise ValueError('BAD_NATIVE_EOS_SOURCE_KNOTS')
    idx=int(np.searchsorted(p,q,side='right')-1)
    if idx<0 or idx>=len(p)-1:raise ValueError('QUERY_OUTSIDE_TABULATED_SOURCE')
    secant=float((e[idx+1]-e[idx])/(p[idx+1]-p[idx]))
    return {'interval_index':idx,'secant_dE_dP':secant,
      'secant_cs2':(1/secant if secant!=0 else None),
      'endpoint_secant_causal':bool(math.isfinite(secant) and secant>=1),
      'pressure_lower':float(p[idx]),'pressure_upper':float(p[idx+1])}
def derivative_profile(ls,eos,q):
    f=native_api(ls,'SimNeutronStarEOSEnergyDensityDerivOfPressureGeometrized')
    dd=np.array([float(f(float(x),eos)) for x in q],float)
    cs2=np.divide(1,dd,out=np.full_like(dd,np.nan),where=dd!=0)
    return cs2
def summarize_original_derived(name,p,e,derived,original_cs2,derived_cs2,pc):
    if not(all(len(x)==len(original_cs2) for x in (original_cs2,derived_cs2,pc))):
        raise ValueError('F142_SAMPLE_LENGTH_MISMATCH')
    if np.any(~np.isfinite(original_cs2)) or np.any(~np.isfinite(derived_cs2)):
        raise ValueError('F142_NATIVE_NONFINITE')
    bad=np.flatnonzero(derived_cs2>1)
    if not len(bad): raise ValueError('F141_REPORTED_ACAUSALITY_NOT_REPRODUCED')
    if np.any(derived_cs2<=0): raise ValueError('F140_DERIVED_NEGATIVE_CS2_OUTSIDE_BRIDGE')
    details=[]
    for ix in bad:
        q=float(pc[ix]);s_orig=bracket_source(p,e,q)
        s_derived=bracket_source(derived[:,0],derived[:,1],q)
        details.append({'sample_index':int(ix),
          'pressure_geom_m_minus2':q,
          'original_src_interval':s_orig,
          'derived_tabulated_interval':s_derived,
          'native_original_cs2':float(original_cs2[ix]),
          'native_derived_cs2':float(derived_cs2[ix]),
          'original_interpolant_also_acausal':bool(original_cs2[ix]>1)})
    source_bad=sum(not x['original_src_interval']['endpoint_secant_causal'] for x in details)
    derived_bad=sum(not x['derived_tabulated_interval']['endpoint_secant_causal'] for x in details)
    original_bad=sum(x['original_interpolant_also_acausal'] for x in details)
    return {'eos':name,'status':'ORIGINAL_VS_DERIVED_NATIVE_COMPARISON_COMPLETE',
      'sampled_pressure_grid_size':len(pc),
      'derived_native_acausal_n':len(details),
      'original_native_acausal_on_same_grid_n':int(np.sum(original_cs2>1)),
      'original_native_acausal_at_derived_acausal_n':original_bad,
      'original_source_endpoint_secant_acausal_at_derived_acausal_n':source_bad,
      'derived_source_endpoint_secant_acausal_at_derived_acausal_n':derived_bad,
      'original_native_cs2_max':float(original_cs2.max()),
      'derived_native_cs2_max':float(derived_cs2.max()),
      'native_sample_detail':details,
      'scientific_limit':'Source p/e secants and LAL native C derivative independently compared. Neither source labels nor spline excursions prove microscopic nuclear EOS false or repaired. Three other derived F140 models already passed F141 sampled gate and are not repeated.',
      'whole_star_source_Gibbs_mu':'NOT_CERTIFIED',
      'source_original_NICER_XPSI_BAYES':'NOT_COMPUTED'}
def run(f140,f141,source,outdir):
    import lalsimulation as ls
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    old,ledger=verify_f140(f140)
    f141file=Path(f141)/'F141_REAL_SIX_STATIC_TOV.json'
    if sha(f141file)!=PREVIOUS_F141_SHA:raise ValueError('F141_ORIGINAL_SOURCE_SHA_MISMATCH')
    prev=json.loads(f141file.read_text())
    if prev.get('native_real_two_tolerance_models_passed')!=6 or set(prev.get('static_GR_C_stars',{}))!=set(ledger.keys()) and len(prev.get('static_GR_C_stars',{}))!=6:
        raise ValueError('F141_REAL_COMPLETION_NOT_VERIFIED')
    for name in BAD:
        if prev['static_GR_C_stars'][name]['full_occupied_pressure_path_native_causality']['fully_positive_and_causal_on_scanned_static_path']:
            raise ValueError('F141_ACAUSAL_C_MODEL_SOURCE_DRIFT:'+name)
    report={'schema':'F142_NATIVE_LAL_ORIGINAL_VS_DERIVED_CAUSALITY_SOURCE_PROBE_V1',
      'jester_commit':JESTER_COMMIT,'F140_real_run':F140_RUN,'F141_real_run':F141_RUN,
      'F141_previous_json_sha256':PREVIOUS_F141_SHA,
      'original_eos_bytes_not_modified':True,
      'three_original_models':{},'status':'IN_PROGRESS'}
    path=out/'F142_REAL_LAL_NATIVE_SOURCE_CAUSALITY.json'
    for name in BAD:
        try:
            p,e,cs=source_gate(Path(source)/(name+'.npz'),name)
            original=ls.SimNeutronStarEOSByName(name)
            new=ls.SimNeutronStarEOSFromFile(str((Path(f140)/(name+'_F140_DERIVED_NOT_ORIGINAL_EOS_SI.txt')).resolve()))
            table=read_candidate(f140,name)
            pc=prev['static_GR_C_stars'][name]['central_pressure_geom_m_minus2']
            q=np.geomspace(float(max(table[0,0],p[0]))*1.000000001,float(pc),8193)
            original_cs2=derivative_profile(ls,original,q)
            derived_cs2=derivative_profile(ls,new,q)
            item=summarize_original_derived(name,p,e,table,original_cs2,derived_cs2,q)
        except Exception as exc: item={'eos':name,'status':'FAIL_CLOSED','error':repr(exc)}
        report['three_original_models'][name]=item
        path.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
        print('F142_REAL_SOURCE_COMPARE',name,item['status'], flush=True)
    report['status']='THREE_REAL_LAL_SOURCE_VS_INTERPOLANT_EVALUATED' if all(v['status']=='ORIGINAL_VS_DERIVED_NATIVE_COMPARISON_COMPLETE' for v in report['three_original_models'].values()) else 'FAIL_CLOSED_PARTIAL'
    path.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    (out/'F142_SHA256.json').write_text(json.dumps({path.name:sha(path)},sort_keys=True,indent=2)+'\n')
    print('F142_FINISHED',report['status'],flush=True)
    return 0 if report['status'].startswith('THREE') else 2
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--f140',required=True);p.add_argument('--f141',required=True);p.add_argument('--source',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();raise SystemExit(run(a.f140,a.f141,a.source,a.out))

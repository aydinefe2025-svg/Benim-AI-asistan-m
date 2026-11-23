#!/usr/bin/env python3
"""F140: real LAL derived local cold seam repair (not original nuclear EOS certification)."""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f139'))
from f139_shared_crust_seam import SOURCE_SHAS,JESTER_COMMIT,KNOT,source_gate,native_api
C=299792458.0;G=6.67430e-11;CONV=C**4/G
PATCHED=tuple(n for n in SOURCE_SHAS if n!='APR4_EPP')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bridge_analytic(p0,p1,e0,e1,n0,points=129):
    if not all(math.isfinite(float(x)) and float(x)>0 for x in (p0,p1,e0,e1,n0)):
        raise ValueError('NONPOSITIVE_BOUNDARY')
    if p1<=p0 or not 3<=points<=8193:raise ValueError('INVALID_BRIDGE_DOMAIN')
    s=(e1-e0)/(p1-p0)
    if not math.isfinite(s) or s<=1.0000000001:raise ValueError('ENDPOINT_CAUSAL_NO_GO')
    pp=np.linspace(p0,p1,points);ee=e0+s*(pp-p0)
    ww=ee+pp;w0=e0+p0
    hh=np.log(ww/w0)/(s+1.)
    nn=n0*(ww/w0)**(s/(s+1.));mu=ww/nn
    if not (np.all(np.diff(pp)>0) and np.all(np.diff(ee)>0) and np.all(np.diff(nn)>0)):
        raise AssertionError('NONMONOTONIC_BRIDGE')
    if np.max(np.abs(mu/mu[0]-np.exp(hh)))>2e-12:raise AssertionError('COLD_FIRST_LAW_FAIL')
    return {'p':pp,'e':ee,'n':nn,'h':hh,'mu':mu,'slope':float(s),'cs2':float(1/s)}
def choose_native_seam(p,e,knot=KNOT,max_expand=80,min_width=2):
    if not (len(p)==len(e) and 0<knot<len(p)-1 and np.all(np.diff(p)>0)):
        raise ValueError('INVALID_SOURCE')
    for width in range(min_width,max_expand+1):
        lo=knot-width;hi=knot+width
        if lo<=0 or hi>=len(p)-1:break
        de=float(e[hi]-e[lo]);dp=float(p[hi]-p[lo])
        if de>dp*(1+1e-10) and de>0:return lo,hi
    raise ValueError('NO_CAUSAL_ENVELOPE_FOR_ORIGINAL_ENDPOINTS')
def assemble_derived(p,e,lo,hi,bridge):
    if lo<1 or hi>len(p)-2 or not lo<hi:raise ValueError('INVALID_SPLICE_BOUNDS')
    pp=np.r_[p[:lo],bridge['p'],p[hi+1:]]
    ee=np.r_[e[:lo],bridge['e'],e[hi+1:]]
    if len(pp)!=len(ee) or np.any(np.diff(pp)<=0):raise ValueError('SPLICE_PRESSURE_FAIL')
    if np.any(ee<=0):raise ValueError('SPLICE_ENERGY_FAIL')
    if not (np.array_equal(pp[:lo],p[:lo]) and np.array_equal(pp[-(len(p)-hi-1):],p[hi+1:])):
        raise AssertionError('ORIGINAL_OUTSIDE_SOURCE_PRESSURE_MODIFIED')
    return pp,ee
def write_lal_two_col(p,e,out):
    """LAL 2-col EOS FromFile SI pressure Pa; energy density J/m^3."""
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',encoding='ascii',newline='\n') as f:
        for q,v in zip(p,e):f.write(f'{float(q)*CONV:.17e} {float(v)*CONV:.17e}\n')
    return sha(out)
def make_one(ls,name,source_dir,out_dir):
    p,e,cs=source_gate(Path(source_dir)/(name+'.npz'),name)
    if name not in PATCHED:raise ValueError('CONTROL_EOS_MUST_REMAIN_UNCHANGED')
    eos=ls.SimNeutronStarEOSByName(name)
    energy=native_api(ls,'SimNeutronStarEOSEnergyDensityOfPressureGeometrized')
    deriv=native_api(ls,'SimNeutronStarEOSEnergyDensityDerivOfPressureGeometrized')
    geth=native_api(ls,'SimNeutronStarEOSPseudoEnthalpyOfPressureGeometrized')
    getrho=native_api(ls,'SimNeutronStarEOSRestMassDensityOfPseudoEnthalpyGeometrized')
    native_e=np.array([float(energy(float(q),eos)) for q in p])
    if np.any(~np.isfinite(native_e)) or np.any(native_e<=0):raise ValueError('BAD_NATIVE_ENERGY')
    # Detect the entire negative-derivative interval, rather than removing one bad knot.
    failures=[]
    for i in range(KNOT-12,KNOT+12):
        for frac in (0.,.25,.5,.75,1.):
            q=math.exp(math.log(p[i])*(1-frac)+math.log(p[i+1])*frac)
            d=float(deriv(float(q),eos))
            if not math.isfinite(d) or d<=0:failures.append(i)
    if not failures:raise ValueError('NO_ORIGINAL_NATIVE_NEGATIVE_REGION_REPRODUCED')
    needed=max(2,max(abs(i-KNOT) for i in failures)+2)
    lo,hi=choose_native_seam(p,native_e,min_width=needed)
    h0=float(geth(float(p[lo]),eos));rho0=float(getrho(h0,eos))
    if not (math.isfinite(h0) and math.isfinite(rho0) and rho0>0):raise ValueError('NO_NATIVE_RHO_ANCHOR')
    bridge=bridge_analytic(float(p[lo]),float(p[hi]),float(native_e[lo]),float(native_e[hi]),rho0)
    pp,ee=assemble_derived(p,native_e,lo,hi,bridge)
    dst=Path(out_dir)/(name+'_F140_DERIVED_NOT_ORIGINAL_EOS_SI.txt')
    digest=write_lal_two_col(pp,ee,dst)
    if not hasattr(ls,'SimNeutronStarEOSFromFile'):raise RuntimeError('NATIVE_LAL_FROMFILE_MISSING')
    patched=ls.SimNeutronStarEOSFromFile(str(dst.resolve()))
    for ix in (lo,(lo+hi)//2,hi):
        q=float(p[ix]);got=float(energy(q,patched));wanted=float(np.interp(q,pp,ee))
        if not math.isfinite(got) or abs(got/wanted-1)>5e-3:
            raise ValueError(f'NATIVE_LAL_TWO_COL_UNIT_OR_INTERPOLATION_MISMATCH:{name}:{ix}')
    # Scan beyond both edges: fail if the negative region was merely pushed out.
    grid=np.geomspace(float(p[KNOT-12]),float(p[KNOT+12]),1537)
    de=np.array([float(deriv(float(q),patched)) for q in grid])
    if not np.all(np.isfinite(de)):raise ValueError('DERIVED_NATIVE_NAN_CS2')
    cs2=1/de
    if np.any(cs2<=0) or np.any(cs2>1.+1e-9):
        raise ValueError(f'DERIVED_NATIVE_LOCAL_CAUSALITY_FAIL:{name}:{np.min(cs2)}:{np.max(cs2)}')
    hs=np.array([float(geth(float(q),patched)) for q in grid])
    es=np.array([float(energy(float(q),patched)) for q in grid])
    rhos=np.array([float(getrho(float(h),patched)) for h in hs])
    if np.any(rhos<=0) or np.any(~np.isfinite(rhos)):raise ValueError('DERIVED_NATIVE_FIRST_LAW_RHO_INVALID')
    mu=(es+grid)/rhos
    maxres=float(np.max(np.abs(np.log(mu/mu[0])-(hs-hs[0]))))
    if maxres>2e-3:raise ValueError(f'DERIVED_NATIVE_FIRST_LAW_RESIDUAL:{maxres}')
    hright=float(geth(float(p[hi]),eos));rright=float(getrho(hright,eos))
    mu_right_native=(float(native_e[hi])+float(p[hi]))/rright
    mu_right_derived=float((float(energy(float(p[hi]),patched))+float(p[hi]))/float(getrho(float(geth(float(p[hi]),patched)),patched)))
    return {'name':name,'source_sha256':SOURCE_SHAS[name],
      'derived_eos_path':str(dst),'derived_eos_sha256':digest,
      'left_knot':lo,'right_knot':hi,'bad_original_interval_indices':sorted(set(failures)),
      'removed_original_internal_knots':hi-lo-1,
      'cold_bridge_exact_cs2':bridge['cs2'],
      'native_derived_min_cs2':float(np.min(cs2)),'native_derived_max_cs2':float(np.max(cs2)),
      'derived_native_cold_mu_h_max_absolute_log_residual':maxres,
      'original_to_derived_mu_right_fractional_difference':float(mu_right_derived/mu_right_native-1.),
      'global_gibbs_consistency':'NOT_ESTABLISHED',
      'physical_eos_identity':'DERIVED_NUMERICAL_LOCAL_BRIDGE_NOT_ORIGINAL_NUCLEAR_MODEL',
      'native_static_tov':'NOT_RUN','native_rotating_c_star':'NOT_RUN',
      'seven_eos_photon_bayes':'NOT_COMPUTED'}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source-dir',required=True);ap.add_argument('--out-dir',required=True)
    a=ap.parse_args();import lalsimulation as ls
    dst=Path(a.out_dir);dst.mkdir(parents=True,exist_ok=True)
    report={'schema':'J0740_F140_COLD_SEAM_DERIVED_VALIDATION_V1',
      'source_jester_commit':JESTER_COMMIT,'models':{},'status':'IN_PROGRESS',
      'original_files_unchanged':True,'global_physical_certificate':'NOT_ESTABLISHED',
      'bayes_posterior':'NOT_COMPUTED'}
    path=dst/'F140_NATIVE_COLD_SEAM_RESULT.json'
    for name in PATCHED:
        try:
            report['models'][name]={'status':'LOCAL_DERIVED_COLD_NATIVE_LAL_PASS',**make_one(ls,name,a.source_dir,dst)}
        except Exception as exc:
            report['models'][name]={'status':'FAIL_CLOSED','error':repr(exc)}
        path.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
        print('F140',name,report['models'][name]['status'],flush=True)
    report['status']='SIX_DERIVED_LOCAL_NATIVE_LAL_PASS_NOT_GLOBAL' if all(r['status']=='LOCAL_DERIVED_COLD_NATIVE_LAL_PASS' for r in report['models'].values()) else 'PARTIAL_FAIL_CLOSED'
    path.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    (dst/'F140_SHA256.json').write_text(json.dumps({p.name:sha(p) for p in dst.iterdir() if p.is_file() and p.name!='F140_SHA256.json'},indent=2,sort_keys=True)+'\n')
    return 0 if report['status'].startswith('SIX_DERIVED') else 2
if __name__=='__main__':raise SystemExit(main())

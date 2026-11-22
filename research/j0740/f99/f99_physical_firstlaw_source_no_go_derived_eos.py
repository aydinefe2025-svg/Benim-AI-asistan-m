#!/usr/bin/env python3
"""J0740 F99 genuine EOS source no-go and distinct cold causal piecewise-linear derived model.

No modification or certification of original CompOSE 328 APR source: published source
and original F88 RNS numerical 1933 rows have finite precision. For those exact
byte-valued endpoints, three intervals violate the joint first-law + causal
existence bound. Construct a *different* cold barotrope P(epsilon) with rederived
baryon density n and enthalpy H from exact analytic interval integrals;
RNS four-point cubic re-interpolation is not itself exactly thermodynamic.
"""
import argparse, hashlib, json, math, sys
from pathlib import Path
import numpy as np
C=2.99792458e10
SHA_SOURCE='7643d0e4361adee77cc79d1b69eb445db70a52443b833c4dddafa973193fb580'
SOURCE_ZIP_SHA='8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12'
ADD={1830:12,1831:12,1908:12,1909:12}
assert sum(ADD.values())==48

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def log_integral(E0,P0,E1,P1):
  b=(P1-P0)/(E1-E0)
  assert b>-1
  return math.log1p((E1+P1-E0-P0)/(E0+P0))/(1+b)

def admissible_bounds(e0,p0,e1,p1):
  """For 0 <= P' <= 1 with fixed P endpoints, early-vs-late pressure rise yields bounds on ln(n1/n0)."""
  d=p1-p0; de=e1-e0
  if d<0 or d>de:return None
  return (log_integral(e0,p0,e0+d,p1)+log_integral(e0+d,p1,e1,p1),
          log_integral(e0,p0,e1-d,p0)+log_integral(e1-d,p0,e1,p1))

def no_go(a):
  failures=[]; intervals=0; nominal_causal=0
  for i,(l,r) in enumerate(zip(a[:-1],a[1:])):
    e0,p0,n0=l[0]*C*C,l[1],l[3]
    e1,p1,n1=r[0]*C*C,r[1],r[3]
    if not(e0<e1 and p0<p1 and n0<n1):raise ValueError('source not monotonic')
    if l[0]>1.8300109355e15:continue
    intervals+=1
    u=admissible_bounds(e0,p0,e1,p1)
    if u is None:continue
    nominal_causal+=1
    obs=math.log(n1/n0)
    # use generous absolute slack of 1e-8 so interval failures >> floating-point noise
    if obs<u[0]-1e-8 or obs>u[1]+1e-8:
      failures.append({'source_interval_0based':i,'rho_left':l[0],'rho_right':r[0],
        'secant_cs2':(p1-p0)/(e1-e0),'observed_log_n_ratio':obs,
        'firstlaw_causal_min_log_n_ratio':u[0], 'firstlaw_causal_max_log_n_ratio':u[1],
        'signed_log_ratio_excess':obs-min(max(obs,u[0]),u[1])})
  return {'source_intervals_below_original_acausal_first_node':intervals,
          'source_secant_causal_intervals':nominal_causal,'exact_endpoints_no_go_intervals':failures,
          'source_exact_finite_precision_nodes_immutable':True,
          'claim':'NO smooth causal cold-barotropic EOS can match all four EXACT n,P,epsilon endpoints across these intervals; not a claim source measurement physically impossible within source rounding'}

def derived(a):
  s=a.copy()
  # Distinct high-density causal extension, rather than silently claiming source original is causal.
  for i in range(1909,len(s)-1):
    s[i+1,1]=s[i,1]+0.99*(s[i+1,0]-s[i,0])*C*C
  t=[]
  for i in range(len(s)-1):
    t.append(s[i:i+1])
    if i in ADD:
      f=np.arange(1,ADD[i]+1)/(ADD[i]+1)
      t.append(s[i:i+1]+f[:,None]*(s[i+1:i+2]-s[i:i+1]))
  t.append(s[-1:])
  x=np.vstack(t)
  eps=x[:,0]*C*C;p=x[:,1]
  slope=np.diff(p)/np.diff(eps)
  if not np.all((slope>0)&(slope<=1+1e-12)):raise ValueError('BAD_DERIVED_P_E_CAUSALITY')
  logn=np.zeros(len(x)); logn[0]=math.log(s[0,3]); h=np.zeros(len(x));h[0]=s[0,2]
  for i in range(len(x)-1):
    I=log_integral(eps[i],p[i],eps[i+1],p[i+1])
    logn[i+1]=logn[i]+I
    # exact analytic integration of dH=c^2 dP/(epsilon+P) on each affine segment
    h[i+1]=h[i]+C*C*slope[i]*I
  x[:,2]=h; x[:,3]=np.exp(logn)
  if not np.all(np.diff(x,axis=0)>0):raise ValueError('DERIVED_H_N_NOT_MONOTONIC')
  # Exact recurrence residual, distinct from RNS cubic interpolation residual
  err_n=max(abs((logn[i+1]-logn[i])-log_integral(eps[i],p[i],eps[i+1],p[i+1])) for i in range(len(x)-1))
  err_h=max(abs((h[i+1]-h[i])/C**2-slope[i]*log_integral(eps[i],p[i],eps[i+1],p[i+1])) for i in range(len(x)-1))
  return x,{'derived_nodes':len(x),'added_derived_interpolation_nodes':48,
    'source_original_P_eps_preserved_up_to_index_1909':True,
    'original_source_h_n_preserved':False,'original_source_high_density_pressure_above_node_1909_preserved':False,
    'min_affine_cs2':float(slope.min()),'max_affine_cs2':float(slope.max()),
    'max_abs_node_firstlaw_log_n_recurrence_residual':float(err_n),
    'max_abs_node_integrated_H_recurrence_residual':float(err_h),
    'source_1933_original_rows_unchanged_in_derived_model':False,
    'calculated_thermodynamic_continuous_representation':'piecewise linear P(eps); n(eps) and H(eps) analytically integrated within every source interval',
    'important_limit':'upstream C RNS four-point cubic log interpolates epsilon(P), P(epsilon), H(P) and n(epsilon) separately; this does NOT guarantee continuous thermodynamic identity of C-evaluated interpolation; must audit separately'}

def main(args):
  src=Path(args.source)
  if sha(src)!=SHA_SOURCE:raise ValueError('SOURCE_SHA_NOT_original')
  a=np.loadtxt(src,skiprows=1)
  if a.shape!=(1933,4):raise ValueError('SOURCE_SHAPE')
  no=no_go(a)
  if [x['source_interval_0based'] for x in no['exact_endpoints_no_go_intervals']]!=[1831,1907,1908]:
    raise ValueError('SOURCE_SCIENCE_DRIFT_NO_GO_NOT_FOUND')
  t,info=derived(a)
  assert len(t)==1981 and t.shape[1]==4
  out=Path(args.out);out.parent.mkdir(exist_ok=True,parents=True)
  with out.open('w',encoding='ascii') as f:
    f.write(str(len(t))+'\n')
    for row in t:f.write(' '.join(f'{v:.17e}' for v in row)+'\n')
  # Back-read original source and derived format at exact float precision.
  rt=np.loadtxt(out,skiprows=1)
  assert np.array_equal(rt,t)
  info.update({'output_SHA256':sha(out),'source_RNS_original_1933_SHA256':SHA_SOURCE,
               'publisher_original_zip_SHA256':SOURCE_ZIP_SHA,'status':'DISTINCT_DERIVED_CAUSAL_COLD_AFFINE_THERMODYNAMIC_EOS_NOT_ORIGINAL_SOURCE'})
  receipt={'schema':'J0740_F99_SOURCE_NODES_EXACT_FIRSTLAW_CAUSAL_NO_GO_DISTINCT_DERIVED_AFFINE_EOS_V1',
           'original_source_no_go':no,'derived_model':info,
           'rotating_C_equilibrium':'NOT_RUN_FOR_DERIVED_F99',
           'source_native_seven_EOS_Bayes':'NOT_RUN',
           'rotating_axisymmetric_dynamical_eigenmodes':'NOT_RUN'}
  path=Path(args.report);path.parent.mkdir(exist_ok=True,parents=True)
  path.write_text(json.dumps(receipt,sort_keys=True,indent=2,allow_nan=False)+'\n')
  print(json.dumps({'source_unrepairable_exact_intervals':[x['source_interval_0based'] for x in no['exact_endpoints_no_go_intervals']],**info},indent=2))

if __name__=='__main__':
  p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);p.add_argument('--report',required=True);main(p.parse_args())

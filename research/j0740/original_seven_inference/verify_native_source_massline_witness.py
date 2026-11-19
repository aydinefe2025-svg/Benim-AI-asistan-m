#!/usr/bin/env python3
"""Independent CI re-integration of original 7 EOS with archived F38 mass-line witness.

This CI independently reads 7 pristine JESTER NPZs. It verifies compact F38
line values, support mask, normalizations, and all 42 integrated scores.
The full F38 2-D source grids live in the offline all-input ZIP and retain an
independently-checked immutable SHA; the trace is *not* claimed to replace it.
"""
from __future__ import annotations
import argparse,base64,hashlib,io,json,zlib
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.integrate import simpson
from original_seven_fullmass_integral import PINNED_NPZ_SHA,PINNED_F38_SHA,PINNED_SEVEN_SHA,M_LOW,M_HIGH,density,xpsi_source_support

def verify(root,witness_path,report_path):
  trace=json.loads(Path(witness_path).read_text());report=json.loads(Path(report_path).read_text())
  assert trace['schema']=='j0740_original_seven_F38_fullmass_line_witness_v1'
  assert trace['original_eos_zip_sha256']==PINNED_SEVEN_SHA
  assert trace['original_source_F38_six_kde_zip_sha256']==PINNED_F38_SHA
  assert report['original_eos_zip_sha256']==PINNED_SEVEN_SHA
  assert report['source_reconstructed_likelihood_zip_sha256']==PINNED_F38_SHA
  names=sorted(PINNED_NPZ_SHA);keys=trace['surface_keys'];n=trace['n_line_mass_nodes_per_model']
  assert trace['model_names']==names and set(keys)==set(report['six_F38_KDE_surfaces'])
  assert len(keys)==6 and n==401 and trace['float_array_shape']==[6,7,401] and trace['array_dtype']=='<f4'
  raw=zlib.decompress(base64.b64decode(trace['ratio_line_arrays_base64_zlib'],validate=True))
  assert hashlib.sha256(raw).hexdigest()==trace['array_raw_sha256']
  values=np.frombuffer(raw,dtype='<f4').reshape(6,7,n)
  assert np.isfinite(values).all() and np.all(values>=0)
  curves={}
  for name in names:
    path=Path(root)/(name+'.npz')
    assert hashlib.sha256(path.read_bytes()).hexdigest()==PINNED_NPZ_SHA[name],name
    a=np.load(path,allow_pickle=False);m=a['masses_EOS'];r=a['radii_EOS'];use=m>=1.
    assert len(m)>=450 and len(m)<=500 and np.all(np.diff(m[use])>0)
    curves[name]=(PchipInterpolator(m[use],r[use],extrapolate=False),float(m.max()))
  maxdiff=0;scorecount=0
  for k,key in enumerate(keys):
    denom=0.
    for j,name in enumerate(names):
      curve,mmax=curves[name]
      masses=np.linspace(M_LOW,min(M_HIGH,mmax),n)
      allowed=xpsi_source_support(masses,curve(masses))
      y=np.asarray(values[k,j],float)
      assert not np.any(y[~allowed]), (key,name,'leaked under source prior')
      estimate=float(simpson(density(masses)*y,x=masses))
      expected=report['six_F38_KDE_surfaces'][key]['model_scores'][name]['value']
      error=abs(estimate/expected-1) if expected>0 else abs(estimate)
      maxdiff=max(error,maxdiff)
      if error>.002:raise ValueError(f'Witness-vs-original-2d-integral failed {name}/{key}: {estimate} vs {expected}={error}')
      denom+=estimate;scorecount+=1
    assert denom>0
  assert scorecount==42
  return {'status':'SEVEN_ORIGINAL_NPZ_CI_REINTEGRATION_42_OF_42_PASS','score_count':scorecount,
          'max_relative_deviation_against_full_F38_grid':maxdiff,
          'original_eos_models':names,'six_actual_f38_sources':keys,
          'important_limitation':'Independent CI is on the archived mass-line witness; full 2D F38 ZIP is included in offline reproduction archive, not reconstructed in CI.'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source-directory',required=True,type=Path);p.add_argument('--witness',required=True,type=Path);p.add_argument('--report',required=True,type=Path);p.add_argument('--out',type=Path);a=p.parse_args()
 res=verify(a.source_directory,a.witness,a.report)
 if a.out:a.out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n')
 print(json.dumps(res,sort_keys=True))

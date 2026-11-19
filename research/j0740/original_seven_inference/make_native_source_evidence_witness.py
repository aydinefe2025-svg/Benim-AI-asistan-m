#!/usr/bin/env python3
"""Compact complete mass-line witness derived from the six immutable F38 2-D grids.
The archival six complete F38 NPZ grids remain inside the full offline ZIP.
"""
import base64,hashlib,io,json,zlib,zipfile
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
from original_seven_fullmass_integral import (PINNED_F38_SHA,PINNED_SEVEN_SHA,PINNED_NPZ_SHA,
    M_LOW,M_HIGH,load_eos,load_surface,density,xpsi_source_support,sha)
N=401
SURFACES=['weighted_0.015_0.20','weighted_0.025_0.35','weighted_0.040_0.50',
          'resampled_0.015_0.20','resampled_0.025_0.35','resampled_0.040_0.50']
MODELS=sorted(PINNED_NPZ_SHA)
def make(eos,f38,out):
    if sha(eos)!=PINNED_SEVEN_SHA or sha(f38)!=PINNED_F38_SHA:
        raise ValueError('unpinned source archives')
    grid=np.zeros((len(SURFACES),len(MODELS),N),dtype='<f4')
    with zipfile.ZipFile(eos) as ez,zipfile.ZipFile(f38) as fz:
      info={name:load_eos(ez,name) for name in MODELS}
      for i,key in enumerate(SURFACES):
        f,_=load_surface(fz,key)
        for j,name in enumerate(MODELS):
            curve,mmax,_,_=info[name]
            m=np.linspace(M_LOW,min(M_HIGH,mmax),N);r=curve(m)
            arr=f(np.column_stack([m,r]));arr[~xpsi_source_support(m,r)]=0
            grid[i,j,:]=arr
    binary=grid.tobytes()
    d={'schema':'j0740_original_seven_F38_fullmass_line_witness_v1',
      'original_eos_zip_sha256':PINNED_SEVEN_SHA,
      'original_source_F38_six_kde_zip_sha256':PINNED_F38_SHA,
      'surface_keys':SURFACES,'model_names':MODELS,'n_line_mass_nodes_per_model':N,
      'float_array_shape':list(grid.shape),'array_dtype':'<f4',
      'array_raw_sha256':hashlib.sha256(binary).hexdigest(),
      'ratio_line_arrays_base64_zlib':base64.b64encode(zlib.compress(binary,9)).decode(),
      'line_mass_rule':'np.linspace(1.7305, min(2.4335, original_JESTER_static_Mtov), 401)',
      'warning':'F38 exact full grids required for independent pixel-by-pixel audit; this is a compact witnessed derived trace'}
    out.write_text(json.dumps(d,sort_keys=True,separators=(',',':'))+'\n')
    print('TRACE size',out.stat().st_size,'gz-blob',len(zlib.compress(binary,9)))
    return d
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--eos',type=Path,required=True);p.add_argument('--f38',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 make(a.eos,a.f38,a.out)

#!/usr/bin/env python3
"""F88: RNS table from real published CompOSE unified APR(APR), plus visibly labeled
analytical low-density extension below native 1e-11 fm^-3 so upstream C/RNS surface
(7.8 g/cm3, 1.01e8 dyn/cm2) lies INSIDE the tabulated support.

No modification of 1833 original CompOSE nodes. Extended model DISTINCT from the
original published table; no EOS evidence or microscopic physical certification.
"""
from __future__ import annotations
import argparse, hashlib,json,math,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f87'))
from f87_real_tov_from_compose import EOS,ONE_MEVFM3,C

N_EXTENSION=100
NB_BOTTOM=1e-20
RNS_SURFACE_P_CGS=1.01e8
RNS_SURFACE_RHO_CGS=7.8

def create(source:Path,out:Path,outjson:Path):
    e=EOS(source)
    n0,P0,E0=map(float,(e.nb[0],e.P[0],e.E[0]))
    gamma=float(math.log(e.P[1]/P0)/math.log(e.nb[1]/n0))
    if not 1<gamma<3:raise RuntimeError('UNPHYSICAL_EXPLICIT_LOW_DENSITY_EXTENSION_GAMMA')
    rest=(E0-P0/(gamma-1))/n0
    if not 900<rest<960:raise RuntimeError('WRONG_SOURCE_MATCHED_REST_MASS')
    extn=np.geomspace(NB_BOTTOM,n0,N_EXTENSION+1)[:-1]
    extP=P0*(extn/n0)**gamma
    extE=rest*extn+extP/(gamma-1)
    nb=np.r_[extn,e.nb];p=np.r_[extP,e.P];en=np.r_[extE,e.E]
    mu=(en+p)/nb
    # Physical cold chemical-potential enthalpy relative zero-density extension.
    h=np.log1p((mu-rest)/rest)
    if len(nb)>2000 or len(nb)!=1933 or np.any(h<=0) or not np.all(np.diff(h)>0):
        raise RuntimeError('RNS_ENTHALPY_SOURCE_BAD')
    if not(np.all(np.diff(en)>0) and np.all(np.diff(p)>0) and np.all(np.diff(nb)>0)):
        raise RuntimeError('RNS_EOS_PHYSICAL_COLUMNS_NONMONOTONE')
    rows=np.array([en*ONE_MEVFM3/C**2,p*ONE_MEVFM3,h*C*C,nb*1e39]).T
    if not rows[0,0]<RNS_SURFACE_RHO_CGS or not rows[0,1]<RNS_SURFACE_P_CGS:
        raise RuntimeError('RNS_HARD_CODED_SURFACE_OUTSIDE_EOS_RANGE')
    for j in range(4):
        if not np.all(np.isfinite(rows[:,j])) or not np.all(np.diff(rows[:,j])>0):
            raise RuntimeError('RNS_BAD_OR_NONMONOTONE_PHYSICAL_COLUMN_'+str(j))
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w') as f:
        f.write(str(len(rows))+'\n')
        for row in rows:f.write(' '.join(f'{z:.16e}' for z in row)+'\n')
    filehash=hashlib.sha256(out.read_bytes()).hexdigest()
    meta={'schema':'F88_EXPLICIT_SOURCE_PRESERVING_UNIFIED_APR_RNS_SURFACE_EXTENSION_V1',
          'status':'RNS_INPUT_PREPARED_NOT_YET_C_EINSTEIN_STAR',
          'original_APR_compose_sha256':e._source_sha if hasattr(e,'_source_sha') else hashlib.sha256((Path(source)/'F87_verified_publisher_original.zip').read_bytes()).hexdigest(),
          'original_native_rows_not_modified':1833,'analytical_extension_rows':N_EXTENSION,
          'model':'CompOSE_APR_APR_UNIFIED_CRUST_PLUS_EXPLICIT_LOW_DENSITY_POLYTROPE_NOT_ORIGINAL_SOURCE',
          'extend_range_nB_fm3':[NB_BOTTOM,n0],'extension_gamma_from_first_two_native_P_n_rows':gamma,
          'extension_rest_chemical_potential_MeV':rest,'cold_first_law_exact_on_extension':True,
          'native_chemical_potential_enthalpy_h_method':'h=ln((epsilon+P)/(n_B*rest)); original P epsilon n_B unmodified, not guaranteed exact integrated firstlaw on every original native interval',
          'original_source_max_cs2':float(e.cs_source.max()),'original_source_nodes_cs2_gt1':int(np.sum(e.cs_source>1)),
          'rns_input_file_sha256':filehash,'rns_rows':len(rows),
          'rns_first_physical_row':rows[0].tolist(),'rns_first_native_row':rows[N_EXTENSION].tolist(),
          'source_RNS_surface_rho_p_coverage':[float(rows[0,0]),float(rows[0,1])],
          'full_real_GR_C_RNS':'NOT_RUN','original_source_photon_likelihood_new_calls':0,
          'important_caveat':'Original EOS high density acausal; extension changes surface model below 1e-11 fm-3. RNS source C uses its native enthalpy interpolation, not source CompOSE smooth thermodynamics.'}
    outjson=Path(outjson);outjson.parent.mkdir(parents=True,exist_ok=True);outjson.write_text(json.dumps(meta,indent=2)+'\n')
    return meta

if __name__=='__main__':
  p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out-eos',type=Path,required=True);p.add_argument('--out-json',type=Path,required=True);a=p.parse_args()
  print(json.dumps(create(a.source,a.out_eos,a.out_json),indent=2))

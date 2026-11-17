"""Independently query the actual LALSimulation APR4_EPP EOS below JESTER p_min.

Record exact library version and original NPZ SHA, refuse claims on version drift.
Does not mutate EOS, create a physical candidate, or run RNS GR.
"""
import argparse,json,hashlib,math,traceback
from pathlib import Path
import numpy as np

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
EXPECTED='639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88'

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--npz',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 import lalsimulation as ls
 import lal
 if sha(a.npz)!=EXPECTED:raise ValueError('JESTER APR4 source SHA mismatch')
 with np.load(a.npz,allow_pickle=False) as z:
  p0,e0,h0=float(z['p'][0]),float(z['e'][0]),float(z['h'][0])
 eos=ls.SimNeutronStarEOSByName('APR4_EPP')
 allnames=[s for s in dir(ls) if 'NeutronStarEOS' in s and ('MinPressure' in s or 'RestMassDensity' in s or 'PseudoEnthalpy' in s)]
 def method(n,*args):
  fn=getattr(ls,n,None)
  if not fn:return None,'UNAVAILABLE'
  try:
   v=float(fn(*args))
   if not math.isfinite(v):return None,'NONFINITE'
   return v,'OK'
  except Exception as exc:return None,type(exc).__name__+': '+str(exc)[:180]
 native_min,ms=method('SimNeutronStarEOSMinPressureGeometerized',eos)
 info={'schema':'J0740_APR4_native_LALSuite_P0_source_probe_v1',
  'source_sha256':EXPECTED,'source_p0':p0,'source_e0':e0,'source_h0':h0,
  'lalsuite_python_version':getattr(ls,'__version__','missing'),'lal_python_version':getattr(lal,'__version__','missing'),
  'minimum_pressure_geo':native_min,'minimum_pressure_status':ms,'api_methods':allnames,
  'sources_caution':'LALSuite wheel version identified here is NOT proven identical to version used by pinned JESTER NPZ generator',
  'samples':[]}
 for exp in [0,-.1,-.5,-1,-1.5,-2,-3,-4,-5,-6,-8,-10,-12]:
  p=p0*(10.0**exp)
  item={'log10_p_over_JESTER_p0':exp,'p_geo_m_minus2':p}
  for name,label in [
   ('SimNeutronStarEOSEnergyDensityOfPressureGeometerized','e_geo'),
   ('SimNeutronStarEOSPseudoEnthalpyOfPressureGeometerized','h'),
   ('SimNeutronStarEOSEnergyDensityDerivOfPressureGeometerized','de_dp_geo')]:
   v,status=method(name,p,eos);item[label]=v;item[label+'_status']=status
  if item['h'] is not None:
   v,status=method('SimNeutronStarEOSRestMassDensityOfPseudoEnthalpyGeometerized',item['h'],eos)
   item['rest_mass_geo']=v;item['rest_mass_status']=status
  if item['de_dp_geo'] is not None and item['de_dp_geo']!=0:item['cs2_native']=1/item['de_dp_geo']
  info['samples'].append(item)
 first=info['samples'][0]
 info['first_source_node_comparison']={
  'native_energy_rel_delta':(first['e_geo']/e0-1) if first['e_geo'] is not None else None,
  'native_enthalpy_abs_delta':(first['h']-h0) if first['h'] is not None else None,
  'matches_original_source_at_first_node':(abs(first['e_geo']/e0-1)<1e-8 and abs(first['h']-h0)<1e-8) if first['e_geo'] is not None and first['h'] is not None else False}
 info['lower_than_JESTER_p0_successes']=sum(x['e_geo'] is not None and x['h'] is not None for x in info['samples'][1:])
 a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(json.dumps(info,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf8')
 print(json.dumps({'min_p_geo':native_min,'min_p_status':ms,'lalsuite_version':info['lalsuite_python_version'],
  'source_first_node':info['first_source_node_comparison'],'lower_pressure_successes':info['lower_than_JESTER_p0_successes'],
  'records':[{k:v for k,v in z.items() if k in ('log10_p_over_JESTER_p0','e_geo','h','cs2_native','rest_mass_geo','e_geo_status')} for z in info['samples']]},ensure_ascii=False))
if __name__=='__main__':main()

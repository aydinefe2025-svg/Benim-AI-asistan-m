"""Interpolation-of-integrand sensitivity only: NOT new GR stellar models."""
import argparse,json,io,zipfile
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
from scipy.interpolate import PchipInterpolator
import f51_extended_support_audit as f

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--f38',type=Path,required=True)
 p.add_argument('--f44',type=Path,required=True)
 p.add_argument('--f48',type=Path,required=True)
 p.add_argument('--curves-dir',type=Path,required=True)
 p.add_argument('--out',type=Path,required=True)
 a=p.parse_args()
 roots=f.load_verified_curves({name:a.curves_dir/('F46_'+name+'.zip') for name in f.EOS},a.f44,a.f48)
 surfaces=f.source_zip(a.f38,'F38')
 result={'method':'PCHIP of R(M) between real C roots for quadrature diagnostic ONLY; not direct RNS stars or an EOS family model',
 'number_of_real_GR_stars':168,'dense_integration_nodes':1601,'surface_max_relative_disagreement':0,
 'per_surface':{}}
 for filename in sorted(x for x in surfaces if x.startswith('posterior_prior_ratio_') and x.endswith('npz')):
  mg,rg,L,mask=f.surface(surfaces,filename)
  data={}
  for name,curve in roots.items():
   m=curve['common_m'];r=curve['common_r']
   coarse=f.integral(m,f.sample(mg,rg,L,mask,m,r))['conditional_on_verified_mass_window_L_over_Z']
   fine_m=np.linspace(f.LO,f.HI,1601)
   fine_r=PchipInterpolator(m,r,extrapolate=False)(fine_m)
   fine=f.integral(fine_m,f.sample(mg,rg,L,mask,fine_m,fine_r))['conditional_on_verified_mass_window_L_over_Z']
   frac=abs(fine-coarse)/max(abs(fine),1.e-20)
   result['surface_max_relative_disagreement']=max(result['surface_max_relative_disagreement'],float(frac))
   data[name]={'coarse_actual_direct_root_quadrature':float(coarse),
               'dense_quadrature_with_interpolated_radius_fine_not_new_GR_roots':float(fine),
               'relative_fractional_disagreement':float(frac)}
  result['per_surface'][filename]=data
 a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 print('MAX_REL_QUADRATURE_SENSITIVITY',result['surface_max_relative_disagreement'])

if __name__=='__main__':main()

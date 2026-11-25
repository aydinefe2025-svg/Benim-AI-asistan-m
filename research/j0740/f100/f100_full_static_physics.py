#!/usr/bin/env python3
"""F100 physically new static TOV maximum + radial omega0² bifurcation on F99 DERIVED cold affine EOS.

This is NOT a mode calculation for rotating stars and NOT original 7-source EOS likelihood.
All source bytes pinned; F95 pulsation operator reused without modifying Einstein equations.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar,brentq

EOS_SHA='c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331'
GRIDS=(220,320,480,700)
PC_REFERENCE=418.74321216708

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def make_eos(path,R):
 if sha(path)!=EOS_SHA:raise ValueError('F99_ORIGINAL_DERIVED_COLD_SOURCE_SHA_CHANGED')
 a=np.loadtxt(path,skiprows=1)
 if a.shape!=(1981,4) or int(Path(path).open().readline().strip())!=1981:raise ValueError('WRONG_DERIVED_BAROTROPE')
 P=a[:,1]*(R.G*1e10/R.C**4);E=a[:,0]*R.C**2*(R.G*1e10/R.C**4)
 slopes=np.diff(P)/np.diff(E)
 if not np.all((slopes>0)&(slopes<1)):raise ValueError('FULL_SOURCE_MUST_BE_PHYSICALLY_CAUSAL')
 def eos(p):
  pp=np.clip(np.asarray(p,dtype=float),P[0],P[-1]);i=np.clip(np.searchsorted(P,pp,side='right')-1,0,len(P)-2)
  ee=E[i]+(pp-P[i])*(E[i+1]-E[i])/(P[i+1]-P[i]);cs=slopes[i]
  return ee,cs,(ee+pp)/pp*cs
 return P,E,slopes,eos

def solve(path,output,solver_root,mesh=GRIDS,rtol=4e-10,max_step=.026):
 sys.path.insert(0,str(solver_root))
 import f95_static_radial_modes as R
 P,E,slopes,eos=make_eos(path,R)
 def star(pc):return R.make_star(pc,eos,P,rtol=rtol,max_step=max_step)
 def mass(pc):return star(pc)['M']/R.MKM
 maxp=float(P[-1]/R.A)
 if maxp<1400:raise ValueError('DERIVED_MODEL_HIGH_DENSITY_SUPPORT_LOST')
 best=minimize_scalar(lambda p:-mass(p),bounds=(820.,1150.),method='bounded',options={'xatol':.002})
 if not best.success:raise RuntimeError('TOV_MAXIMIZATION_FAIL')
 Pc=float(best.x);sc=star(Pc)
 if not(900<Pc<1030 and 2.10<-best.fun<2.30):raise ValueError('F100_UNEXPECTED_PHYSICAL_TOV_MAX')
 stages=[('j0740_equilibrium',PC_REFERENCE),('stable_branch',900.),('tov_mass_maximum',Pc),('unstable_branch',985.),('deep_unstable_branch',1200.)]
 models=[]
 for label,p in stages:
  s=star(p);modes=[]
  for n in mesh:
   e=R.radial(s,eos,P,N=n)
   if e['node_counts'][:4]!=[0,1,2,3]:raise ValueError('MODE_ORDER_NODES_CHANGED_'+str(n))
   modes.append({'mesh':n,'omega0_squared_km_minus2':e['eigen_omega2_kmminus2'][0],'signed_f0_Hz':e['signed_frequency_hz'][0], 'nodes':e['node_counts'][0]})
  if label in ('j0740_equilibrium','stable_branch') and not all(x['omega0_squared_km_minus2']>0 for x in modes):raise ValueError('PHYSICAL_STABLE_BRANCH_NOT_POSITIVE')
  if label in ('unstable_branch','deep_unstable_branch') and not all(x['omega0_squared_km_minus2']<0 for x in modes):raise ValueError('PHYSICAL_UNSTABLE_BRANCH_NOT_NEGATIVE')
  models.append({'label':label,'central_P_MeVfm3':p,'M_Msun':s['M']/R.MKM,'R_km':s['R'],'modes':modes})
  print('F100_GR_PHYSICS',label,'P',round(p,5),'M',round(models[-1]['M_Msun'],8),'f0',[(x['mesh'],round(x['signed_f0_Hz'],2)) for x in modes],flush=True)
 roots=[]
 for n in mesh:
  def omega2(p):return R.radial(star(p),eos,P,N=n)['eigen_omega2_kmminus2'][0]
  root=brentq(omega2,940.,980.,xtol=.02,maxiter=25)
  delta=root-Pc
  if abs(delta)>3.:raise ValueError('TURNING_POINT_AND_DYNAMIC_RADIAL_ZERO_INCOMPATIBLE')
  roots.append({'mesh':n,'zero_omega0sq_P_MeVfm3':root,'delta_from_static_max_P_MeVfm3':delta,'relative_delta_pct':100*delta/Pc})
  print('F100_ZERO_MODE',n,root,delta,flush=True)
 report={'schema':'J0740_F100_DERIVED_F99_STATIC_TOV_GLOBAL_TURNING_AND_RADIAL_EIGENMODE_BIFURCATION','source_F99_SHA256':EOS_SHA,'derived_model_distinct_from_original_seven_EOS':True,'reference_eos':'F99_1981_NODE_DISTINCT_AFFINE_COLD_PHYSICALLY_DERIVED','nodes':1981,'all_EOS_native_segments_causal':True,'cs2_min':float(np.min(slopes)),'cs2_max':float(np.max(slopes)), 'EOS_max_tabulated_P_MeVfm3':maxp,'M_max_TOV_MSun':-best.fun,'Pc_at_Mmax_MeVfm3':Pc,'R_km_at_Mmax':sc['R'],'J0740_mass_reference_2p073_MSun_central_P_MeVfm3':PC_REFERENCE,'static_models':models,'radial_omega2_zero_mesh_checks':roots,'mesh_root_delta_max_pct':max(abs(x['relative_delta_pct']) for x in roots),'real_GR_TOV_stars_derived_EOS':True,'real_GR_radial_linear_axisymmetric_mode_nonrotating':True,'uniformly_rotating_axisymmetric_perturbation_eigenmodes':'NOT_RUN','real_rotating_fixed_J_sequence':'NOT_RUN_BY_THIS_SCRIPT','seven_original_EOS_all_MR_native_photon_evidence':'NOT_RUN','failure_guard':'Mode nodes and eigenvalue signs validated; no positive frequency assigned to unstable eigenvalues','source_method':'F95 native-source verified static GR radial Sturm-Liouville FE operator reused but EOS is F99 thermodynamically derived (not published APR original).'}
 output.parent.mkdir(parents=True,exist_ok=True)
 output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
 return report

if __name__=='__main__':
 a=argparse.ArgumentParser()
 a.add_argument('--eos',type=Path,required=True)
 a.add_argument('--solver-root',type=Path,default=Path(__file__).resolve().parents[1]/'f95')
 a.add_argument('--out',type=Path,required=True)
 args=a.parse_args();solve(args.eos,args.out,args.solver_root)

"""F43 static TOV diagnostic of F42 NEW candidate tables, not final EOS approval.

Independent spherical GR hydrostatic equilibrium numerical integration, RNS
200-row representation. Full rotating GR, Love, prior and Bayes remain open.
"""
from __future__ import annotations
import argparse,hashlib,io,json,math,zipfile
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.integrate import solve_ivp
from scipy.optimize import brentq, minimize_scalar

C=299792458.;G=6.67430e-11;MSUN=1.988409870698051e30
MSUN_GEO=G*MSUN/C**2
EXPECTED_F42_ZIP_SHA='c8d8cdc9804a702860ab1af65b60fa25dfac0f74fce9ec6347c4271ea3353115'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class TabEOS:
 """Independent RNS-tabulated piecewise-linear E(P) and EXACT cold first-law H.

 This construction avoids independently interpolating E(H),P(H) (which can
 manufacture superluminal c_s² even when tabular interval secants are causal).
 It is not identical to the F42 finer original-node continuum; a finite-200
 table resampling/stellar convergence study is still required.
 """
 def __init__(self,rows):
  x=np.asarray(rows,dtype=float)
  if x.ndim!=2 or x.shape[1]!=4 or not(80<=len(x)<=200) or not np.isfinite(x).all() or not np.all(x>0) or not np.all(np.diff(x,axis=0)>0):
   raise ValueError('Invalid F42 200-row RNS table')
  self.e=x[:,0]*1e3*G/C**2
  self.p=x[:,1]*.1*G/C**4
  self.source_h=x[:,2]/(C*100)**2
  self.alpha=.6
  self.slope=np.diff(self.e)/np.diff(self.p)
  self.cs2=1/self.slope
  if not(np.isfinite(self.cs2).all() and np.all(self.cs2>0) and np.max(self.cs2)<=.99*(1+5e-11)):
   raise ValueError('F42 converted table produced acausal or nonpositive sound-speed secant')
  self.h0=math.log1p(self.p[0]/self.e[0])/(1-self.alpha)
  increments=np.log1p((np.diff(self.e)+np.diff(self.p))/(self.e[:-1]+self.p[:-1]))/(self.slope+1)
  self.hknots=self.h0+np.r_[0.,np.cumsum(increments)]
  if not np.all(np.diff(self.hknots)>0):raise ValueError('Rebuilt first-law enthalpy nonmonotone')
  self.hmin=float(self.hknots[0]);self.hmax=float(self.hknots[-1])
  self.plow=float(self.p[0]);self.elow=float(self.e[0])
  self.max_abs_input_h_difference=float(np.max(np.abs(self.source_h-self.hknots)))
 def state(self,h):
  if not math.isfinite(h):raise ValueError('invalid enthalpy')
  if h<=0:return 0.,0.
  if h>self.hmax*(1+1e-12):raise ValueError('enthalpy exceeds numerical EOS table')
  if h<self.hmin:
   y=math.expm1((1-self.alpha)*h)
   frac=(y/(self.plow/self.elow))**(1/(1-self.alpha))
   p=self.plow*frac
   return float(p),float(self.elow*frac**self.alpha)
  h=min(h,self.hmax)
  i=int(np.clip(np.searchsorted(self.hknots,h,side='right')-1,0,len(self.p)-2))
  a=self.slope[i];dh=h-self.hknots[i]
  dp=(self.e[i]+self.p[i])*math.expm1((a+1)*dh)/(a+1)
  pp=self.p[i]+dp
  return float(pp),float(self.e[i]+a*dp)
 def central_h(self,ec):
  if not self.e[3]<ec<self.e[-2]:raise ValueError('central density outside EOS table')
  i=int(np.clip(np.searchsorted(self.e,ec,side='right')-1,0,len(self.e)-2))
  dp=(ec-self.e[i])/self.slope[i];a=self.slope[i]
  return float(self.hknots[i]+math.log1p((a+1)*dp/(self.e[i]+self.p[i]))/(a+1))
 def tov(self,central_rho_cgs,*,rtol=3e-7,method="RK45"):
  ec=central_rho_cgs*1e3*G/C**2
  hc=self.central_h(ec)
  pc,ec2=self.state(hc)
  if not abs(ec2/ec-1)<1e-8:raise ValueError('central EOS analytic inverse inconsistent')
  r0=1.
  h0=hc-2*math.pi*(ec2/3+pc)*r0*r0
  m0=4*math.pi/3*ec2*r0**3
  if not 0<h0<hc:raise ValueError('center expansion failed')
  def rhs(r,y):
   m,h=y
   if not (0<m<r/2):raise ValueError('TOV Schwarzschild horizon reached')
   p,e=self.state(h)
   return (4*math.pi*r*r*e,-(m+4*math.pi*r**3*p)/(r*(r-2*m)))
  def surface(r,y):return y[1]
  surface.direction=-1;surface.terminal=True
  sol=solve_ivp(rhs,(r0,40000.),(m0,h0),events=surface,method=method,rtol=rtol,atol=(2e-6,2e-11),max_step=150)
  if not sol.success or len(sol.t_events[0])!=1:
   raise ValueError('TOV surface integration failed: '+sol.message)
  R=float(sol.t_events[0][0]);M=float(sol.y_events[0][0][0]/MSUN_GEO)
  if not (5.0<R/1000<30 and .01<M<4):raise ValueError('TOV invalid mass/radius')
  return {'center_density_g_cm3':central_rho_cgs,'mass_msun':M,'radius_km':R/1000,'compactness':(M*MSUN_GEO)/R,
     'solver_rel_tol':rtol,'solver_method':method,'tov_spherical':'STATIC_ONLY_NOT_ROTATING'}

def run(zipfile_path,out):
 if sha(zipfile_path)!=EXPECTED_F42_ZIP_SHA:raise ValueError('F42_REAL_ARTIFACT_ZIP_SHA_MISMATCH')
 report={'schema':'J0740_F43_NEW_F42_CANDIDATE_STATIC_TOV_v1','source_F42_artifact_sha256':sha(zipfile_path),
   'status':'STATIC_TOV_FINITE_GRID_DIAGNOSTIC','seven_EOS_Bayes':'NOT_RUN',
   'rotating_GR_stability':'NOT_RUN','physical_model_acceptance':'NOT_ESTABLISHED','eos':{}}
 with zipfile.ZipFile(zipfile_path) as z:
  if z.testzip() is not None:raise ValueError('F42 ZIP CRC fail')
  source=json.loads(z.read('F42_candidate_build_report.json'))
  for name,s in sorted(source['results'].items()):
   label=s['new_model_label'];path=label+'.rns'
   raw=z.read(path)
   expected=s['new_rns_SHA256']
   if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('F42 RNS input SHA not matched '+name)
   rows=np.loadtxt(io.BytesIO(raw),skiprows=1)
   model=TabEOS(rows)
   maxrho=float(rows[-1,0])
   dmax=min(4.5e15,maxrho*.92)
   dmin=3.0e14
   densities=np.geomspace(dmin,dmax,26)
   stars=[];failures=[]
   for d in densities:
    try:stars.append(model.tov(float(d)))
    except Exception as ex:failures.append({'density':float(d),'reason':str(ex)})
   if len(stars)<15:raise ValueError('insufficient TOV stars for '+name)
   mass=np.asarray([v['mass_msun'] for v in stars]);peak=int(np.argmax(mass))
   info={'new_model_label':label,'source_rns_sha256':expected,'star_count':len(stars),
      'failed_models':failures,'stars':stars,'maximum_sampled_mass_msun':float(mass[peak]),
      'at_sampled_mass_max_central_density':stars[peak]['center_density_g_cm3'],
      'sampled_branch_mass_increasing_before_peak':bool(np.all(np.diff(mass[:peak+1])>0)),
      'candidate_supports_2p073_sampled_static':bool(mass[peak]>=2.073),
      'maximum_mass_interpretation':'finite density scan; independent peak refinement only when bracketed',
      'max_sampled_mass_grid_index':peak,
      'max_tabulated_causal_cs2':float(np.max(model.cs2)),
      'maximum_original_vs_reconstructed_h_abs':model.max_abs_input_h_difference,
      'max_mass_refinement':'NOT_ESTABLISHED',
      'first_stable_2p073_root':'NOT_RUN'}
   if peak not in (0,len(stars)-1):
    low=stars[peak-1]['center_density_g_cm3'];high=stars[peak+1]['center_density_g_cm3']
    try:
     opt=minimize_scalar(lambda u:-model.tov(float(u*1e15),rtol=1e-8,method='DOP853')['mass_msun'],
             bounds=(low/1e15,high/1e15),method='bounded',options={'xatol':1e-9,'maxiter':60})
     if opt.success and low/1e15<opt.x<high/1e15:
      best=model.tov(float(opt.x*1e15),rtol=1e-8,method='DOP853')
      info['max_mass_refinement']={'method':'bounded local max on 26-node density scan using DOP853',
            'peak_star':best,'convergence':'NUMERICAL_LOCAL_STATIC_TOV_ONLY'}
    except Exception as ex:info['max_mass_refinement_error']=str(ex)
   if mass[peak]>=2.073:
    bracket=next(((stars[i]['center_density_g_cm3'],stars[i+1]['center_density_g_cm3'])
      for i in range(peak) if mass[i]<2.073<=mass[i+1]),None)
    if bracket:
     try:
      target=2.073
      root=brentq(lambda u:model.tov(u*1e15,rtol=1e-8,method='DOP853')['mass_msun']-target,
                  bracket[0]/1e15,bracket[1]/1e15,xtol=1e-11)
      fine=model.tov(root*1e15,rtol=1e-8,method='DOP853')
      coarse=model.tov(root*1e15,rtol=3e-7,method='RK45')
      info['first_stable_2p073_root']={'fine':fine,'coarse':coarse,
         'coarse_minus_fine_radius_m':1000*(coarse['radius_km']-fine['radius_km']),
         'coarse_minus_fine_mass_msun':coarse['mass_msun']-fine['mass_msun'],
         'physical_admissibility':'NOT_ESTABLISHED','rotating_equatorial_radius':'NOT_RUN',
         'resampled_resolution_study':'SEPARATE_EXPERIMENT_PENDING'}
     except Exception as ex:info['first_stable_2p073_root_error']=str(ex)
   report['eos'][name]=info
 out.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 return report

def main():
 p=argparse.ArgumentParser();p.add_argument('--f42-artifact',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();r=run(a.f42_artifact,a.out)
 print(json.dumps({name:{'TOV_mmax_sampled':x['maximum_sampled_mass_msun'],'M2p073_static_scan':x['candidate_supports_2p073_sampled_static']} for name,x in r['eos'].items()}))
if __name__=='__main__':main()

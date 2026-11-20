#!/usr/bin/env python3
"""Re-solve TOV using exact source CompOSE APR unified EOS with source n_B, P, e.

The source is not APR4_EPP; source checks require real publisher SHA digest.
The TOV interpolation is a *declared numerical approximation*, not the publisher's own.
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, zipfile
import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

C=2.99792458e10;G=6.67430e-8;MSUN=1.98847e33
ONE_MEVFM3=1.602176634e33
SRC_MD5='ccc2fbef2b0f51df389ff8f7d9b00608'
SRC_SHA='8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12'

class EOS:
 def __init__(self,root):
  root=pathlib.Path(root)
  orig=root/'F87_verified_publisher_original.zip'
  raw=orig.read_bytes()
  assert hashlib.md5(raw).hexdigest()==SRC_MD5 and hashlib.sha256(raw).hexdigest()==SRC_SHA,'PUBLISHER_ORIGINAL_ZIP_HASH_MISMATCH'
  with zipfile.ZipFile(orig) as source_zip:
   assert source_zip.testzip() is None, 'PUBLISHER_SOURCE_ZIP_CRC_FAIL'
   for name in ('eos.nb','eos.thermo','eos.mr'):
    assert (root/name).read_bytes()==source_zip.read(name), 'PUBLISHER_ORIGINAL_EXTRACTED_MEMBER_MUTATED: '+name
  self.nb=np.loadtxt(root/'eos.nb',skiprows=2)
  self.tab=np.loadtxt(root/'eos.thermo',skiprows=1)
  assert len(self.nb)==len(self.tab)==1833
  mn=float((root/'eos.thermo').read_text().splitlines()[0].split()[0]);self.mn=mn
  assert np.array_equal(self.tab[:,1].astype(int),np.arange(1,1834))
  self.P=self.nb*self.tab[:,3]
  self.E=self.nb*mn*(1+self.tab[:,9])
  self.mu_calc=(self.E+self.P)/self.nb
  self.mu_source=mn*(1+self.tab[:,5])
  self.cs_source=self.tab[:,11]
  assert np.all(self.P>0)&np.all(self.E>0)
  assert np.all(np.diff(self.P)>0)&np.all(np.diff(self.E)>0)
  self.logeps=PchipInterpolator(np.log(self.P),np.log(self.E),extrapolate=False)
  self.logpc_at_n=PchipInterpolator(np.log(self.nb),np.log(self.P),extrapolate=False)
  self.logn_at_pc=PchipInterpolator(np.log(self.P),np.log(self.nb),extrapolate=False)
 def eps_at_P(self,p):
  return np.exp(self.logeps(np.log(np.clip(p,self.P[0],self.P[-1]))))
 def pc_at_n(self,n):
  return np.exp(self.logpc_at_n(np.log(n)))
 def star(self,pc,rtol=3e-8,max_step=.125):
  epsc=float(self.eps_at_P(pc))*ONE_MEVFM3
  r0=1e-5;M0=4*np.pi*(r0*1e5)**3*epsc/(3*C*C*MSUN)
  def rhs(r,y):
   M,p=y
   if r<=0 or M<0:return [0,0]
   p=max(float(p),self.P[0]);eps=float(self.eps_at_P(p))*ONE_MEVFM3;pres=p*ONE_MEVFM3
   rc=r*1e5;mg=M*MSUN
   cmp=1-2*G*mg/(rc*C*C)
   if cmp<=0:raise ValueError('TOV_METRIC_HORIZON')
   dmdr=4*np.pi*rc*rc*eps/C**2*1e5/MSUN
   dpdr= -G*(eps+pres)/C**2*(mg+4*np.pi*rc**3*pres/C**2)/(rc*rc*cmp)*1e5/ONE_MEVFM3
   return [dmdr,dpdr]
  def surface(r,y):return y[1]-self.P[0]
  surface.terminal=True;surface.direction=-1
  x=solve_ivp(rhs,(r0,45),(M0,float(pc)),method='DOP853',rtol=rtol,atol=[3e-9,4e-13],events=surface,max_step=max_step)
  if not x.success or x.t_events[0].size!=1:raise RuntimeError('TOV_NO_SURFACE '+x.message)
  return {'pc_MeVfm3':float(pc),'M_Msun':float(x.y_events[0][0,0]),'R_km':float(x.t_events[0][0]),'steps':int(x.t.size)}

def run(root,output):
 e=EOS(root); pub=np.loadtxt(pathlib.Path(root)/'eos.mr')
 candidates=np.geomspace(2.0,1650.,65)
 stars=[]
 for pc in candidates:
  if not(e.P[0]<pc<e.P[-1]):continue
  stars.append(e.star(pc))
 imax=max(range(len(stars)),key=lambda i:stars[i]['M_Msun'])
 def at_goal(pc):return e.star(pc)['M_Msun']-2.073
 lo=next((stars[i]['pc_MeVfm3'] for i in range(imax) if stars[i]['M_Msun']<2.073 and stars[i+1]['M_Msun']>2.073),None)
 if lo is None:raise RuntimeError('MASS_TARGET_NOT_BRACKETED_ON_LOW_DENSITY_BRANCH')
 hi=next(stars[i+1]['pc_MeVfm3'] for i in range(imax) if stars[i]['pc_MeVfm3']==lo)
 ref=e.star(brentq(at_goal,lo,hi,xtol=1e-10))
 # compare against published actual numerical star table (R, M, Lambda)
 ind=np.argmin(abs(pub[:,1]-ref['M_Msun']))
 closest={'M':float(pub[ind,1]),'R_km':float(pub[ind,0]),'abs_mass_diff':float(abs(pub[ind,1]-ref['M_Msun'])),'abs_radius_diff_m':float(abs(pub[ind,0]-ref['R_km'])*1000)}
 csbad=np.flatnonzero(e.cs_source>1.0)
 secant=np.diff(e.P)/np.diff(e.E)
 secbad=np.flatnonzero(secant>1)
 low=pub[:np.argmax(pub[:,1])+1]
 publisher_interp_R=float(np.interp(ref['M_Msun'],low[:,1],low[:,0]))
 star_tight=e.star(ref['pc_MeVfm3'],rtol=2e-10,max_step=.06)
 core_nb=float(np.exp(e.logn_at_pc(np.log(ref['pc_MeVfm3']))))
 report={'schema':'J0740-F87-original-CompOSE-unified-APR-real-TOV-source-v1','original_archive_sha256':SRC_SHA,'exact_native_n_b_points':len(e.nb),'energy_unit':'MeV/fm3','true_baryon_density':'fm-3','largest_firstlaw_mu_disagreement_MeV':float(np.max(abs(e.mu_calc-e.mu_source))),'max_native_source_cs2':float(e.cs_source.max()),'native_source_cs2_gt1_count':len(csbad),'first_source_superluminal_nb_fm3':float(e.nb[csbad[0]]) if len(csbad) else None,'secant_cs2_gt1_intervals':len(secbad),'first_secant_superluminal_nb_fm3':float(e.nb[secbad[0]]) if len(secbad) else None,'target_M2p073_static':ref,'target_star_central_nB_fm3':core_nb,'target_star_central_P_below_first_source_acausal_P':bool(ref['pc_MeVfm3']<e.P[csbad[0]]),'max_source_cs2_within_target_star_central_nb':float(np.max(e.cs_source[e.nb<=core_nb])),'publisher_M2p073_interpolated_R_km':publisher_interp_R,'radius_difference_from_publisher_at_exact_M_m':(ref['R_km']-publisher_interp_R)*1000,'tight_integration_crosscheck':star_tight,'tight_crosscheck_R_diff_m':(ref['R_km']-star_tight['R_km'])*1000,'publisher_closest_MR':closest,'publisher_mass_max':float(pub[:,1].max()),'publisher_R_at_Mmax':float(pub[np.argmax(pub[:,1]),0]),'actual_computed_sequence_coarse':stars,'status':'REAL_ORIGINAL_EOS_TOV_SOLVED_WITH_CAUSALITY_EXCEPTIONS_RECORDED','physical_caveat':'APR(APR) unified is distinct from APR4_EPP. Its native superluminal rows at high densities mean complete global causality cannot be certified; preserve original EOS unchanged. TOV used PCHIP log(E) vs log(P), a numerical interpolation not publisher method. Nonrotating TOV is not 346.536369 Hz C/RNS, not full star stability and not X-PSI.'}
  # independent numerical interpolation check
 pathlib.Path(output).parent.mkdir(parents=True,exist_ok=True)
 pathlib.Path(output).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
 return report

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('source_dir');a.add_argument('--out',required=True);args=a.parse_args();print(json.dumps(run(args.source_dir,args.out),indent=2))

"""Construct NEW candidate barotropes, never relabel raw JESTER EOS as repaired.

Rule: one-sided minimal causal energy envelope at fixed source pressures;
piecewise-linear e(p) ensures 0 < dp/de <= cap everywhere between knots.
Below original p_min, explicit gamma=5/3 cold-gas continuation to p=0.
First-law h and baryon density use analytic integrals and mu(0)=m_b*c^2.
These are mathematical candidates, not validated nuclear EOS, stable GR stars,
or posterior model evidence.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np

G=6.67430e-11
C=299792458.0
MB=1.66053906660e-27
NAMES=('APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2')
PINNED_COMMIT='e6768650ce992abfd1153a6833857572fe5cd230'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def causal_energy_envelope(p,e,*,cap=.99):
    p,e=np.asarray(p,float),np.asarray(e,float)
    if not(.5<=cap<1 and p.ndim==e.ndim==1 and len(p)>=4 and p.shape==e.shape
            and np.isfinite(p).all() and np.isfinite(e).all() and
            np.all(p>0) and np.all(e>0) and np.all(np.diff(p)>0)):
        raise ValueError('invalid source pressure/energy/cap')
    c=e.copy()
    for i in range(1,len(c)):
        c[i]=max(e[i],c[i-1]+(p[i]-p[i-1])/cap)
    de=np.diff(c)
    speed=np.diff(p)/de
    if not(np.isfinite(speed).all() and np.all(de>0) and np.all(speed>0)
           and np.all(speed<=cap*(1+3e-11))):
        raise ValueError('causal envelope failed')
    return c,speed

class Candidate:
    def __init__(self,p,e,*,cap=.99,alpha=.6):
        if not(0<alpha<1):raise ValueError('invalid low-pressure cold gas exponent')
        self.p=np.array(p,dtype=float);self.source_e=np.array(e,dtype=float)
        self.e,self.cs2=causal_energy_envelope(self.p,self.source_e,cap=cap)
        self.cap,self.alpha=cap,alpha
        self.slope=np.diff(self.e)/np.diff(self.p)
        self.h0=math.log1p(self.p[0]/self.e[0])/(1-alpha)
        h=[self.h0]
        for i,a in enumerate(self.slope):
            # Integral dh = dp/(epsilon+p) exactly on each linear segment.
            inc=math.log1p((self.e[i+1]-self.e[i]+self.p[i+1]-self.p[i])/
                          (self.e[i]+self.p[i]))/(a+1)
            if not inc>0:raise ValueError('nonpositive first-law enthalpy increment')
            h.append(h[-1]+inc)
        self.hknots=np.array(h)
        if not np.all(np.diff(self.hknots)>0):raise ValueError('enthalpy not strictly increasing')
    def values(self,pressures):
        vals=np.asarray(pressures,dtype=float)
        if not (np.isfinite(vals).all() and np.all(vals>0) and np.all(vals<=self.p[-1])):
            raise ValueError('query outside EOS support')
        pp=vals.reshape(-1);ee=np.empty(len(pp));hh=np.empty(len(pp));speed=np.empty(len(pp))
        below=pp<self.p[0]
        if np.any(below):
            e=self.e[0]*np.power(pp[below]/self.p[0],self.alpha)
            ee[below]=e
            hh[below]=np.log1p(pp[below]/e)/(1-self.alpha)
            speed[below]=pp[below]/(self.alpha*e)
        if np.any(~below):
            x=pp[~below];idx=np.clip(np.searchsorted(self.p,x,side='right')-1,0,len(self.p)-2)
            en=self.e[idx]+self.slope[idx]*(x-self.p[idx])
            ee[~below]=en
            hh[~below]=self.hknots[idx]+np.log1p((en-self.e[idx]+x-self.p[idx])/
                     (self.e[idx]+self.p[idx]))/(self.slope[idx]+1)
            speed[~below]=1/self.slope[idx]
        n=(ee+pp)*np.exp(-hh)*C*C/(G*MB)/1e6
        if not(np.isfinite(ee).all() and np.isfinite(hh).all() and np.isfinite(n).all()
               and np.all(ee>0) and np.all(hh>0) and np.all(n>0)
               and np.all(speed>0) and np.all(speed<=self.cap*(1+1e-9))):
            raise ValueError('EOS EOS thermodynamic or causal value invalid')
        return ee.reshape(vals.shape),hh.reshape(vals.shape),n.reshape(vals.shape),speed.reshape(vals.shape)
    def rns_table(self,*,points=200,surface_depth=12):
        if not(40<=points<=200 and 2<=surface_depth<=16):raise ValueError('invalid RNS resampling')
        pp=np.geomspace(self.p[0]*10.0**(-surface_depth),self.p[-1],points)
        ee,hh,nn,cs2=self.values(pp)
        table=np.column_stack([ee*C*C/G*1e-3,pp*C**4/G*10.0,hh*(C*100)**2,nn])
        if not(np.isfinite(table).all() and np.all(table>0) and
               all(np.all(np.diff(table[:,i])>0) for i in range(4))):
            raise ValueError('RNS tabulated thermo monotonicity failed')
        return table,{'sampled_min_cs2':float(cs2.min()),'sampled_max_cs2':float(cs2.max()),
            'max_source_energy_fractional_lift':float(np.max((self.e-self.source_e)/self.source_e)),
            'source_perturbed_nodes':int(np.count_nonzero(self.e>self.source_e)),
            'max_original_source_cs2_secant':float(np.max(np.divide(np.diff(self.p),np.diff(self.source_e),out=np.full(len(self.p)-1,float('nan')),where=np.diff(self.source_e)!=0))),
            'max_causal_candidate_cs2_secant':float(self.cs2.max()),
            'pseudoenthalpy_zero_surface':'P→0 analytical cold gas',
            'mu0_assumption':'rest baryon mass 1.66053906660e-27 kg',
            'physical_EOS_acceptance':'NOT_ESTABLISHED',
            'TOV_RNS_stability':'NOT_RUN'}

def build_one(path,out_dir,fixture,cap=.99):
    name=Path(path).stem
    if name not in NAMES:raise ValueError('unrecognized original EOS source')
    expected=fixture['eos'][name]['expected_source_sha256']
    digest=sha(path)
    if digest!=expected:raise ValueError('PINNED_SOURCE_SHA_MISMATCH:'+name)
    with np.load(path,allow_pickle=False) as data:
        p=data['p'];e=data['e']
    can=Candidate(p,e,cap=cap)
    rows,s=can.rns_table()
    label=name+'__CAUSAL_LIFT_FIRSTLAW_GAS_V1'
    output=out_dir/(label+'.rns')
    with output.open('w',encoding='ascii',newline='\n') as f:
        f.write(str(len(rows))+'\n');np.savetxt(f,rows,fmt='%.15e')
    s.update({'new_model_label':label,'source_EOS_name':name,'source_JESTER_commit':PINNED_COMMIT,
       'source_original_SHA256':digest,'new_rns_SHA256':sha(output), 'new_rns_bytes':output.stat().st_size,
       'source_eos_modified':True,'causality_limit_cs2':cap,
       'construction':'one-sided causal energy lift + analytic piecewise cold first-law + cold-gas surface',
       'scientific_warning':'This is a new mathematical candidate, not the original nuclear EOS model or a validated J0740 likelihood/evidence.'})
    return s

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--fixture',type=Path,required=True);p.add_argument('--cap',type=float,default=.99)
    args=p.parse_args();fixture=json.loads(args.fixture.read_text())
    if fixture['source_commit']!=PINNED_COMMIT or set(fixture['eos'])!=set(NAMES):raise ValueError('source pin/7-EOS mismatch')
    args.out.mkdir(parents=True,exist_ok=True)
    report={'schema':'J0740_F42_NEW_CANDIDATE_BAROTROPES_v1','status':'SOURCE_REBUILT_MATHEMATICAL_CANDIDATES_NOT_FULL_PHYSICAL_VALIDATION',
            'source_commit':PINNED_COMMIT,'candidate_label_is_original_EOS':False,'results':{},
            'TOV_RNS_and_EOS_Bayes':'NOT_RUN'}
    for name in NAMES:
        try:report['results'][name]=build_one(args.source_dir/(name+'.npz'),args.out,fixture,cap=args.cap)
        except Exception as ex:report['results'][name]={'status':'FAILED_NOT_VALIDATED','error_type':type(ex).__name__,'reason':str(ex)}
    (args.out/'F42_candidate_build_report.json').write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    if any('new_rns_SHA256' not in x for x in report['results'].values()):raise SystemExit('Some source candidates could not be generated; fail closed.')
    print(json.dumps({'status':report['status'],'candidate_count':len(report['results']),'source_original_modified':False}))
if __name__=='__main__':main()

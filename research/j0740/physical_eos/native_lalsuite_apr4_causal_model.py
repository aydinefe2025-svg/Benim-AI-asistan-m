from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import CubicSpline, PchipInterpolator
from scipy.optimize import brentq, minimize_scalar
from numpy.polynomial.legendre import leggauss

C=299792458.0; G=6.67430e-11; MSUN=1.988409870698051e30
NPZ_SHA='639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88'
LAL_TABLE_SHA='2a63cd7f1e1c5a158bb3cc06ab4b51f4344a9a1e6bfaeec7f98937c3d5a5447f'
LAL_SOURCE_SHA='1c84c672e663d853b1ef87f9bb23520e85ab007c2b4e66048d2abc82bc7825df'
LAL_WHEEL_SHA='d37698363f9ec74255514ecadc5d8aeb4aca7ad3f04cd50534ac0caffe55f4bf'

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

class NativeAPR4CausalEOS:
    """LALSuite native APR4 table interpolation, exact h integration, cs2=1 tail."""
    def __init__(self,table,max_pressure=None,quadrature_order=12,enthalpy_subdivisions=16):
        a=np.loadtxt(table); self.pdata=a[:,0];self.edata=a[:,1]
        if len(a)!=1447 or np.any(np.diff(self.pdata)<=0) or np.any(np.diff(self.edata)<=0):
            raise ValueError('Pinned native table shape or monotonicity mismatch')
        self.x=np.log(self.pdata);self.y=np.log(self.edata)
        self.e_spline=CubicSpline(self.x,self.y,bc_type='natural')
        self.p0=float(self.pdata[0]);self.e0=float(self.edata[0]);self.x0=float(self.x[0])
        self.h0=2.5*math.log1p(self.p0/self.e0)
        gx,gw=leggauss(quadrature_order)
        xx=[np.linspace(a,b,enthalpy_subdivisions+1)[:-1] for a,b in zip(self.x[:-1],self.x[1:])]
        self.hx=np.r_[np.concatenate(xx),self.x[-1]]; xa=self.hx[:-1];xb=self.hx[1:]
        xt=(xa+xb)[:,None]/2+(xb-xa)[:,None]*gx/2
        integ=np.exp(xt)/(np.exp(self.e_spline(xt))+np.exp(xt))
        dh=(xb-xa)/2*(integ@gw)
        self.hnodes=self.h0+np.r_[0.,np.cumsum(dh)]
        if np.any(np.diff(self.hnodes)<=0):raise ValueError('first-law enthalpy is not increasing')
        self.h_of_x=PchipInterpolator(self.hx,self.hnodes)
        self.x_of_h=PchipInterpolator(self.hnodes,self.hx)
        self.pcut=float(self.find_first_causal_crossing())
        self.ecut=float(self.energy_native(self.pcut));self.hcut=float(self.h(self.pcut))
        self.ptop=float(self.pdata[-1]*1.0 if max_pressure is None else max_pressure)
        if self.ptop<=self.pcut:self.ptop=12*self.pcut
    def energy_native(self,p):
        p=float(p)
        if p<=0:return 0.
        if p<self.p0:return self.e0*(p/self.p0)**.6
        if p>self.pdata[-1]:return self.edata[-1]+p-self.pdata[-1]
        return math.exp(float(self.e_spline(math.log(p))))
    def energy(self,p):
        p=float(p)
        if p<=self.pcut:return self.energy_native(p)
        return self.ecut+(p-self.pcut)
    def h_native(self,p):
        p=float(p)
        if p<=0:return 0.
        if p<self.p0:return self.h0*(p/self.p0)**.4
        if p>self.pdata[-1]:
            hmax=float(self.h_of_x(self.x[-1])); emax=float(self.edata[-1]);pmax=float(self.pdata[-1])
            return hmax+0.5*math.log((emax-pmax+2*p)/(emax+pmax))
        return float(self.h_of_x(math.log(p)))
    def h(self,p):
        p=float(p)
        if p<=self.pcut:return self.h_native(p)
        return self.hcut+0.5*math.log((self.ecut-self.pcut+2*p)/(self.ecut+self.pcut))
    def pressure(self,h):
        h=float(h)
        if h<=0:return 0.
        if h<self.h0:return self.p0*(h/self.h0)**2.5
        if h<=self.hcut:return math.exp(float(self.x_of_h(h)))
        return 0.5*((self.ecut+self.pcut)*math.exp(2*(h-self.hcut))-(self.ecut-self.pcut))
    def cs2_native(self,p):
        p=float(p)
        if p<self.p0:return (5/3)*p/self.energy_native(p)
        x=math.log(p); y=float(self.e_spline(x));g=float(self.e_spline(x,1))
        return math.exp(x-y)/g
    def cs2(self,p):return self.cs2_native(p) if float(p)<=self.pcut else 1.0
    def interval_extrema(self):
        out=[];ming=math.inf;maxg=-math.inf
        for i,h in enumerate(np.diff(self.x)):
            a,b,c,d=self.e_spline.c[:,i]
            D=np.array([c,2*b,3*a]);Dp=np.array([2*b,6*a])
            tpoints=[0.,float(h)]
            if Dp[1]!=0:
                root=-Dp[0]/Dp[1]
                if 0<root<h:tpoints.append(float(root))
            gs=[float(np.polynomial.polynomial.polyval(t,D)) for t in tpoints]
            ming=min(ming,min(gs));maxg=max(maxg,max(gs))
            sq=np.polynomial.polynomial.polymul(D,D)
            eq=-np.pad(sq,(0,max(0,5-len(sq))))
            eq[:3]+=D;eq[:2]-=[2*b,6*a]
            tr=np.trim_zeros(eq,'b'); candidates=[0.,float(h)]
            if len(tr)>1:
                candidates += [float(r.real) for r in np.polynomial.polynomial.polyroots(tr) if abs(r.imag)<1e-9 and 0<r.real<h]
            for t in candidates:
                x=float(self.x[i]+t);out.append((self.cs2_native(math.exp(x)),x))
        return out,ming,maxg
    def find_first_causal_crossing(self):
        # Check the low-pressure analytic continuation first.
        if (5/3)*self.p0/self.e0>=1: return self.p0
        lastx=self.x0
        cs_at_left=self.cs2_native(self.p0)
        for i in range(len(self.x)-1):
            a,b,c,d=self.e_spline.c[:,i];h=float(self.x[i+1]-self.x[i])
            D=np.array([c,2*b,3*a]);sq=np.polynomial.polynomial.polymul(D,D)
            eq=-np.pad(sq,(0,max(0,5-len(sq))));eq[:3]+=D;eq[:2]-=[2*b,6*a]
            tr=np.trim_zeros(eq,'b'); pts=[0.,h]
            if len(tr)>1:pts += [float(r.real) for r in np.polynomial.polynomial.polyroots(tr) if abs(r.imag)<1e-9 and 0<r.real<h]
            pts=sorted(set(pts));vals=[self.cs2_native(math.exp(self.x[i]+t)) for t in pts]
            if max(vals)>=1:
                for j in range(len(pts)-1):
                    if vals[j]<1<=vals[j+1]:
                        root=brentq(lambda x:self.cs2_native(math.exp(x))-1,self.x[i]+pts[j],self.x[i]+pts[j+1],xtol=2e-14)
                        return math.exp(root)
                # A local maximum can cross 1 and return below in one interval.
                k=int(np.argmax(vals))
                if vals[k]>=1 and k>0:
                    root=brentq(lambda x:self.cs2_native(math.exp(x))-1,self.x[i]+pts[k-1],self.x[i]+pts[k],xtol=2e-14)
                    return math.exp(root)
            lastx=self.x[i+1];cs_at_left=vals[-1]
        return float(self.pdata[-1])

def tov(eos,pc,rtol=2e-10,atol=1e-11):
    hc=eos.h(pc);ec=eos.energy(pc);dh=max(1e-12*hc,1e-14)
    hstart=hc-dh;r0=math.sqrt(3*dh/(2*math.pi*(ec+3*pc)));m0=4*math.pi*ec*r0**3/3
    def rhs(h,y):
        r,m=y;p=eos.pressure(h);e=eos.energy(p);den=m+4*math.pi*r**3*p;f=r*(r-2*m)/den
        return [-f,-4*math.pi*r**3*e*(r-2*m)/den]
    sol=solve_ivp(rhs,(hstart,0.),(r0,m0),method='DOP853',rtol=rtol,atol=atol,max_step=max(hc/100,1e-7))
    if not sol.success:raise RuntimeError(sol.message)
    r,m=sol.y[:,-1]
    return {'M_msun':m*C*C/G/MSUN,'R_km':r/1000,'pc_geom_m-2':pc,'hc':hc,'steps':len(sol.t)}

def reproduce_jester_export(table,npz):
    with np.load(npz,allow_pickle=False) as z:
        p=z['p'];e=z['e'];h=z['h'];d=z['dloge_dlogp'];n=z['n']
    a=np.loadtxt(table);x=np.log(a[:,0]);y=np.log(a[:,1]);s=CubicSpline(x,y,bc_type='natural');xp=np.log(p)
    ehat=np.exp(s(xp));dhat=s(xp,1)
    # Faithful to LALSuite 7.26.4 C source: h0=P/(e+P), then linear
    # interpolation/integration of P/(e+P) in log(P), then natural cubic log(h).
    w=a[:,0]/(a[:,0]+a[:,1]);h0=w[0];hn=h0+np.r_[0.,np.cumsum(np.diff(x)*(w[1:]+w[:-1])/2)]
    hhat=np.exp(CubicSpline(x,np.log(hn),bc_type='natural')(xp))
    mavg=float(e[0]/n[0]);nratio=(ehat+p)*np.exp(-hhat)/mavg/n
    return {'e_rel_max':float(np.max(np.abs(ehat/e-1)),),'dloge_abs_max':float(np.max(np.abs(dhat-d))),
            'native_h_rel_max':float(np.max(np.abs(hhat/h-1))),
            'jester_n_proxy_to_native_firstlaw_ratio_first':float(nratio[0]),
            'jester_n_proxy_to_native_firstlaw_ratio_last':float(nratio[-1]),
            'jester_n_proxy_to_native_firstlaw_ratio_min':float(nratio.min()),
            'jester_n_proxy_to_native_firstlaw_ratio_max':float(nratio.max()),'m_avg_geom_m':mavg}

def run(table,npz,outdir,grid_sizes):
    if sha256(npz)!=NPZ_SHA:raise ValueError('JESTER NPZ SHA mismatch')
    if sha256(table)!=LAL_TABLE_SHA:raise ValueError('native LAL table SHA mismatch')
    eos=NativeAPR4CausalEOS(table)
    ext,ming,maxg=eos.interval_extrema()
    maxcs=max(v for v,_ in ext);mincs=min(v for v,_ in ext)
    if ming<=0:raise AssertionError('native EOS has continuous thermodynamic instability')
    pcut=eos.pcut
    # Physical surface continuation plus native crust: h0 must satisfy exact first-law integral for Gamma=5/3.
    source=reproduce_jester_export(table,npz)
    if source['e_rel_max']>1e-11 or source['dloge_abs_max']>1e-10 or source['native_h_rel_max']>1e-10:
        raise AssertionError(f'JESTER export does not reproduce from pinned LAL table/source: {source}')
    if maxcs<=1 or eos.cs2_native(pcut)<1-5e-10 or ming<=0:
        raise AssertionError('native continuous causality/stability gate did not identify a valid first causal cutoff')
    mavg=source['m_avg_geom_m'];max_firstlaw_residual=0.0
    for i in range(int(np.searchsorted(eos.pdata,pcut))-1):
        x1,x2=float(eos.x[i]),float(eos.x[i+1]);x=(x1+x2)/2
        eps=min(1e-5,(x2-x1)*0.1);q=math.exp(x)
        def ln_n(xx):
            pp=math.exp(xx);ee=eos.energy(pp)
            return math.log((ee+pp)*math.exp(-eos.h(pp))/mavg)
        fd=(ln_n(x+eps)-ln_n(x-eps))/(2*eps)
        gamma=float(eos.e_spline(x,1));exact=gamma*eos.energy(q)/(eos.energy(q)+q)
        max_firstlaw_residual=max(max_firstlaw_residual,abs(fd-exact))
    if max_firstlaw_residual>5e-6:raise AssertionError(f'continuous first-law density-shape test failed: {max_firstlaw_residual}')
    outdir.mkdir(parents=True,exist_ok=True)
    summary=[]
    for N in grid_sizes:
        pcs=np.geomspace(pcut*.03,pcut*12,N);seq=[tov(eos,float(q)) for q in pcs];m=np.array([r['M_msun'] for r in seq]);i=int(np.argmax(m))
        z=minimize_scalar(lambda lp:-tov(eos,math.exp(lp))['M_msun'],bounds=(math.log(pcs[i-1]),math.log(pcs[i+1])),method='bounded',options={'xatol':2e-12})
        peak=tov(eos,math.exp(z.x));summary.append({'central_pressure_grid':N,'turning_point':peak,'sampled_peak_index':i,'sequence':seq})
    fine=summary[-1]['turning_point'];mid=summary[-2]['turning_point']
    nsample=np.geomspace(float(eos.pdata[0])*1e-10,pcut,4000)
    nvals=np.array([(eos.energy(q)+q)*math.exp(-eos.h(q))/mavg for q in nsample])
    if not np.all(np.isfinite(nvals)) or not np.all(nvals>0):raise AssertionError('native first-law baryon density invalid')
    report={
      'status':'NATIVE_LAL_TABLE_REPRODUCED; CAUSAL_COMPLETION_TOV_CONDITIONAL; ABSOLUTE_PHYSICAL_MU0_NOT_ESTABLISHED',
      'model_name':'APR4_EPP_LALSuite_7.26.4_native_crust_firstlaw_h_causal_limit_completion',
      'provenance':{'jester_commit':'e6768650ce992abfd1153a6833857572fe5cd230','jester_npz_sha256':NPZ_SHA,
        'jester_npz_git_blob':'970790a9fd2aeb1f2fccd3ebfdccf206fcd80f89','lalsuite_tag':'lalsuite-v7.26.4',
        'lalsuite_wheel_sha256':LAL_WHEEL_SHA,'native_table_sha256':LAL_TABLE_SHA,'native_table_nodes':len(eos.pdata),
        'native_table_gitlab_blob':'a8e340236646f81099f76b5de8c1bf3daa0e1f56','tabular_source_sha256':LAL_SOURCE_SHA,
        'tabular_source_gitlab_blob':'4bb3a04819a959fdf0cec9fb74981283b4afed65'},
      'jester_export_reproduction':source,
      'continuous_native_stability':{'min_dloge_dlogp':float(ming),'max_dloge_dlogp':float(maxg),'all_positive':bool(ming>0)},
      'continuous_native_causality':{'min_cs2':float(mincs),'max_cs2':float(maxcs),'first_causal_cut_p_geom_m-2':pcut,'cut_cs2':eos.cs2_native(pcut),'globally_causal_original_native_table':bool(maxcs<=1)},
      'physical_crust':'Native LALSuite APR4_EPP table includes 1447 nodes down to P=1.94e-31 m^-2; analytic Gamma=5/3 continuation below its first node.',
      'baryon_density':'n=(e+P) exp(-h)/m_avg, with m_avg inferred exactly from JESTER generator convention; true physical zero-pressure chemical potential mu0 is not separately present in the two-column EOS table, so absolute physical normalization is NOT_ESTABLISHED.',
      'first_law_h':'For the new EOS, h(0)=0 and h(Pmin)=2.5 ln(1+Pmin/e_min), then dh/dlnP=P/(e+P) integrated over the native natural-cubic E(P) spline. This corrects the finite lower-end h0 convention used by the source LAL table loader.',
      'continuous_firstlaw_n_shape_max_abs_derivative_residual':max_firstlaw_residual,
      'causal_completion':'Above the first continuous cs2=1 crossing, epsilon(P)=epsilon_cut+(P-P_cut); analytic h integrated to preserve the first law. Original APR4 table is unmodified.',
      'tov_convergence':summary,
      'turning_point_grid_delta_M_msun':abs(float(fine['M_msun'])-float(mid['M_msun'])),'turning_point_grid_delta_R_km':abs(float(fine['R_km'])-float(mid['R_km'])),
      'physical_M_TOV':'NOT_ESTABLISHED because mu0 normalization and EOS family treatment for the inference remain open; reported turning point is conditional for this explicitly new completion.'}
    (outdir/'APR4_native_LAL_causal_completion_TOV.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    import csv
    with open(outdir/'APR4_native_LAL_causal_completion_TOV_sequence.csv','w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['resolution','pc_geom_m-2','M_msun','R_km','steps'])
        for s in summary:
            for row in s['sequence']:w.writerow([s['central_pressure_grid'],row['pc_geom_m-2'],row['M_msun'],row['R_km'],row['steps']])
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--table',type=Path,required=True);ap.add_argument('--npz',type=Path,required=True);ap.add_argument('--outdir',type=Path,required=True);ap.add_argument('--grid-sizes',type=int,nargs='+',default=[41,81,161])
    a=ap.parse_args();r=run(a.table,a.npz,a.outdir,a.grid_sizes)
    print('cs2',r['continuous_native_causality']['min_cs2'],r['continuous_native_causality']['max_cs2'],'cut',r['continuous_native_causality']['first_causal_cut_p_geom_m-2'])
    for s in r['tov_convergence']:print(s['central_pressure_grid'],s['turning_point']['M_msun'],s['turning_point']['R_km'],s['turning_point']['pc_geom_m-2'])


"""J0740 APR4 *trial* EOS: C1 low-P polytropic continuation plus first-law h(P), n(P).

Pinned source immutable. The low-pressure continuation is an explicit model
assumption, NOT the native LALSuite crust or a uniquely physical solution.
No scientific claims about a corrected EOS or GR star follow from this table.
Requires NumPy only; source JESTER is verified by SHA256.
"""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np

G=6.67430e-11
C=299792458.0
SHA_APR4='639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88'
RHO_CENTER_GCM3=1.7497312585302398e15


def checksum(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def end_slope(h0,h1,d0,d1):
    v=((2*h0+h1)*d0-h0*d1)/(h0+h1)
    if np.sign(v)!=np.sign(d0): return 0.
    if np.sign(d0)!=np.sign(d1) and abs(v)>3*abs(d0):return 3*d0
    return v


def pchip_slopes(x,y):
    h=np.diff(x);d=np.diff(y)/h
    if np.any(h<=0) or np.any(d<=0):
        raise ValueError('nonmonotonic source energy or pressure: fail closed')
    m=np.empty_like(x)
    m[0]=end_slope(h[0],h[1],d[0],d[1])
    m[-1]=end_slope(h[-1],h[-2],d[-1],d[-2])
    w1=2*h[1:]+h[:-1];w2=h[1:]+2*h[:-1]
    m[1:-1]=(w1+w2)/(w1/d[:-1]+w2/d[1:])
    return m


class FirstLawCrust:
    def __init__(self,p,e,n,source_h,center_e,*,nquad=32):
        self.p,self.e,self.n,self.source_h=(np.asarray(a,float) for a in (p,e,n,source_h))
        if not all(a.ndim==1 and a.shape==self.p.shape and np.isfinite(a).all() for a in (self.p,self.e,self.n,self.source_h)) or len(self.p)<10:
            raise ValueError('source shape/nonfinite')
        if np.any(self.p<=0) or np.any(self.e<=0) or np.any(self.n<=0) or np.any(np.diff(self.p)<=0) or np.any(np.diff(self.e)<=0) or np.any(np.diff(self.source_h)<=0):
            raise ValueError('source nonmonotonic or nonpositive: reject')
        self.x=np.log(self.p);self.y=np.log(self.e);self.m=pchip_slopes(self.x,self.y)
        self.beta=float(self.m[0]);self.p0=float(self.p[0]);self.e0=float(self.e[0]);self.center_e=float(center_e)
        if not (0<self.beta<1 and self.p0<self.p[-1] and self.e0<self.center_e<self.e[-1]):
            raise ValueError('no admissible C1 low-P continuation or centre range')
        self.mu_geom=float(np.median(self.e/self.n))
        if np.max(np.abs(self.e/self.n/self.mu_geom-1))>2e-10:
            raise ValueError('original n is not ε/m_avg; source unexpectedly changed')
        self.h0=math.log1p(self.p0/self.e0)/(1-self.beta)
        self.qx,self.qw=np.polynomial.legendre.leggauss(nquad)
        self.prefix=np.zeros(len(self.x))
        for i in range(len(self.x)-1):
            self.prefix[i+1]=self.prefix[i]+self.integrate_log(self.x[i],self.x[i+1],i)

    def interval(self,idx):
        h=float(self.x[idx+1]-self.x[idx]);y0=float(self.y[idx]);y1=float(self.y[idx+1]);m0=float(self.m[idx]);m1=float(self.m[idx+1])
        return h,np.array([2*y0-2*y1+h*(m0+m1),-3*y0+3*y1-h*(2*m0+m1),h*m0,y0],float)

    def y_s(self,x):
        if x<self.x[0]:
            return self.y[0]+self.beta*(x-self.x[0]),self.beta
        if x>self.x[-1]+1e-12: raise ValueError('extrapolation above source forbidden')
        k=min(len(self.x)-2,max(0,int(np.searchsorted(self.x,x,side='right')-1)))
        h,c=self.interval(k);t=(x-float(self.x[k]))/h
        A,B,C,D=c
        return ((A*t+B)*t+C)*t+D,(3*A*t*t+2*B*t+C)/h

    def integrate_log(self,a,b,idx=None):
        if not b>a:return 0.
        xx=(a+b)*.5 + (b-a)*.5*self.qx
        ys=[]
        if idx is None:
            for x in xx:ys.append(self.y_s(float(x))[0])
        else:
            hh,c=self.interval(idx);t=(xx-self.x[idx])/hh
            A,B,C,D=c;ys=((A*t+B)*t+C)*t+D
        ratios=np.exp(xx-np.array(ys))
        integrand=ratios/(1+ratios)
        return float((b-a)*.5*np.dot(self.qw,integrand))

    def at_p(self,p):
        p=float(p)
        if p<=0 or p>self.p[-1]*(1+2e-13):raise ValueError('out of admissible positive range')
        x=math.log(p);y,s=self.y_s(x);e=math.exp(y)
        if p<=self.p0:
            h=math.log1p(p/e)/(1-self.beta)
        else:
            k=min(len(self.x)-2,int(np.searchsorted(self.x,x,side='right')-1))
            h=self.h0+float(self.prefix[k])+self.integrate_log(float(self.x[k]),x,k)
        n=(e+p)*math.exp(-h)/self.mu_geom
        cs2=p/(e*s)
        return {'p':p,'e':e,'h':h,'n':n,'source_approx_n':e/self.mu_geom,'s':s,'cs2':cs2}

    def at_e(self,e):
        e=float(e)
        if not 0<e<=self.e[-1]:raise ValueError('invalid energy')
        lo,hi=math.log(self.p0)-50.,float(self.x[-1])
        for _ in range(95):
            xm=(lo+hi)/2
            if self.y_s(xm)[0]<math.log(e):lo=xm
            else:hi=xm
        return self.at_p(math.exp((lo+hi)/2))

    def causal_screen(self,pmax):
        # Upper bounds for the particular candidate interpolant (not native LAL EOS).
        end=math.log(pmax)
        values=[]
        for k in range(len(self.x)-1):
            x0=float(self.x[k]);xend=min(float(self.x[k+1]),end)
            if xend<=x0:break
            hh,c=self.interval(k);zmax=(xend-x0)/hh
            A,B,C,D=c
            s=lambda z:(3*A*z*z+2*B*z+C)/hh
            possible=[0.,zmax]
            if abs(A)>1e-20:
                z=-B/(3*A)
                if 0<z<zmax:possible.append(z)
            if min(s(z) for z in possible)<=0:raise ValueError('nonpositive candidate derivative')
            sp=np.array([C,2*B,3*A])/hh
            sd=np.array([2*B,6*A])/(hh*hh)
            q=np.polynomial.polynomial.polysub(sp,np.polynomial.polynomial.polymul(sp,sp))
            q=np.polynomial.polynomial.polysub(q,sd)
            while len(q)>1 and abs(q[-1])<1e-14*max(1.,float(np.max(np.abs(q)))):q=q[:-1]
            if len(q)>1:
                for rt in np.polynomial.polynomial.polyroots(q):
                    if abs(rt.imag)<1e-8 and 0<float(rt.real)<zmax:possible.append(float(rt.real))
            cs=[]
            for z in possible:
                yv=((A*z+B)*z+C)*z+D
                cs.append(math.exp(x0+hh*z-yv)/s(z))
            values.append((min(cs),max(cs)))
        upper=max(q[1] for q in values)
        lower=min(q[0] for q in values)
        if not (0<lower<=upper<=1.):raise ValueError(f'candidate is acausal in tested range: {lower}..{upper}')
        return {'n_intervals':len(values),'max_cs2':upper,'min_cs2':lower,'matched_low_pressure_cs2':self.p0/(self.beta*self.e0)}

    def make_table(self,pmax,points=196,floor_ratio=1.e-12):
        if not (30<=points<=200 and 1e-15<=floor_ratio<=1e-6 and self.p0<pmax<=self.p[-1]):
            raise ValueError('invalid RNS grid/floor')
        pgrid=np.geomspace(self.p0*floor_ratio,pmax,points)
        states=[self.at_p(p) for p in pgrid]
        e=np.array([v['e'] for v in states]);p=np.array([v['p'] for v in states]);h=np.array([v['h'] for v in states]);n=np.array([v['n'] for v in states]);na=np.array([v['source_approx_n'] for v in states]);cs=np.array([v['cs2'] for v in states]);
        if not all(np.all(np.diff(v)>0) for v in (e,p,h,n,na)) or not np.all((cs>0)&(cs<=1)):
            raise ValueError('RNS table monotonicity/causality screen failure')
        basic=[e*C*C/G*1e-3,p*C**4/G*10.,h*(C*100.)**2]
        rows_new=np.column_stack([*basic,n/1.e6])
        rows_naive=np.column_stack([*basic,na/1.e6])
        if not np.array_equal(rows_new[:,:3],rows_naive[:,:3]):raise AssertionError('not a pure n-column ablation')
        return rows_new,rows_naive,states


def from_pinned(path):
    path=Path(path)
    if checksum(path)!=SHA_APR4:raise ValueError('APR4 pinned NPZ SHA mismatch')
    with np.load(path,allow_pickle=False) as d:
        ee,pp,nn,hh=[np.asarray(d[k],dtype=float) for k in ('e','p','n','h')]
    center=RHO_CENTER_GCM3*1000*G/(C*C)
    return FirstLawCrust(pp,ee,nn,hh,center)


def write_rns(path,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='ascii',newline='\n') as f:
        f.write(str(len(rows))+'\n');np.savetxt(f,rows,fmt='%.15e')

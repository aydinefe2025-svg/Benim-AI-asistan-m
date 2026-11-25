"""Single-diode IV model fitting and within-curve held-out validation. SI units."""
import numpy as np
from scipy.optimize import least_squares, brentq
from scipy.interpolate import PchipInterpolator

def current(v, params):
    # Positive parameters: Iph, Is, Rs, Rsh, a. Implicit equation monotone in I.
    iph,isat,rs,rsh,a=map(float,params)
    if not all(np.isfinite([iph,isat,rs,rsh,a])) or min(iph,isat,rs,rsh,a)<=0:
        raise ValueError('nonpositive or nonfinite parameters')
    def solve(v):
        def f(i):
            u=v+i*rs
            return iph-isat*np.expm1(np.clip(u/a,-700,700))-u/rsh-i
        lo,hi=-max(iph,1.),max(iph,1.)*2
        for _ in range(60):
            if f(lo)>=0 and f(hi)<=0:break
            if f(lo)<0:lo*=2
            if f(hi)>0:hi*=2
        else:raise ValueError('root not bracketed')
        return brentq(f,lo,hi,xtol=1e-12)
    return np.asarray([solve(float(x)) for x in np.atleast_1d(v)])

def validate(v,i):
    v,i=np.asarray(v,float),np.asarray(i,float)
    if v.ndim!=1 or i.shape!=v.shape or len(v)<8 or not np.all(np.isfinite(v)) or not np.all(np.isfinite(i)) or np.any(np.diff(v)<=0):raise ValueError('need >=8 finite strictly increasing voltage samples')
    if max(i)<=0 or max(v)<=0:raise ValueError('no positive power region')
    return v,i

def fit(v,i):
    v,i=validate(v,i);vs=max(abs(v));cs=max(abs(i));vn=v/vs;inn=i/cs
    # normalize to device scale; broad positive bounds, not calibrated priors
    lo=np.log([.1,1e-15,1e-7,.01,.005]);hi=np.log([5,1e-1,2,1e7,1.])
    def residual(p):return current(vn,np.exp(p))-inn
    fits=[]
    for sat,a in [(1e-8,.06),(1e-6,.08),(1e-4,.12)]:
        x=np.log([1.01,sat,.03,100,a]);r=least_squares(residual,x,bounds=(lo,hi),max_nfev=400,xtol=1e-9,ftol=1e-9,gtol=1e-9)
        if r.success:fits.append(r)
    if not fits:raise RuntimeError('fit failed')
    r=min(fits,key=lambda x:np.sum(x.fun**2));p=np.exp(r.x)*np.array([cs,cs,vs/cs,vs/cs,vs]);return p

def metrics(i,pred,scale):
    d=np.asarray(pred)-np.asarray(i);return dict(n=len(d),mae_A=float(np.mean(abs(d))),rmse_A=float(np.sqrt(np.mean(d*d))),max_abs_A=float(np.max(abs(d))),normalized_rmse_pct=float(100*np.sqrt(np.mean(d*d))/scale))

def split(v,i):
    # Endpoints always training: tests are interpolation, not extrapolation.
    v,i=validate(v,i);train=np.arange(len(v))%2==0;train[-1]=True
    return train,~train

def evaluate(v,i,tr):
    v,i=validate(v,i);tr=np.asarray(tr,bool)
    if tr.shape!=v.shape or tr.sum()<8 or tr.sum()==len(v) or not tr[0] or not tr[-1]:raise ValueError('need >=8 training points, both endpoints and held-out samples')
    te=~tr;p=fit(v[tr],i[tr]);pred=current(v,p);base=np.interp(v,v[tr],i[tr]);cubic=PchipInterpolator(v[tr],i[tr])(v);scale=max(abs(i[tr]))
    return dict(parameters=dict(zip(['Iph_A','Is_A','Rs_ohm','Rsh_ohm','a_V'],map(float,p))),train_n=int(tr.sum()),test_n=int(te.sum()),model=metrics(i[te],pred[te],scale),linear=metrics(i[te],base[te],scale),pchip=metrics(i[te],cubic[te],scale),points=[dict(V=float(x),I_A=float(y),split='train' if t else 'test',pred_A=float(z),linear_A=float(l),pchip_A=float(c)) for x,y,t,z,l,c in zip(v,i,tr,pred,base,cubic)])
def audit(v,i):
    v,i=validate(v,i);tr,_=split(v,i);return evaluate(v,i,tr)
def sparse_audit(v,i,k):
    v,i=validate(v,i)
    if not isinstance(k,int) or not 8<=k<len(v):raise ValueError('training count outside [8,n-1]')
    tr=np.zeros(len(v),bool);tr[np.rint(np.linspace(0,len(v)-1,k)).astype(int)]=True
    return evaluate(v,i,tr)

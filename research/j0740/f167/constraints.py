"""Independent 3+1 stationary-data constraints; not a time evolution."""
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
import sys,json
def constraints(s,u,re,al,ga,ro,om,e,p,v2,Omega):
    r=re*s/(1-s); r=r[:,None]; U=u[None,:]
    sin=np.sqrt(np.maximum(0,1-U*U))
    A=np.exp(2*al); N=np.exp((ga+ro)/2); psi=np.exp((ga-ro)/2)*r*sin
    jac=A*r*r*np.exp((ga-ro)/2)
    aa=((1-s)**2/re)[:,None]; bb=(-2*(1-s)**3/re**2)[:,None]
    def ds(f):return np.gradient(f,s,axis=0,edge_order=2)
    def du(f):return np.gradient(f,u,axis=1,edge_order=2)
    def dr(f):return aa*ds(f)
    def lap(f):return aa**2*ds(ds(f))+bb*ds(f)+dr(f)/r+((1-U*U)*du(du(f))-U*du(f))/r**2
    with np.errstate(divide='ignore',invalid='ignore',over='ignore'):
        R=-2/A*(lap(al)+lap(psi)/psi)
        kr=-psi**2/(2*N*A)*dr(om)
        ku=-psi**2*(1-U*U)/(2*N*A*r*r)*du(om)
        K2=psi**2/(2*N*N*A)*(dr(om)**2+(1-U*U)*du(om)**2/r**2)
        # Regularization solely at coordinate singular r=0; excluded below.
        kr[0,:]=ku[0,:]=0.
        div=(dr(jac*kr)+du(jac*ku))/jac
        valid=e>0
        W2=np.ones_like(e); W2[valid]=1/(1-v2[valid])
        E=(e+p)*W2-p
        v=np.zeros_like(e);v[valid]=(Omega-om[valid])*np.broadcast_to(r*sin,e.shape)[valid]*np.exp(-ro[valid])
        S=(e+p)*W2*v*psi
        H=R-K2-16*np.pi*E
        M=div-8*np.pi*S
    return H,M,v,psi
def manufactured(n):
    s=np.linspace(0,.9999,2*n-1);u=np.linspace(0,1,n);re=1.
    z=np.zeros((len(s),len(u)))
    h,m,*_=constraints(s,u,re,z,z,z,z,z,z,z,0.)
    mask=(s[:,None]>.15)&(s[:,None]<.45)&(u[None,:]>.05)&(u[None,:]<.8)
    return float(np.sqrt(np.mean(h[mask]**2))),float(np.max(np.abs(m[mask])))
def main():
    d=Path(sys.argv[1]);f=d/'fields.txt'
    hdr=np.fromstring(f.open().readline()[2:],sep=' ')
    ns,nu=map(int,hdr[:2]);re,Omega,e_surface,M,Mb,R=hdr[2:]
    raw=np.loadtxt(f).reshape(ns,nu,10)
    assert np.isfinite(raw).all()
    s,u=raw[:,0,0],raw[0,:,1]
    assert np.all(np.diff(s)>0) and np.all(np.diff(u)>0)
    assert np.all(raw[:,:,0]==s[:,None]) and np.all(raw[:,:,1]==u[None,:])
    al,ga,ro,om,e,p,h,v2=np.moveaxis(raw[:,:,2:],2,0)
    matter=e>e_surface
    assert np.all((v2[matter]>=0)&(v2[matter]<1))
    C=2.99792458e10;G=6.673e-8;MSUN=1.989e33;KAPPA=1.e-15*C*C/G
    # Exact cold first-law rest density, native units.
    rest=np.where(matter,(e+p)*np.exp(-h),0)
    W=np.ones_like(e);W[matter]=1/np.sqrt(1-v2[matter])
    volume=np.exp(2*al+(ga-ro)/2)
    shape=(s*s/(1-s)**4)[:,None]
    bmass=4*np.pi*np.sqrt(KAPPA)*C*C/G/MSUN*re**3*simpson(simpson(shape*volume*rest*W,x=u,axis=1),x=s)
    assert abs(bmass/Mb-1)<1e-5,(bmass,Mb)
    first=h+(ga+ro)/2-np.log(W)
    core=matter & (e>.05*e[0,0]) & (s[:,None]>.05)&(s[:,None]<.45)&(u[None,:]<.85)
    assert core.sum()>100
    first_range=float(np.ptp(first[core]))
    H,Mom,v,psi=constraints(s,u,re,al,ga,ro,om,e,p,v2,Omega)
    vel_error=float(np.max(np.abs(v[core]**2-v2[core])))
    assert vel_error<1e-5 and first_range<1e-4
    assert np.isfinite(H[core]).all() and np.isfinite(Mom[core]).all()
    a,b=manufactured(61),manufactured(121)
    assert b[0]<a[0]*.35 and a[1]==b[1]==0.,(a,b)
    norm=16*np.pi*e[0,0]
    result=dict(grid=[ns,nu],r_e=re,Omega_dimensionless=Omega,central_e=e[0,0],baryon_mass_integrated=bmass,baryon_mass_reference=Mb,bernoulli_range=first_range,velocity_squared_error=vel_error,core_points=int(core.sum()),hamiltonian_core_rms_normalized=float(np.sqrt(np.mean(H[core]**2))/norm),momentum_phi_core_rms_normalized=float(np.sqrt(np.mean(Mom[core]**2))/(norm*re)),flat_test=[a,b],limits='Stationary axisymmetric core constraints only; coordinate-axis, surface and exterior excluded; not a dynamical stability test.')
    (d/'constraints.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print('F167_INITIAL_DATA',json.dumps(result),flush=True)
if __name__=='__main__': main()

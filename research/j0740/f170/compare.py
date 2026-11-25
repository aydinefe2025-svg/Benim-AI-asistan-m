import sys,json,io,zipfile,hashlib
from pathlib import Path
import numpy as np
from scipy.interpolate import RectBivariateSpline
def assess(raw):
 h=np.fromstring(raw.splitlines()[0].decode()[2:],sep=' ');ns,nu=map(int,h[:2]);re,Omega=h[2:4]
 d=np.loadtxt(io.BytesIO(raw)).reshape(ns,nu,10);assert np.isfinite(d).all()
 s,u=d[:,0,0],d[0,:,1];a,g,rho,om,e,p,ent,v2=np.moveaxis(d[:,:,2:],2,0)
 x=np.linspace(.09,.35,131);y=np.linspace(.08,.78,111);S,U=np.meshgrid(x,y,indexing='ij');r=re*S/(1-S);sin2=1-U**2
 ds=(1-S)**2/re;d2s=-2*(1-S)**3/re**2
 def der(f):
  q=RectBivariateSpline(s,u,f,kx=5,ky=5,s=0)
  return q(x,y),ds*q(x,y,dx=1),ds**2*q(x,y,dx=2)+d2s*q(x,y,dx=1),q(x,y,dy=1),q(x,y,dy=2)
 av,ar,arr,au,auu=der(a);b,br,brr,bu,buu=der((g-rho)/2);n,nr,nrr,nu,nuu=der((g+rho)/2);w,wr,wrr,wu,wuu=der(om)
 A=np.exp(2*av);N=np.exp(n);psi2=np.exp(2*b)*r*r*sin2
 R=-2/A*(arr+brr+(ar+3*br)/r+(sin2*(auu+buu)-U*(au+3*bu))/r**2+br**2+sin2*bu**2/r**2)
 K2=psi2/(2*N*N*A)*(wr**2+sin2*wu**2/r**2)
 div=-psi2/(2*N*A)*(wrr+(4/r+3*br-nr)*wr+(sin2*(wuu+(3*bu-nu)*wu)-4*U*wu)/r**2)
 ee,pp,vv=[der(f)[0] for f in (e,p,v2)];assert (ee>.05*e[0,0]).all()
 E=(ee+pp)/(1-vv)-pp;vel=(Omega-w)*r*np.sqrt(sin2)*np.exp(b-n);Sm=(ee+pp)/(1-vv)*vel*np.sqrt(psi2)
 norm=16*np.pi*e[0,0];par={}
 for name,f in [('alpha',a),('gamma',g),('rho',rho),('omega',om)]:
  ev=RectBivariateSpline(s[::2],u,f[::2],kx=5,ky=5)(x,y);od=RectBivariateSpline(s[1::2],u,f[1::2],kx=5,ky=5)(x,y)
  par[name]=float(np.max(np.abs(ev-od)))
 return dict(H_rms=float(np.sqrt(np.mean((R-K2-16*np.pi*E)**2))/norm),M_rms=float(np.sqrt(np.mean((div-8*np.pi*Sm)**2))/(norm*re)),parity=par,header=h.tolist())
base,new,out=map(Path,sys.argv[1:])
with zipfile.ZipFile(base) as z: assert z.testzip() is None; a=assess(z.read('fields.txt'))
b=assess((new/'fields.txt').read_bytes())
result=dict(status='CONTROLLED_QUADRATURE_VARIANT_NOT_CERTIFIED',baseline=a,variant=b,H_ratio=b['H_rms']/a['H_rms'],rho_parity_ratio=b['parity']['rho']/a['parity']['rho'],limits='Same central density and spin; no retargeting, no global constraint or evolution acceptance.')
(out/'parity_comparison.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)

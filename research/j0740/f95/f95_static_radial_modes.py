#!/usr/bin/env python3
"""F95 provisional *nonrotating* radial SL eigensolver; verified original APR(APR) EOS 328.
Not rotating X-PSI EOS evidence nor a dynamic axisymmetric spinning-star analysis.
Source: Eq. Sturm-Liouville in Chandrasekhar radial perturbations (Kokkotas/others).
"""
from pathlib import Path
import math,json,hashlib,zipfile
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.integrate import solve_ivp
from scipy.optimize import brentq
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import eigsh
C=2.99792458e10;G=6.67430e-8;MSUN=1.98847e33;MEVFM=1.602176634e33
A=G*MEVFM*1e10/C**4 # (MeV fm^-3) to km^-2
MKM=G*MSUN/C**2/1e5
BASE=Path(__file__).resolve().parent
SRC=BASE/'source'

def prepare():
 b=(SRC/'F87_verified_publisher_original.zip').read_bytes()
 assert hashlib.sha256(b).hexdigest()=='8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12'
 with zipfile.ZipFile(SRC/'F87_verified_publisher_original.zip') as z:
  for nm in ('eos.nb','eos.thermo','eos.mr'):
   assert z.read(nm)==(SRC/nm).read_bytes()
 nb=np.loadtxt(SRC/'eos.nb',skiprows=2)
 tab=np.loadtxt(SRC/'eos.thermo',skiprows=1)
 mn=float((SRC/'eos.thermo').read_text().splitlines()[0].split()[0])
 P=nb*tab[:,3]; E=nb*mn*(1+tab[:,9]);cs=tab[:,11]
 assert len(P)==1833 and np.all(np.diff(P)>0) and np.all(np.diff(E)>0)
 assert (cs>1).sum()==24
 loge=PchipInterpolator(np.log(P),np.log(E),extrapolate=True)
 def eos(pp):
  pp=np.maximum(pp,P[0]*A);logp=np.log(pp/A)
  ee=A*np.exp(loge(logp)); grad=loge.derivative()(logp)
  dp_de=(pp/ee)/grad
  gamma=(ee+pp)/ee/grad
  return ee,dp_de,gamma
 return P,E,eos,nb,cs

def make_star(pc_mev,eos,P,rtol=1e-9,max_step=.035):
 p0=pc_mev*A;ec=eos(p0)[0];r0=1e-4
 m0=4*np.pi*ec*r0**3/3
 def rhs(r,y):
  m,p,nu=y; p=max(p,P[0]*A)
  e=eos(p)[0]
  met=1-2*m/r
  grav=(m+4*math.pi*r**3*p)/(r*r*met)
  return [4*np.pi*r*r*e,-(e+p)*grav,2*grav]
 def surface(r,y):return y[1]-P[0]*A
 surface.direction=-1;surface.terminal=True
 sol=solve_ivp(rhs,(r0,30),(m0,p0,0),rtol=rtol,atol=[1e-11,1e-20,1e-10],max_step=max_step,events=surface,dense_output=True,method='DOP853')
 if not sol.success or len(sol.t_events[0])!=1:raise RuntimeError('F95_STATIC_SURFACE_NOT_FOUND '+str(sol.message))
 R=float(sol.t_events[0][0]);M=float(sol.y_events[0][0,0]);nu0=float(sol.y_events[0][0,2]);shift=math.log(1-2*M/R)-nu0
 return {'R':R,'M':M,'pc':pc_mev,'m':sol.sol,'shift':shift,'steps':len(sol.t),'rtol':rtol,'max_step':max_step}

def find_M2073(eos,P,rtol=1e-9,max_step=.035):
 def val(p):return make_star(p,eos,P,rtol,max_step)['M']/MKM-2.073
 print('brackets',[(x,val(x)) for x in (150,200,250,300,400,500,600)],flush=True)
 root=brentq(val,150,600,xtol=1e-10)
 star=make_star(root,eos,P,rtol,max_step)
 print('star',root,star['M']/MKM,star['R'],star['steps'],flush=True)
 return star

def matrices(star,eos,P,N=400,rmin=1e-4):
 # center Dirichlet zeta(r0)=0; physical zeta~r^3 exactly at r=0
 R=star['R']
 # inner grid uniform, outer crust beta-weighted refinement; normalizes r intervals
 x=np.linspace(0,1,N+1)
 rr=rmin+(R-rmin)*(1-(1-x)**2.4)
 rowsK=[];colsK=[];valsK=[];rowsB=[];colsB=[];valsB=[]
 T=np.array([[1.,-1.],[-1.,1.]])
 nodes = np.array([0.5-0.5/math.sqrt(3),0.5+0.5/math.sqrt(3)])
 for k in range(N):
  rL,rH=rr[k:k+2];h=rH-rL
  kk=np.zeros((2,2));bb=np.zeros((2,2))
  for t in nodes:
   r=rL+t*h
   m,p,nu=star['m'](r)
   p=max(p,P[0]*A)
   e,cs2,gamma=eos(p)
   nu+=star['shift']
   elambda=1/(1-2*m/r)
   grav=(m+4*math.pi*r**3*p)/(r*r*(1-2*m/r))
   dp=-(e+p)*grav
   v=math.exp(0.5*(math.log(elambda)+3*nu))/r**2
   Pi=gamma*p*v
   Q=v*(dp*dp/(e+p)-4*dp/r-8*math.pi*elambda*p*(e+p))
   W=(e+p)*math.exp(0.5*(3*math.log(elambda)+nu))/r**2
   phi=np.array([1-t,t]);Kloc=Pi/h*T - h*Q*np.outer(phi,phi)
   Bloc=h*W*np.outer(phi,phi)
   kk+=Kloc/2;bb+=Bloc/2
  for i in range(2):
   for j in range(2):
    if k+i==0 or k+j==0:continue
    rowsK.append(k+i-1);colsK.append(k+j-1);valsK.append(kk[i,j])
    rowsB.append(k+i-1);colsB.append(k+j-1);valsB.append(bb[i,j])
 K=coo_matrix((valsK,(rowsK,colsK)),shape=(N,N)).tocsr()
 B=coo_matrix((valsB,(rowsB,colsB)),shape=(N,N)).tocsr()
 return rr,K,B

def radial(star,eos,P,N=400):
 rr,K,B=matrices(star,eos,P,N=N)
 vals,vecs=eigsh(K,M=B,k=4,sigma=0,which='LM',tol=1e-8,maxiter=2000)
 ind=np.argsort(vals);vals=vals[ind];vecs=vecs[:,ind]
 counts=[]
 for i in range(4):
  a=vecs[:,i];mask=np.where(abs(a)>1e-5*np.max(abs(a)))[0]
  z=a[mask]
  counts.append(int(np.count_nonzero(z[:-1]*z[1:]<0)))
 hz=[math.copysign(math.sqrt(abs(x))*C/1e5/(2*math.pi),x) for x in vals]
 return {'N':N,'eigen_omega2_kmminus2':vals.tolist(),'signed_frequency_hz':hz,'node_counts':counts,'min_radius_grid_km':float(rr[0]),'max_radius_grid_km':float(rr[-1])}

if __name__=='__main__':
 P,E,eos,nb,cs=prepare()
 print('units',A,'MKM',MKM,flush=True)
 st=find_M2073(eos,P)
 for n in [250,400,600]:
  try:r=radial(st,eos,P,n);print('RADIAL',json.dumps(r),flush=True)
  except Exception as ex:print('RADIAL_EXCEPTION',n,repr(ex),flush=True)
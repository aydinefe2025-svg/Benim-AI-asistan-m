"""Pinned F171 RNS -> native GR-Athena import data, no new equilibrium fit."""
import hashlib,io,json,pathlib,sys,zipfile
import h5py,numpy as np
from scipy.interpolate import RectBivariateSpline
SOURCE="a7770d2fb40bea0a50d2c2f7f7c60fce1ad755d53b9ccd8648c3b036dfbba77c"
TABLE="bd9cda6359f4e68d4de3a27b3a0e80bd830d0fb3936f91dfea59517e403c090d"
FIELDS="48c0dd8358f42f6e08492d679c4f5fd3b69de59c08ff87893534af1963f68972"
sha=lambda b:hashlib.sha256(b).hexdigest()
raw=pathlib.Path(sys.argv[1]).read_bytes(); assert sha(raw)==SOURCE
out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 assert z.testzip() is None
 field=z.read("fields.txt");table=z.read("model.rns")
 assert sha(field)==FIELDS and sha(table)==TABLE
 ref=json.loads(z.read("reference.json"))
hdr=np.fromstring(field.splitlines()[0].decode()[2:],sep=" ")
ns,nu=map(int,hdr[:2]);re,Omega,es,M,Mb,R=hdr[2:]
a=np.loadtxt(io.BytesIO(field)).reshape(ns,nu,10)
s,u=a[:,0,0],a[0,:,1]
assert np.all(a[:,:,0]==s[:,None]) and np.all(a[:,:,1]==u[None,:])
assert np.all(np.isfinite(a)) and np.min(a[:,:,7])>=0
C=2.99792458e10;G=6.67408e-8;G0=6.673e-8;MS=1.98848e33;MS0=1.989e33;MB=1.66e-24;MEV=1.6021766208e-6
L=G*MS/C**2;F=np.sqrt(1e-15*C*C/G0)/L;D=1e15*L**3/MS
t=np.loadtxt(io.BytesIO(table),skiprows=1)
E,P,H,n=t[:,0]*C*C,t[:,1],t[:,2]/C**2,t[:,3];sl=np.diff(E)/np.diff(P)
assert np.all(sl>=1-1e-10) and np.max(abs((E+P)*np.exp(-H)/(MB*C*C*n)-1))<1e-12
def evaln(q):
 i=np.clip(np.searchsorted(n,q,side="right")-1,0,len(sl)-1)
 dp=(E[i]+P[i])/(1+sl[i])*np.expm1((1+sl[i])/sl[i]*np.log(q/n[i]))
 pp=P[i]+dp;ee=E[i]+sl[i]*dp;cs=1/sl[i]
 low=q<n[0];y=np.cbrt(q[low]/n[0]);v=y/(1+P[0]/E[0]*(1-y))
 pp[low]=P[0]*v**4;ee[low]=E[0]*v**3;cs[low]=4*pp[low]/(3*ee[low])
 return ee,pp,cs
q=np.exp(np.linspace(np.log(n[0]*1e-6),np.log(n[-1]),1048577));q[-1]=n[-1]
eg,pg,cg=evaln(q);nb=q*1e-39;en=eg*1e-39/MEV;pn=pg*1e-39/MEV;mb=MB*C*C/MEV
rng=np.random.default_rng(7406620);probe=np.unique(np.r_[np.exp(rng.uniform(np.log(q[0]),np.log(q[-1]),250000)),n,np.sqrt(n[1:]*n[:-1]),n[1:-1]*(1-1e-8),n[1:-1]*(1+1e-8)])
ep,pp,cp=evaln(probe)
errp=np.max(abs(np.exp(np.interp(np.log(probe),np.log(q),np.log(pg)))/pp-1))
erre=np.max(abs(np.exp(np.interp(np.log(probe),np.log(q),np.log(eg)))/ep-1))
assert max(errp,erre)<1e-4
with h5py.File(out/"cold.h5","w") as f:
 for k,v in {"nb":nb,"mn":[mb],"Q1":pn/nb,"Q2":np.zeros_like(nb),"Q3":(en+pn)/(nb*mb)-1,"Q4":np.zeros_like(nb),"Q5":np.zeros_like(nb),"Q7":en/(nb*mb)-1,"cs2":cg}.items():f[k]=v
with h5py.File(out/"cold.h5") as f:
 assert np.max(abs(f["mn"][0]*(1+f["Q7"][:])*f["nb"][:]/en-1))<1e-14
 assert np.max(abs(f["Q1"][:]*f["nb"][:]/pn-1))<1e-14
# Store cubic Hermite coefficients of the existing metric splines, no smoothing.
cols=[]
for j in range(2,6):
 sp=RectBivariateSpline(s,u,a[:,:,j])
 cols.extend([sp(s,u,dx=ds,dy=du) for ds,du in [(0,0),(1,0),(0,1),(1,1)]])
cols.append(a[:,:,7]) # pressure: bilinear, preserves nonnegative support
node=np.stack(cols,-1).reshape(-1,17)
assert np.all(np.isfinite(node))
with (out/"bridge.dat").open("w") as f:
 f.write(f"{ns} {nu} {len(P)} {re*F:.17e} {Omega/F:.17e} {F:.17e} {D:.17e}\n")
 np.savetxt(f,s[None,:],fmt="%.17e")
 np.savetxt(f,u[None,:],fmt="%.17e")
 np.savetxt(f,np.c_[P/(1e15*C*C),E/(1e15*C*C),H],fmt="%.17e")
 np.savetxt(f,node,fmt="%.17e")
receipt=dict(source_sha=SOURCE,fields_sha=FIELDS,table_sha=TABLE,source_grid=[ns,nu],mass_legacy=M,spin_hz=ref["native"][3],expected_Mb=Mb*MS0/MS,expected_J=float(ref["native"][4])/(G*MS**2/C),radius_coordinate=re*F,domain_halfwidth=2*re*F,pressure_rel=float(errp),energy_rel=float(erre),eos_nodes=len(q),scope="F171 derived cold MPA1; hybrid thermal extension diagnostic; no physical certification")
(out/"input_receipt.json").write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt),flush=True)

import hashlib,io,json,sys,zipfile,shutil
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
root,source,model,grid,out=sys.argv[1:];root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
here=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((here/'exact_barotrope.h').read_bytes())=='709f927bac24685ac4c29d31fa88271b2e93648661ddf759877f38871332b9b8'
manifest={'ENG':'c58bf5f66218863329d192690da97c4e708218c140b19b6da1c62d88e02fa1ad','MPA1':'a9f764c5018da1e5ac350aebe89e2836b3cf4bce4461f3ecbb8029b0004e57e4','MS1':'b17f03e7f58fb4f25523bce442e83fa39e499ad286e9b181107ed1104f65625a','MS1B':'ecbcbaa9b4e5c951fc58dec9f9a1936fd9b1851973512f0b8504bcc050e8bc63','WFF1':'029cb866331d4925e9f286705f8b71a52dd94832c653f6ab622ada4b348be814','WFF2':'e22f2051b4548758009b3e8e25a2809ccf7690a07f3a8e1b5d50b93316b900b2'}
seeds={'ENG':1.143812036790614e-9,'MPA1':7.712607904453857e-10,'MS1':4.769771566864099e-10,'MS1B':4.74617070339011e-10,'WFF1':1.6324068006027125e-9,'WFF2':1.3449424371488425e-9}
assert model in manifest and grid in ('151x301','201x401')
raw=Path(source).read_bytes();assert sha(raw)=='c73eada7da05c015fae75a27f29782aaafc62038a49bc760830f3de4cee6c435'
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 assert z.testzip() is None
 ledger=json.loads(z.read('results/F140/F140_SHA256.json'))
 for f,d in ledger.items():
  path=f if f.startswith('results/') else 'results/F140/'+f;assert sha(z.read(path))==d
 p,e=np.loadtxt(io.BytesIO(z.read('results/F140/'+model+'_F140_DERIVED_NOT_ORIGINAL_EOS_SI.txt'))).T*1e6
e=p+np.maximum.accumulate(e-p)
# Exactly replay local causal-majorant input bytes, not Windows alternate family.
f=out/'candidate_PE_geom_m2.txt';np.savetxt(f,np.c_[p,e]/1e6,fmt='%.17e',header='DERIVED F140 causal majorant candidate P epsilon [m^-2], piecewise linear P; NOT original EOS')
assert sha(f.read_bytes())==manifest[model]
p,e=np.loadtxt(f).T
s=np.diff(e)/np.diff(p);assert np.all(s>=1-1e-10)
h0=4*np.log1p(p[0]/e[0]);h=np.r_[h0,h0+np.cumsum(np.log1p((s+1)*np.diff(p)/(e[:-1]+p[:-1]))/(s+1))]
# Same G,C,MSUN,MB as pinned RNS code (not modern observational constants).
C=2.99792458e10;G=6.673e-8;MSUN=1.989e33;MB=1.66e-24
rho=e*1e-4*C*C/G;pressure=p*1e-4*C**4/G;n=(rho+pressure/C**2)*np.exp(-h)/MB
rows=np.c_[rho,pressure,h*C*C,n];assert np.all(np.diff(rows,axis=0)>0) and len(rows)<=2000
with open('model.rns','w') as a:
 a.write(str(len(rows))+'\n');np.savetxt(a,rows,fmt='%.17e')
assert np.array_equal(np.loadtxt('model.rns',skiprows=1),rows)
shutil.copyfile('model.rns',out/'model.rns')
# Independent static enthalpy ODE at same central density for solver-transfer test.
def pe(H):
 if H<=0:return 0.,0.
 if H<h[0]:
  t=(np.expm1(H/4)/(p[0]/e[0]))**4;return p[0]*t*1e6,e[0]*t**.75*1e6
 j=np.clip(np.searchsorted(h,H,side='right')-1,0,len(s)-1);dp=(p[j]+e[j])*np.expm1((s[j]+1)*(H-h[j]))/(s[j]+1)
 return (p[j]+dp)*1e6,(e[j]+s[j]*dp)*1e6
seed=seeds[model];j=np.clip(np.searchsorted(e,seed,side='right')-1,0,len(s)-1);pc=p[j]+(seed-e[j])/s[j];hc=h[j]+np.log1p((s[j]+1)*(pc-p[j])/(p[j]+e[j]))/(s[j]+1)
def tov(tol):
 P,E=pe(hc);delta=1e-8;r=np.sqrt(3*delta/(2*np.pi*(E+3*P)));m=4*np.pi*E*r**3/3
 def rhs(H,y):
  r,m=y;P,E=pe(H);dr=-r*(r-2*m)/(m+4*np.pi*r**3*P);return [dr,4*np.pi*r*r*E*dr]
 a=solve_ivp(rhs,(hc-delta,0),[r,m],rtol=tol,atol=tol*.01,max_step=.01);assert a.success and a.t[-1]==0
 r,m=a.y[:,-1];return dict(M_msun=float(m/(G*MSUN/C**2/1e5)),R_km=float(r))
static=[tov(2e-9),tov(2e-11)];assert abs(static[0]['M_msun']-static[1]['M_msun'])<1e-5 and abs(static[0]['R_km']-static[1]['R_km'])<1e-4
receipt=dict(model=model,grid=grid,source_sha=sha(raw),candidate_sha=manifest[model],rns_table_sha=sha(Path('model.rns').read_bytes()),nodes=len(p),min_dE_dP=float(s.min()),seed_rho=float(seed*1e-4*C*C/G),upper_rho=float(rho[-1]),static=static,normalization='mu_surface=MB*c^2 conventional; not microscopic calibration')
(out/'inputs.json').write_text(json.dumps(receipt,indent=2));print(receipt,flush=True)
# Replace only thermodynamic lookups, low-pressure cutoff consistency, root
# precision and print diagnostics. No Einstein field equations changed.
def replace(s,a,b):
 assert s.count(a)==1,a
 return s.replace(a,b,1)
f=root/'equil.c';s=f.read_text();s=replace(s,'#include "equil.h"','#include "equil.h"\n#include "exact_barotrope.h"')
s=replace(s,' FILE *f_eos;',' double jp[2000],je[2000];\n FILE *f_eos;')
s=replace(s,'       log_e_tab[i]=log10(rho*C*C*KSCALE);','       jp[i-1]=p*KSCALE; je[i-1]=rho*C*C*KSCALE;\n       log_e_tab[i]=log10(rho*C*C*KSCALE);')
s=replace(s,'    }\n}\n\n\n\n/*******************************************************************/\ndouble e_of_rho0','    }\n    jb_init(*n_tab,jp,je);\n    fclose(f_eos);\n}\n\n\n\n/*******************************************************************/\ndouble e_of_rho0')
for a,b in [('interp(log_p_tab,log_e_tab,n_tab,log10(pp), n_nearest_pt)','jb_e_at_p(pp)'),('interp(log_e_tab,log_p_tab,n_tab,log10(ee), n_nearest_pt)','jb_p_at_e(ee)'),('interp(log_h_tab,log_p_tab,n_tab,log10(hh), n_nearest_pt)','jb_p_at_h(hh)'),('interp(log_p_tab,log_h_tab,n_tab,log10(pp), n_nearest_pt)','jb_h_at_p(pp)'),('interp(log_e_tab,log_n0_tab,n_tab,log10(ee), n_nearest_pt)','jb_nmu_at_e(ee)/(KSCALE*MB*C*C)')]:
 s=replace(s,'pow(10.0,'+a+')',b)
f.write_text(s);shutil.copyfile(here/'exact_barotrope.h',root/'exact_barotrope.h')
f=root/'findmodel.c';s=f.read_text()
s=replace(s,'    star->enthalpy_min=1.0/(C*C);','    star->enthalpy_min=1.0/(C*C);\n    if(strcmp(eos->eos_type,"tab")==0){\n      int near=1;\n      star->e_surface=e_at_p(p_surface,eos->log_e_tab,eos->log_p_tab,eos->n_tab,&near,eos->eos_type,eos->Gamma_P);\n      star->enthalpy_min=h_at_p(p_surface,eos->log_h_tab,eos->log_p_tab,eos->n_tab,&near);\n    }')
# Source contains a second float statement for SetJ; patch SetSpin only.
ix=s.index('int SetSpin(');a=s[:ix];b=s[ix:];needle='  float ans, fh,fl,fm,fnew,sroot,xh,xl,xm,xnew,xacc=1e-5;';assert needle in b;b=b.replace(needle,'  double ans, fh,fl,fm,fnew,sroot,xh,xl,xm,xnew,xacc=1e-9;',1);f.write_text(a+b)
f=root/'rns.c';s=f.read_text();s=replace(s,'printf("%g \\t %4.3f \\t %4.2f \\t %4.1f \\n",','printf("F164_NATIVE %.17e %.17e %.17e %.17e %.17e %.17e %.17e\\n",')
s=replace(s,'star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI));','star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI), star.ang_mom, star.Mass_0/MSUN, star.Omega_K/(2.0*PI));');f.write_text(s)
f=root/'makefile';s=f.read_text();needle='HIGHSIZE=-DMDIV=151 -DSDIV=301';assert s.splitlines().count(needle)==1
if grid=='201x401':f.write_text(s.replace(needle,'HIGHSIZE=-DMDIV=201 -DSDIV=401'))
print('F164_EXACT_ADAPTER_PATCH_AND_SOURCE_IDENTITY_PASS',flush=True)

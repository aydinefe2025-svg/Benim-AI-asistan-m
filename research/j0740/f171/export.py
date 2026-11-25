"""Export the actual stationary RNS solution; no changes to EOS or field equations."""
from pathlib import Path
import sys,json,subprocess,hashlib
root,source,out=map(Path,sys.argv[1:]);out.mkdir(exist_ok=True)
ref=json.loads((source/'result.json').read_text())
assert ref['status']=='NATIVE_EQUILIBRIA_RECORDED' and ref['inputs']['model']=='MPA1'
t=ref['target']
p=root/'rns.c';s=p.read_text()
anchor='  return 0;'
assert s.count(anchor)==1
extra=r'''
  /* F167 export in native dimensionless RNS coordinates and units. */
  FILE *f=fopen("fields.txt","w");
  if(!f) return 91;
  fprintf(f,"# %d %d %.17e %.17e %.17e %.17e %.17e %.17e\n",
    SDIV,MDIV,star.r_e,star.Omega*sqrt(KAPPA)/C,
    star.e_surface,star.Mass/MSUN,star.Mass_0/MSUN,star.R_e*1e-5);
  for(int a=1;a<=SDIV;a++)for(int b=1;b<=MDIV;b++){
    fprintf(f,"%.17e %.17e %.17e %.17e %.17e %.17e %.17e %.17e %.17e %.17e\n",
     star.metric.s_gp[a],star.metric.mu[b],star.metric.alpha[a][b],
     star.metric.gama[a][b],star.metric.rho[a][b],star.metric.omega[a][b],
     star.energy[a][b],star.pressure[a][b],star.enthalpy[a][b],star.velocity_sq[a][b]);
  }
  if(fclose(f)) return 92;
'''
p.write_text(s.replace(anchor,extra+'\n'+anchor))
subprocess.run(['make','-C',str(root),"CC=gcc -include stdlib.h",'rns'],check=True)
import shutil
shutil.copyfile(source/'model.rns',out/'model.rns')
b=root.resolve()/'rns'
import numpy as np
from scipy.optimize import brentq
Mtarget=2.073/(6.673e-8*1.989e33/1.3271244e26)
ftarget=346.536369
journal=out/'retarget_calls.jsonl'
assert not journal.exists()
def evaluate(logrho,ratio):
 rho=float(np.exp(logrho))
 args=[str(b),'-f','model.rns','-e',format(rho,'.17e'),'-r',format(ratio,'.17e')]
 p=subprocess.run(args,cwd=out,capture_output=True,text=True,timeout=300)
 with journal.open('a') as j:j.write(json.dumps(dict(rho=rho,ratio=ratio,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr),allow_nan=False)+'\n')
 assert p.returncode==0,p.stderr
 lines=[x for x in p.stdout.splitlines() if x.startswith('F164_NATIVE ')]
 assert len(lines)==1
 v=list(map(float,lines[0].split()[1:]))
 assert len(v)==7 and np.isfinite(v).all() and abs(v[0]*1e15/rho-1)<1e-8 and v[3]>0
 return v,p.stdout+'\n'+p.stderr
ratio0=t['value'];assert t['command']=='-r'
def at_spin(logrho):
 ratio=brentq(lambda rr:evaluate(logrho,rr)[0][3]-ftarget,ratio0-.002,ratio0+.002,xtol=2e-10,rtol=1e-12,maxiter=30)
 v,log=evaluate(logrho,ratio)
 assert abs(v[3]-ftarget)<.01,(ratio,v)
 return ratio,v,log
x0=np.log(t['rho'])
rho_root=brentq(lambda x:at_spin(x)[1][1]-Mtarget,x0-.005,x0+.005,xtol=2e-9,rtol=1e-12,maxiter=30)
ratio,v,log=at_spin(rho_root)
(out/'native.log').write_text(log)
assert abs(v[1]/Mtarget-1)<1e-5 and abs(v[3]-ftarget)<.01,(Mtarget,v)
assert abs(v[2]-t['R_km'])<.1 and abs(v[4]/t['J']-1)<.02 and abs(v[5]-t['Mb_rns'])<.01
(out/'reference.json').write_text(json.dumps(dict(source=ref['inputs'],target=t,native=v,retarget_ratio=ratio,retarget_rho=float(np.exp(rho_root)),target_msun=2.073,target_spin=ftarget,call_count=len(journal.read_text().splitlines()),binary_sha256=hashlib.sha256(b.read_bytes()).hexdigest()),indent=2))
print('F171_RETARGETED',ref['inputs']['grid'],v,flush=True)

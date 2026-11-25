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
args=[str(b),'-f','model.rns','-e',format(t['rho'],'.17e'),t['command'],format(t['value'],'.17e')]
p=subprocess.run(args,cwd=out,capture_output=True,text=True,timeout=300)
(out/'native.log').write_text(p.stdout+'\n'+p.stderr)
assert p.returncode==0,p.stderr
lines=[x for x in p.stdout.splitlines() if x.startswith('F164_NATIVE ')]
assert len(lines)==1
v=list(map(float,lines[0].split()[1:]))
assert abs(v[1]-t['M_rns'])<.01 and abs(v[2]-t['R_km'])<.1 and abs(v[3]-t['f'])<.05
assert abs(v[4]/t['J']-1)<.02 and abs(v[5]-t['Mb_rns'])<.01
(out/'reference.json').write_text(json.dumps(dict(source=ref['inputs'],target=t,native=v,binary_sha256=hashlib.sha256(b.read_bytes()).hexdigest()),indent=2))
print('F170_CONTROLLED_FIXED_DENSITY_EXPORT',ref['inputs']['grid'],v,flush=True)

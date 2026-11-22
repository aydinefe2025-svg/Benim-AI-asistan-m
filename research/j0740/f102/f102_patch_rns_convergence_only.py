#!/usr/bin/env python3
"""F102 numerical-convergence-only patch on pinned upstream RNS."""
import hashlib,json,sys
from pathlib import Path
OLD_SPIN='float ans, fh,fl,fm,fnew,sroot,xh,xl,xm,xnew,xacc=1e-5;'
NEW_SPIN='double ans, fh,fl,fm,fnew,sroot,xh,xl,xm,xnew,xacc=1e-9;'
OLD_ACC='double accuracy=1e-4;'
NEW_ACC='double accuracy=1e-7;'
SETSPIN='int SetSpin( EOS *eos, NeutronStar *star,'
RNSFN='int rns(double r_ratio,'
SETJ='int SetJ( EOS *eos, NeutronStar *star,'
def patch(path):
 p=Path(path); raw=p.read_bytes(); s=raw.decode('utf-8')
 assert s.count(OLD_SPIN)==1 and s.count(SETSPIN)==1 and s.count(SETJ)==1
 a=s.index(SETSPIN);b=s.index(SETJ,a);assert a<s.index(OLD_SPIN)<b
 s=s.replace(OLD_SPIN,NEW_SPIN,1)
 assert s.count(OLD_ACC)==1 and s.count(RNSFN)==1
 a=s.index(RNSFN); b=s.index(SETJ,a)
 pos=s.index(OLD_ACC,a,b);s=s[:pos]+s[pos:].replace(OLD_ACC,NEW_ACC,1)
 assert s.count(NEW_SPIN)==1 and s.count(NEW_ACC)==1
 p.write_text(s)
 return {'path':str(p),'upstream_sha256':hashlib.sha256(raw).hexdigest(),'patched_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'changes':{'SetSpin_Ridder_scalars':'float -> double','SetSpin_xacc':'1e-5 -> 1e-9','rns_equilibrium_accuracy':'1e-4 -> 1e-7'},'physical_equations_changed':False,'EOS_or_J_or_density_or_acceptance_changed':False}
if __name__=='__main__': print(json.dumps([patch(p) for p in sys.argv[1:]],indent=2))

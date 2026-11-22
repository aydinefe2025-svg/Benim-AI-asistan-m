#!/usr/bin/env python3
"""Upstream rns-alberta/rns::findmodel.c print + SetSpin precision-only patch.

MUST NOT alter native Einstein field equations, EOS source or physical J.
A distinct binary is built and marked PATCHED NUMERIC in all receipts.
"""
import sys,hashlib,json
from pathlib import Path

OLD='float ans, fh,fl,fm,fnew,sroot,xh,xl,xm,xnew,xacc=1e-5;'
NEW='double ans, fh,fl,fm,fnew,sroot,xh,xl,xm,xnew,xacc=1e-9;'
FUNCTION='int SetSpin( EOS *eos, NeutronStar *star,'

def patch(s):
 assert s.count(OLD)==1, 'THE EXACT SOURCE SCALAR NUMERIC FLOAT STATEMENT MUST OCCUR ONCE'
 assert s.count(FUNCTION)==1, 'ORIGINAL C SetSpin SIGNATURE NOT PRESENT'
 assert 0 <= s.index(FUNCTION) < s.index(OLD) < s.index('int SetJ(')
 r=s.replace(OLD,NEW,1)
 assert r.replace(NEW,OLD,1)==s, 'NO PHYSICS SOURCE ALTERATION PERMITTED'
 return r

def main(paths):
 out={}
 for path in paths:
  p=Path(path);original=p.read_bytes();text=original.decode('utf8');adjusted=patch(text).encode('utf8');p.write_bytes(adjusted)
  out[str(p)]={'upstream_findmodel_C_SHA256':hashlib.sha256(original).hexdigest(),
               'patched_findmodel_C_SHA256':hashlib.sha256(adjusted).hexdigest(),
               'diff_exact':{'old':OLD,'new':NEW},'Einstein_equations_changed':False,
               'original_eos_changed':False,'source_substitution_count':1}
 print(json.dumps(out,indent=2))

if __name__=='__main__':main(sys.argv[1:])

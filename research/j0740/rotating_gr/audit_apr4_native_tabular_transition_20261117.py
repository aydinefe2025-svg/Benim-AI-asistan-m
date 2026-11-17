"""APR4_EPP tabular LALSuite derivative transition replay (read-only).

The named APR4_EPP EOS is loaded from LALSimNeutronStarEOS_APR4_EPP.dat,
NOT from the four-parameter piecewise-polytrope constructor.
Compare actual tabular LALSuite 8.0.2 with the SHA-locked JESTER source
and the analytic SLy crust reference without silently replacing either.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

SOURCE_SHA="639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88"
G=6.67430e-11
C=299792458.0
RHO_SI=np.array([0.0,2.44033979e10,3.78358138e14,2.62780487e15])
K_SI=np.array([1.0801158752700761e7,1.311359898998385e10,6.507604807550857e19,3.053461077133694e8])
GAMMA=np.array([1.58424999,1.28732904,0.62223344,1.35692395])

def sha256(path:Path)->str:
 return hashlib.sha256(path.read_bytes()).hexdigest()

def compare(source:Path,version:str="8.0.2")->dict:
 import lal
 import lalsimulation as lalsim
 if sha256(source)!=SOURCE_SHA:
  raise ValueError("pinned JESTER APR4_EPP NPZ mismatch")
 with np.load(source,allow_pickle=False) as z:
  if str(z["eos_name"].item())!="APR4_EPP":
   raise ValueError("incorrect EOS name")
  p,e,h,cs=(np.asarray(z[k],float) for k in ("p","e","h","cs2"))
 if any(len(v)!=865 for v in (p,e,h,cs)):raise ValueError("unexpected NPZ row count")
 if not np.all((p>0)&(e>0)&(cs>0)):raise ValueError("invalid source low-pressure nodes")
 eos=lalsim.SimNeutronStarEOSByName("APR4_EPP")
 rsi=G*RHO_SI/C**2
 k=K_SI*G**(1.0-GAMMA)*C**(2.0*GAMMA-4.0)
 ni=1.0/(GAMMA-1.0)
 pb=k[1:]*rsi[1:]**GAMMA[1:]
 a=np.zeros(4)
 for i in range(1,4):
  a[i]=a[i-1]+(ni[i-1]-ni[i])*pb[i-1]/rsi[i]
 mask=p<=pb[-1]
 idxs=np.flatnonzero(mask)
 v_native={"e":[],"h":[],"cs2":[]}
 v_analytic={"e":[],"h":[],"cs2":[]}
 for i in idxs:
  pp=float(p[i])
  v_native["e"].append(lalsim.SimNeutronStarEOSEnergyDensityOfPressureGeometerized(pp,eos))
  v_native["h"].append(lalsim.SimNeutronStarEOSPseudoEnthalpyOfPressureGeometerized(pp,eos))
  dedp=lalsim.SimNeutronStarEOSEnergyDensityDerivOfPressureGeometerized(pp,eos)
  v_native["cs2"].append(1.0/dedp)
  piece=max(0,int(np.searchsorted(np.r_[0.,pb],pp,side="left")-1))
  rho=(pp/k[piece])**(1./GAMMA[piece])
  en=(1.+a[piece])*rho+ni[piece]*pp
  hh=np.log(1.+a[piece]+(ni[piece]+1.)*pp/rho)
  sound=GAMMA[piece]*pp/(en+pp)
  v_analytic["e"].append(float(en))
  v_analytic["h"].append(float(hh))
  v_analytic["cs2"].append(float(sound))
 for d in (v_native,v_analytic):
  for key in d:d[key]=np.asarray(d[key],float)
 assert all(np.isfinite(d[k]).all() for d in (v_native,v_analytic) for k in ("e","h","cs2"))
 compare_metrics={}
 for k,orig in (("e",e[mask]),("h",h[mask]),("cs2",cs[mask])):
  compare_metrics[k]={
   "max_rel_diff_native_vs_source":float(np.max(np.abs(v_native[k]/orig-1))),
   "max_rel_diff_analytic_vs_source":float(np.max(np.abs(v_analytic[k]/orig-1))),
   "max_rel_diff_native_vs_analytic":float(np.max(np.abs(v_native[k]/v_analytic[k]-1)))
  }
 probe=[]
 for i in range(258,269):
  jj=int(i)
  pi=np.where(idxs==jj)[0]
  if len(pi)!=1:raise ValueError("missing low-pressure source sample")
  q=int(pi[0])
  probe.append({
   "row_index_zero_based":jj,
   "p_geom_m_inv2":float(p[jj]),
   "p_over_transition":float(p[jj]/pb[1]),
   "cs2_JESTER_source":float(cs[jj]),
   "cs2_LAL_native_tabular":float(v_native["cs2"][q]),
   "cs2_analytic_four_piece_crust":float(v_analytic["cs2"][q]),
   "gamma_effective_JESTER":float(cs[jj]*(e[jj]+p[jj])/p[jj]),
   "gamma_effective_LAL_native":float(v_native["cs2"][q]*(v_native["e"][q]+p[jj])/p[jj]),
   "relative_native_minus_JESTER":float(v_native["cs2"][q]/cs[jj]-1.),
   "relative_analytic_minus_JESTER":float(v_analytic["cs2"][q]/cs[jj]-1.)
  })
 transition=probe[4] # zero-based row 262
 improvement=abs(transition["relative_native_minus_JESTER"]) < abs(transition["relative_analytic_minus_JESTER"])
 out={
  "schema":"j0740-lalsuite-byname-apr4-epp-tabular-derivative-crosscheck-v1",
  "input":{"JESTER_npz_sha256":SOURCE_SHA,"n_source_rows":len(p),"n_crust_rows":len(idxs)},
  "native_reference":{"library":"lalsuite","requested_version":version,"reported_lalsimulation_version":getattr(lalsim,"__version__","unknown"),"reported_lal_version":getattr(lal,"__version__","unknown"),"named_eos":"APR4_EPP","loader":"XLALSimNeutronStarEOSByName -> XLALSimNeutronStarEOSFromFile -> tabular interpolation"},
  "analytic_model":{"reference":"four-piece SLy low-density analytic approximation, NOT named table identity","gamma":GAMMA.tolist(),"transition_pressures_m_inv2":pb.tolist()},
  "metrics":compare_metrics,"transition_probe":probe,
  "checks":{
   "source_sha_ok":True,
   "native_rows_finite":True,
   "native_closer_than_analytic_at_row262":bool(improvement),
   "source_transition_gamma_in_analytic_bracket":bool(GAMMA[2]<transition["gamma_effective_JESTER"]<GAMMA[1])
  },
  "status":"REFERENCE_VERSION_CROSSCHECK_ONLY__EOS_NOT_CERTIFIED",
  "limitations":[
   "JESTER generator LALSuite dependency version was not pinned. This run is explicitly LALSuite "+version+".",
   "APR4_EPP is a named tabulated LALSuite EOS, not the four-parameter analytic constructor.",
   "Any residual mismatch requires inspection of native table version/units/interpolation, not silent clamping.",
   "This does not certify high-density causality, baryon normalization, RNS target rotation root, or EOS Bayes."
  ]
 }
 return out

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--source",required=True,type=Path)
 parser.add_argument("--output",required=True,type=Path)
 x=parser.parse_args()
 d=compare(x.source)
 if x.output.exists():raise FileExistsError("refusing overwrite")
 x.output.parent.mkdir(parents=True,exist_ok=True)
 x.output.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
 print(json.dumps({"output":str(x.output),"source":d["input"],"metrics":d["metrics"],"row262":d["transition_probe"][4],"checks":d["checks"]},indent=2))

if __name__=="__main__":main()

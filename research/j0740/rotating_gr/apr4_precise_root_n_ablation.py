"""Six actual RNS C/GR evaluations at the ALREADY VERIFIED APR4 mass-spin root.

Change ONLY EOS column 4 (baryon number n). Same 196-point (epsilon, P, H),
same central energy density, axis ratio and RNS C binary. Quantify M0's
dependence on the thermodynamic first-law column and RNS MB convention.
This is conditional numerical sensitivity, NOT physically certified EOS.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from precise_apr4_mass_spin_root import run_model
from jester_to_rns import from_jester_npz,write_rns
SOURCE_SHA="639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88"
OLD_TABLE_SHA="c8f4da82524a5e0b3450c682198359078deb78d573a1f50f2487235df16d88c7"
MAVG_G=1.673774710865e-24
RNS_MB_G=1.66e-24
ROOTS=(
 ("rns_151x301",1754499753449583.5,0.9861323240269972),
 ("rns_201x401",1755892141395923.5,0.9861776900224013),
)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def baryon_variants(rows,e,p,h):
 rows=np.asarray(rows,float);e=np.asarray(e,float);p=np.asarray(p,float);h=np.asarray(h,float)
 if rows.ndim!=2 or rows.shape[1]!=4 or e.shape!=p.shape or e.shape!=h.shape or e.shape!=(len(rows),):
  raise ValueError("bad EOS source shape")
 if not np.isfinite(rows).all() or any(not np.isfinite(v).all() for v in (e,p,h)):raise ValueError("EOS nonfinite")
 if (rows<=0).any() or (e<=0).any() or (p<=0).any() or np.any(np.diff(h)<=0):
  raise ValueError("EOS nonpositive or nonmonotone h")
 ratio=(1+p/e)*np.exp(-h)
 out={"native_approx":rows.copy()}
 for name,factor in (("firstlaw_mavg",1.),("firstlaw_rns_mb",MAVG_G/RNS_MB_G)):
  x=rows.copy();x[:,3]=rows[:,3]*ratio*factor
  if np.any(np.diff(x[:,3])<=0) or not np.isfinite(x[:,3]).all():
   raise ValueError("non-monotonic first-law number density")
  if not np.array_equal(x[:,:3],rows[:,:3]):
   raise AssertionError("EOS structural columns changed")
  out[name]=x
 return out
def create_tables(source,work):
 if sha(source)!=SOURCE_SHA:raise ValueError("APR4 NPZ SHA mismatch")
 native,meta=from_jester_npz(source,points=196)
 with np.load(source,allow_pickle=False) as z:
  p=np.asarray(z["p"],float);e=np.asarray(z["e"],float);h=np.asarray(z["h"],float)
 pt=np.geomspace(p[0],p[-1],196)
 et=np.exp(np.interp(np.log(pt),np.log(p),np.log(e)))
 ht=np.interp(np.log(pt),np.log(p),h)
 variants=baryon_variants(native,et,pt,ht)
 work.mkdir(parents=True,exist_ok=True)
 paths={}
 for key,v in variants.items():
  path=work/("apr4_"+key+".rns");write_rns(path,v);paths[key]=path
 if sha(paths["native_approx"])!=OLD_TABLE_SHA:raise AssertionError("baseline EOS row hash drifted")
 return paths,meta
def perform(source,binaries,work,out):
 if len(binaries)!=2:raise ValueError("two independent mesh binaries required")
 paths,conversion=create_tables(source,work)
 doc={
  "schema":"j0740-apr4-precise-RNS-Mf-root-n-only-ablation-v1",
  "status":"IN_PROGRESS",
  "source":{"jester_npz_sha256":SOURCE_SHA,"root_run":44049313908,"root_commit":"37f77c0de187f511744c3a9dd99fb5d11d096b7e",
            "root_table_sha256":OLD_TABLE_SHA,"RNS_MB_g":RNS_MB_G,"JESTER_mavg_g":MAVG_G,
            "ablation_table_sha256":{k:sha(v) for k,v in paths.items()}},
  "scope":"Same P,e,H EOS and same fixed exact-root (ec,ratio) for native and two h-firstlaw n columns; no RNS root repetition; 6 direct C/GR solves",
  "conversion":conversion,"meshes":[],
  "physical_EOS_certification":"NOT_ESTABLISHED","EOS_Bayes":"NOT_RUN"}
 def checkpoint():
  out.parent.mkdir(parents=True,exist_ok=True)
  out.write_text(json.dumps(doc,sort_keys=True,indent=2)+"\n",encoding="utf-8")
 checkpoint()
 for (name,ec,ratio),binary in zip(ROOTS,binaries):
  entry={"grid":name,"root_ec_g_cm3":ec,"root_axis_ratio":ratio,"binary_sha256":sha(binary),"runs":{},"checks":{}}
  doc["meshes"].append(entry);checkpoint()
  for key in ("native_approx","firstlaw_mavg","firstlaw_rns_mb"):
   entry["runs"][key]=run_model(binary,paths[key],ec,ratio)
   checkpoint()
  a=entry["runs"]["native_approx"]
  if abs(a["mass_msun"]-2.073)>1e-5 or abs(a["spin_hz"]-346.536369)>1e-4:
   raise AssertionError("baseline exact root was not reproduced")
  for key in ("firstlaw_mavg","firstlaw_rns_mb"):
   v=entry["runs"][key]
   for f in ("mass_msun","spin_hz","radius_eq_km"):
    if v[f]!=a[f]:raise AssertionError(name+": metric changed with fourth EOS column "+f)
   if not v["rns_M0_using_native_Mb_msun"]<a["rns_M0_using_native_Mb_msun"]:
    raise AssertionError(name+": firstlaw M0 unexpectedly >= source approx M0")
  m0_native=a["rns_M0_using_native_Mb_msun"]
  m0_mavg=entry["runs"]["firstlaw_mavg"]["rns_M0_using_native_Mb_msun"]
  m0_mb=entry["runs"]["firstlaw_rns_mb"]["rns_M0_using_native_Mb_msun"]
  if abs(m0_mb/m0_mavg-MAVG_G/RNS_MB_G)>3e-7:
   raise AssertionError("RNS mass-convention factor was not reproduced")
  entry["checks"]={"baseline_root_pass":True,"all_M_R_f_bitwise_equal":True,
   "M0_original_approx_msun_UNPHYSICAL":m0_native,
   "M0_firstlaw_mavg_msun_CONDITIONAL":m0_mavg,
   "M0_firstlaw_RNS_MB_msun_CONDITIONAL":m0_mb,
   "pct_delta_M0_mavg":(m0_mavg/m0_native-1)*100,
   "pct_delta_M0_RNS_MB":(m0_mb/m0_native-1)*100,
   "mavg_div_MB_recovered":m0_mb/m0_mavg}
  checkpoint()
 doc["status"]="PASS_CONDITIONAL_N_ONLY_ABLATION_GEOMETRY_INVARIANT"
 doc["limitations"]=[
   "Original JESTER n≈e/mavg violates first-law density; not a valid physical M0.",
   "First-law M0 assumes source LALSuite h absolute normalization and RNS MB=1.66e-24g; source starts at P>0.",
   "Changing n alone is not a crust/stability/causality certification or EOS Bayes inference.",
   "Exact-Mf root (ec,ratio) was reused, not solved again."
 ]
 checkpoint()
 print(json.dumps({"status":doc["status"],"results":[dict(grid=x["grid"],**x["checks"]) for x in doc["meshes"]],
                   "output_json_sha256":sha(out)},indent=2))
 return doc
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--source",required=True,type=Path)
 p.add_argument("--binary",required=True,nargs=2,type=Path)
 p.add_argument("--work",required=True,type=Path)
 p.add_argument("--out",required=True,type=Path)
 a=p.parse_args()
 perform(a.source,a.binary,a.work,a.out)
if __name__=="__main__":main()

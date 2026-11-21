from __future__ import annotations
import argparse, hashlib, json, subprocess, zipfile
from pathlib import Path
import numpy as np

ARCHIVE_SHA="8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12"
ARCHIVE_MD5="ccc2fbef2b0f51df389ff8f7d9b00608"
RNS_COMMIT="97e85d325a33e37f702306414533f6cd77812477"
MEV_FM3_TO_ERG_CM3=1.602176634e33
C=2.99792458e10
MASS=2.073
SPIN_HZ=346.536369

def digest(b): return hashlib.sha256(b).hexdigest()

def read_source(root):
    archive=(root/"psr_J0740+6620_with_3p6_Years_of_NICER_Data.tar.gz").read_bytes() if (root/"psr_J0740+6620_with_3p6_Years_of_NICER_Data.tar.gz").exists() else None
    # The F87 source probe is the publisher-provenance gate; these exact files must
    # be byte-identical to their unique members in the verified source ZIP.
    zip_paths=list(root.glob("*.zip"))
    if archive is not None and not zip_paths: raise ValueError("Expected verified F87 ZIP artifact absent")
    zpath=next((p for p in zip_paths if hashlib.md5(p.read_bytes()).hexdigest()==ARCHIVE_MD5),None)
    if zpath is None: raise ValueError("PUBLISHER_ZIP_MD5_MISMATCH_OR_MISSING")
    zb=zpath.read_bytes()
    if digest(zb)!=ARCHIVE_SHA: raise ValueError("PUBLISHER_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(zpath) as z:
        if z.testzip() is not None: raise ValueError("PUBLISHER_ZIP_CRC_FAILURE")
        member_hash={}
        for name in ("eos.nb","eos.thermo","eos.mr"):
            matches=[m for m in z.namelist() if m.rsplit("/",1)[-1]==name]
            if len(matches)!=1 or (root/name).read_bytes()!=z.read(matches[0]): raise ValueError("PUBLISHER_MEMBER_MISMATCH:"+name)
            member_hash[name]=digest(z.read(matches[0]))
    hdr=(root/"eos.nb").read_text().split()
    if hdr[:2]!=["1","1833"]: raise ValueError("UNEXPECTED_EOS_NB_HEADER")
    n=np.loadtxt(root/"eos.nb",skiprows=2)
    t=np.loadtxt(root/"eos.thermo",skiprows=1)
    if n.shape!=(1833,) or t.shape!=(1833,12): raise ValueError("EOS_SHAPE_MISMATCH")
    mn=float((root/"eos.thermo").read_text().splitlines()[0].split()[0])
    p=n*t[:,3]                 # source-native P=n Q1
    e=n*mn*(1+t[:,9])          # source-native energy density
    mu=(e+p)/n
    mu0=mn*(1+t[:,5])
    cs2=t[:,11]
    for key,a in (("n",n),("P",p),("epsilon",e),("mu",mu)):
        if not np.all(np.isfinite(a)) or np.any(a<=0) or np.any(np.diff(a)<=0): raise ValueError("INVALID_OR_NONMONOTONE_"+key)
    h=np.r_[0.,np.cumsum(np.diff(p)/((e[:-1]+p[:-1]+e[1:]+p[1:])*.5))]
    h_mu=np.log(mu/mu[0])
    herr=float(np.max(np.abs(h-h_mu)))
    if herr>1e-4: raise ValueError("FIRST_LAW_ENTHALPY_CROSSCHECK_FAILED")
    bad=np.flatnonzero(cs2>1)
    if not len(bad): raise ValueError("EXPECTED_SOURCE_CAUSALITY_AUDIT_MISSING")
    i=int(bad[0])
    info={"source_archive_sha256":ARCHIVE_SHA,"source_archive_md5":ARCHIVE_MD5,"publisher_member_sha256":member_hash,
      "source_points":1833,"firstlaw_mu_max_discrepancy_MeV":float(np.max(np.abs(mu-mu0))),
      "firstlaw_integral_vs_log_mu_max_abs":herr,"native_cs2_gt1_count":int(len(bad)),
      "native_cs2_max":float(np.max(cs2)),"first_native_acausal_index":i,
      "first_native_acausal_nB_fm3":float(n[i]),"first_native_acausal_energy_density_g_cm3":float(e[i]*MEV_FM3_TO_ERG_CM3/C**2),
      "first_native_acausal_pressure_MeV_fm3":float(p[i])}
    return n,p,e,h,cs2,info

def write_table(root,out):
    n,p,e,h,cs2,info=read_source(root)
    x=np.linspace(np.log(p[0]),np.log(p[-1]),196); po=np.exp(x)
    eo=np.exp(np.interp(x,np.log(p),np.log(e))); no=np.exp(np.interp(x,np.log(p),np.log(n)))
    ho=np.interp(x,np.log(p),h)
    # RNS schema: rho_mass-equivalent, pressure, H=c^2 int(dP/(e+P))+1, n_B.
    rows=np.column_stack((eo*MEV_FM3_TO_ERG_CM3/C**2,po*MEV_FM3_TO_ERG_CM3,1+C**2*ho,no*1e39))
    if not np.all(np.isfinite(rows)) or np.any(rows<=0) or not np.all(np.diff(rows,axis=0)>0): raise ValueError("RNS_TABLE_INVALID")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text("196\n"+"".join(" ".join(f"{v:.15e}" for v in row)+"\n" for row in rows))
    info.update({"rns_table_sha256":digest(out.read_bytes()),"rns_table_points":196,"source_preserved":True,
      "rns_columns":["energy_density_g_cm3","pressure_dyn_cm2","enthalpy_cm2_s2","baryon_density_cm3"],
      "enthalpy_definition":"H=1+c^2 integral_source_min^P dP/(epsilon+P)"})
    return rows,info,cs2

def run(binary,table,rho,spin):
    p=subprocess.run([str(binary.resolve()),"-f","./"+table.name,"-e",f"{rho:.12g}","-s",f"{spin:.9f}"],
      cwd=table.parent,text=True,capture_output=True,timeout=180)
    if p.returncode: raise RuntimeError("RNS_EXIT_"+str(p.returncode)+":"+p.stderr[-400:])
    rows=[]
    for line in p.stdout.splitlines():
        c=line.split()
        if len(c)==4:
            try: v=[float(x) for x in c]
            except ValueError: continue
            if np.all(np.isfinite(v)): rows.append(v)
    if len(rows)!=1: raise ValueError("RNS_EXPECTED_ONE_OUTPUT_ROW:"+str(len(rows)))
    r,m,req,f=rows[0]
    if not(.5<m<3.5 and 7<req<25 and abs(r*1e15-rho)<max(5e11,rho*1e-4)): raise ValueError("RNS_RESULT_INVALID")
    if spin and abs(f-spin)>.25: raise ValueError("RNS_SPIN_RESIDUAL_GT_0.25_HZ")
    return {"central_energy_density_g_cm3":rho,"mass_msun":m,"radius_eq_km":req,"requested_spin_hz":spin,"reported_spin_hz":f,"spin_residual_hz":f-spin}

def root(binary,table,spin,lo,hi):
    trace=[]
    def ev(x):
        try:
            r=run(binary,table,x,spin); trace.append(r); return r
        except (RuntimeError,ValueError,subprocess.TimeoutExpired) as e:
            trace.append({"central_energy_density_g_cm3":x,"status":"REJECTED","reason":type(e).__name__+":"+str(e)[:240]}); return None
    a,b=ev(lo),ev(hi)
    if a is None or b is None or not a["mass_msun"]<MASS<b["mass_msun"]: raise ValueError("MASS_ROOT_BRACKET_FAILURE")
    for _ in range(36):
        f=min(.9,max(.1,(MASS-a["mass_msun"])/(b["mass_msun"]-a["mass_msun"])))
        accepted=False
        for q in (f,.5,.382,.618,.25,.75,.1,.9):
            x=lo+q*(hi-lo); r=ev(x)
            if r is None: continue
            if not a["mass_msun"]-.002<=r["mass_msun"]<=b["mass_msun"]+.002: raise ValueError("NONMONOTONE_STABLE_BRANCH_SAMPLE")
            if abs(r["mass_msun"]-MASS)<=.0015: return r,trace
            if r["mass_msun"]<MASS: lo,a=x,r
            else: hi,b=x,r
            accepted=True; break
        if not accepted: break
    raise RuntimeError("RNS_FIXED_MASS_ROOT_NOT_CERTIFIED")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-dir",type=Path,required=True); ap.add_argument("--rns",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True); ap.add_argument("--grid",choices=("151x301","201x401"),required=True)
    a=ap.parse_args(); table=a.out.with_name("eosF87_compose_apr_unified")
    _,info,cs2=write_table(a.source_dir,table)
    ib=int(np.flatnonzero(cs2>1)[0]); _,_,e,_,_,_=read_source(a.source_dir)
    rho_bad=float(e[ib]*MEV_FM3_TO_ERG_CM3/C**2); lo,hi=1.45e15,rho_bad*.999
    stat,st= root(a.rns,table,0.,lo,hi); rot,rt=root(a.rns,table,SPIN_HZ,lo,hi)
    tov=json.loads((a.source_dir/"F87_REAL_ORIGINAL_APR_TOV.json").read_text())
    ref=float(tov["target_M2p073_static"]["R_km"])
    delta=stat["radius_eq_km"]-ref
    if abs(delta)>.25: raise ValueError("RNS_STATIC_VS_INDEPENDENT_TOV_RADIUS_GT_0.25_KM")
    if rot["central_energy_density_g_cm3"]>=rho_bad: raise ValueError("TARGET_CENTER_REACHES_SOURCE_ACAUSAL_NODE")
    out={"schema":"J0740_F87_COMPOSE_APR_RNS_FIXED_SPIN_V1","rns_upstream_commit":RNS_COMMIT,"rns_binary_sha256":digest(a.rns.read_bytes()),
      "grid":a.grid,"target_mass_msun":MASS,"target_spin_hz":SPIN_HZ,"source":info,"static_TOV_reference_radius_km":ref,
      "static_RNS_minus_independent_TOV_radius_km":delta,"static_at_target":stat,"rotating_at_target":rot,
      "rotating_minus_static_equatorial_radius_km":rot["radius_eq_km"]-stat["radius_eq_km"],
      "static_root_trace":st,"rotating_root_trace":rt,"global_causality":"FAIL_ORIGINAL_SOURCE_HAS_SUPERLUMINAL_NODES",
      "target_star_center_below_first_superluminal_source_node":True,"EOS_Bayes":"NOT_RUN","stability":"NOT_ESTABLISHED",
      "physical_scope":"fixed-mass, fixed-spin numerical C/RNS equilibrium; no event likelihood or posterior"}
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:v for k,v in out.items() if not k.endswith("_trace")},indent=2))
if __name__=="__main__": main()

#!/usr/bin/env python3
"""Export the named BPS–MPA1 EOS in native RNS units and optionally solve J0740.

RNS source is pinned externally to rns-alberta/rns commit
97e85d325a33e37f702306414533f6cd77812477. Its tabulated input is rho[g/cm^3],
P[dyn/cm^2], H*c^2[cm^2/s^2], n_b[cm^-3]. The baryon number density comes from
the absolute first-law normalization, not the source LALSimulation n column.
"""
from __future__ import annotations
import argparse, hashlib, json, math, re, subprocess
import sys
from pathlib import Path
import numpy as np
from scipy.optimize import brentq
sys.path.insert(0,str(Path(__file__).resolve().parent))
from jester_bps_mpa1_matched_tov import Hybrid, MU0_GEOM, G, C, MSUN_GEOM, tov, find_pc_for_mass

HERE=Path(__file__).resolve().parent
RNS_REPO="rns-alberta/rns"
RNS_COMMIT="97e85d325a33e37f702306414533f6cd77812477"
TARGET_M=2.073
TARGET_SPIN_HZ=346.536369
CGS_C=2.99792458e10
CGS_G=6.673e-8

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def export_rns_eos(path:Path,n_grid=800,max_enthalpy=1.5):
    eos=Hybrid(subdivisions=1)
    if max_enthalpy>=eos.hmax:raise ValueError("RNS table enthalpy exceeds completed EOS domain")
    hs=np.unique(np.r_[np.geomspace(1e-9,max_enthalpy,n_grid),eos.hh,eos.h0,eos.ht])
    hs=hs[(hs>0)&(hs<=max_enthalpy)]
    if len(hs)>1950:raise ValueError("RNS EOS exceeds 1950-point safety limit (RNS arrays hold 2001)")
    rows=[]
    for h in hs:
        p,e=eos.state_h(float(h))
        n=(e+p)/(MU0_GEOM*math.exp(float(h))) # m^-3; exact cold first law
        # Convert geometrized SI m^-2 to RNS cgs density and pressure.
        rho_cgs=e*C**2/G*1e-3
        p_cgs=p*C**4/G*10.0
        h_cgs=float(h)*CGS_C**2
        n_cgs=n/1e6
        rows.append((rho_cgs,p_cgs,h_cgs,n_cgs))
    a=np.asarray(rows)
    if not np.isfinite(a).all() or np.any(a<=0) or np.any(np.diff(a,axis=0)<=0):
        raise ValueError("RNS EOS table must be finite, positive and strictly increasing")
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="ascii",newline="\n") as f:
        f.write(f"{len(a)}\n")
        np.savetxt(f,a,fmt="%.15e")
    return {"path":path.name,"sha256":sha(path),"rows":len(a),
      "columns":["rho_g_cm3","P_dyn_cm2","H_times_c2_cm2_s2","baryon_number_density_cm3"],
      "firstlaw_absolute_mu_surface_MeV":930.4,"source_native_n_used":False,
      "density_min_max":[float(a[0,0]),float(a[-1,0])],"pressure_min_max":[float(a[0,1]),float(a[-1,1])],
      "enthalpy_min_max":[float(a[0,2]/CGS_C**2),float(a[-1,2]/CGS_C**2)],
      "baryon_n_min_max_cm3":[float(a[0,3]),float(a[-1,3])],"max_rows":1950}

def parse_rns_stdout(stdout):
    numeric=[]
    for line in stdout.splitlines():
        cols=line.split()
        if len(cols)!=4:continue
        try: vals=[float(c) for c in cols]
        except ValueError:continue
        if all(math.isfinite(x) for x in vals):numeric.append(vals)
    if not numeric:raise RuntimeError("RNS output did not contain its four-column model row: "+stdout[-2000:])
    ec15,mass,radius,spin=numeric[-1]
    return {"central_energy_density_1e15_g_cm3":ec15,"M_msun":mass,"R_equatorial_km":radius,"spin_hz":spin}

def solve_one_grid(rns_binary,eos_path,grid_tag):
    eos=Hybrid(subdivisions=1)
    pc=find_pc_for_mass(eos,TARGET_M); h=eos.h_at_p(pc); _,ec=eos.state_h(h)
    rho_guess=ec*CGS_C**2/CGS_G*1e-3
    def evaluate(logrho):
        rho=10.0**float(logrho)
        eos_arg=os.path.relpath(eos_path,Path.cwd())
        if len(eos_arg)>=75:raise ValueError("RNS source char[80] EOS path is too long; use a short relative path")
        cmd=[str(rns_binary),"-f",eos_arg,"-e",f"{rho:.14e}","-s",f"{TARGET_SPIN_HZ:.9f}"]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=180,check=False)
        if p.returncode!=0:raise RuntimeError(f"RNS failed ({p.returncode}) at rho={rho:g}: {p.stdout[-1000:]} {p.stderr[-1000:]}")
        row=parse_rns_stdout(p.stdout)
        row["rho_c_g_cm3"]=rho;row["mass_residual_msun"]=row["M_msun"]-TARGET_M
        row["stdout_tail"]=p.stdout[-1200:]
        return row
    logs=np.log10(rho_guess)+np.array([-0.20,-0.10,0.0,0.10,0.20])
    rows=[evaluate(x) for x in logs]
    bracket=None
    for left,right in zip(rows[:-1],rows[1:]):
        if left["mass_residual_msun"]==0 or left["mass_residual_msun"]*right["mass_residual_msun"]<0:
            bracket=(math.log10(left["rho_c_g_cm3"]),math.log10(right["rho_c_g_cm3"]));break
    if bracket is None:
        raise RuntimeError("RNS mass root not bracketed near independent TOV seed; "+json.dumps(rows))
    root=brentq(lambda x:evaluate(x)["mass_residual_msun"],*bracket,xtol=3e-6,rtol=1e-12,maxiter=12)
    final=evaluate(root)
    final.update({"grid":grid_tag,"root_bracket_log10_rho":list(bracket),"seed_rho_g_cm3":rho_guess,
      "mass_tolerance_msun":1e-5,"spin_tolerance_hz":0.1,
      "status":"PASS" if abs(final["mass_residual_msun"])<1e-5 and abs(final["spin_hz"]-TARGET_SPIN_HZ)<0.1 else "FAIL"})
    return {"result":final,"trace":rows}

def run(args):
    eosfile=Path(args.eos_file)
    export=export_rns_eos(eosfile)
    out={"schema":"J0740_BPS_MPA1_RNS_V1","status":"EOS_EXPORT_PASS_RNS_NOT_RUN",
      "model":"JESTER_BPS_CRUST_LAL_MPA1_HIGH_PRESSURE_CROSSING_CAUSAL_TAIL_V1",
      "rns_source":{"repository":RNS_REPO,"commit":RNS_COMMIT},"rns_eos_export":export,
      "targets":{"mass_msun":TARGET_M,"spin_hz":TARGET_SPIN_HZ},
      "limits":{"new_model_RNS":"NOT_RUN","XPSI_source_native_marginalization":"NOT_RUN","final_EOS_Bayes":"NOT_RUN"}}
    if args.rns_binary:
        if len(args.rns_binary)!=2 or len(args.grid_tags)!=2:
            raise ValueError("RNS convergence claim requires exactly two independently compiled grid binaries")
        binaries=args.rns_binary
        runs=[solve_one_grid(Path(b),eosfile,tag) for b,tag in zip(binaries,args.grid_tags)]
        for result,binary in zip(runs,binaries):
            result["rns_binary_sha256"]=sha(binary)
            result["rns_binary_path"]=str(binary)
        results=[r["result"] for r in runs]
        dm=abs(results[0]["M_msun"]-results[-1]["M_msun"])
        dr=abs(results[0]["R_equatorial_km"]-results[-1]["R_equatorial_km"])
        converged=(all(r["status"]=="PASS" for r in results) and dm<1e-4 and dr<0.05)
        out.update({"status":"PASS_RNS_TWO_GRID_CONVERGENCE" if converged else "FAIL_RNS_OR_GRID_CONVERGENCE",
          "RNS_runs":runs,"grid_convergence":{"mass_difference_msun":dm,"radius_difference_km":dr,"mass_tolerance_msun":1e-4,"radius_tolerance_km":0.05,"passed":converged},
          "limits":{"new_model_RNS":"PASS" if converged else "FAIL","XPSI_source_native_marginalization":"NOT_RUN","final_EOS_Bayes":"NOT_RUN"}})
    return out

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--eos-file",type=Path,default=HERE/"JESTER_BPS_MPA1_RNS_20261119.rns");ap.add_argument("--rns-binary",type=Path,nargs="*");ap.add_argument("--grid-tags",nargs="*",default=["151x301","201x401"]);ap.add_argument("--output",type=Path,default=HERE/"JESTER_BPS_MPA1_RNS_20261119.json");a=ap.parse_args();r=run(a);a.output.write_text(json.dumps(r,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8");print(json.dumps(r,indent=2,sort_keys=True))


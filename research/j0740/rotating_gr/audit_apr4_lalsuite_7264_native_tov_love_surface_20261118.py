from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

TABLE_SHA = "2a63cd7f1e1c5a158bb3cc06ab4b51f4344a9a1e6bfaeec7f98937c3d5a5447f"
JESTER_SHA = "639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88"
LAL_TABULAR_C_SHA = "1c84c672e663d853b1ef87f9bb23520e85ab007c2b4e66048d2abc82bc7825df"
G=6.67430e-11; C=299792458.0; MSUN_GEOM_M=1476.6250385
TARGET_M=2.073; SURFACE_P=1e-33

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def relative_max(a,b):
    d=np.abs(np.asarray(a)/np.asarray(b)-1.0); i=int(np.argmax(d))
    return {"max_abs_relative":float(d[i]),"index":i}

class NativeTable:
    def __init__(self, table: Path):
        if sha(table)!=TABLE_SHA: raise ValueError("official LALSuite APR4_EPP table SHA mismatch")
        t=np.loadtxt(table); self.p=t[:,0]; self.e=t[:,1]
        if t.shape!=(1447,2) or not np.all(np.diff(self.p)>0) or not np.all(np.diff(self.e)>0):
            raise ValueError("APR4 table shape/monotonicity failure")
        self.lp=np.log(self.p); self.le=np.log(self.e)
        self.e_spline=CubicSpline(self.lp,self.le,bc_type="natural")
        self.ratio=float(self.p[0]/self.e[0]); self.h0=float(self.ratio/(1+self.ratio))
        f=self.p/(self.e+self.p)
        self.h_nodes=self.h0+np.r_[0.,np.cumsum(.5*(f[1:]+f[:-1])*np.diff(self.lp))]
        self.h_spline=CubicSpline(self.lp,np.log(self.h_nodes),bc_type="natural")
        self.delta_h=float(2.5*np.log1p(self.ratio)-self.h0)
    def values(self,p:float,corrected=True):
        if not (0<p<=self.p[-1]): raise ValueError("pressure outside source EOS")
        if p<self.p[0]:
            x=p/self.p[0]; e=self.e[0]*x**0.6
            h=2.5*math.log1p(self.ratio*x**0.4) if corrected else self.h0*x**0.4
            cs2=5*p/(3*e)
        else:
            lp=math.log(p); e=math.exp(float(self.e_spline(lp)))
            h=math.exp(float(self.h_spline(lp)))+(self.delta_h if corrected else 0.)
            cs2=p/(e*float(self.e_spline(lp,1)))
        return e,h,cs2
    def star(self,logpc,step,corrected=True,surface_p:SURFACE_P=SURFACE_P):
        pc=math.exp(logpc); ec,hc,csc=self.values(pc,corrected)
        rho_c=(ec+pc)*math.exp(-hc); r0=.01
        m0=4*math.pi*ec*r0**3/3; mb0=4*math.pi*rho_c*r0**3/3; qsurf=math.log(surface_p)
        def rhs(r,s):
            m,q,Y,mb=s; p=math.exp(q); e,h,cs2=self.values(p,corrected)
            den=max(1-2*m/r,1e-15); grav=(m+4*math.pi*r**3*p)/den
            dp=-(e+p)*grav/r**2; dm=4*math.pi*r**2*e
            rb=(e+p)*math.exp(-h); dmb=4*math.pi*r**2*rb/math.sqrt(den)
            ff=(1-4*math.pi*r**2*(e-p))/den
            Q=4*math.pi*(5*e+9*p+(e+p)/max(cs2,1e-30))/den-6/(r*r*den)-4*grav**2/r**4
            dY=-(Y*Y+Y*ff+r*r*Q)/r
            return [dm,dp/p,dY,dmb]
        def surface(r,s): return s[1]-qsurf
        surface.terminal=True; surface.direction=-1
        sol=solve_ivp(rhs,(r0,1e6),[m0,logpc,2.,mb0],method="DOP853",rtol=2e-9,
                      atol=[1e-5,1e-11,1e-9,1e-5],max_step=step,events=surface)
        if not sol.success or len(sol.t_events[0])!=1: raise RuntimeError(sol.message)
        R=sol.t_events[0][0]; m,q,Y,mb=sol.y_events[0][0]; Cc=m/R
        num=(8*Cc**5/5)*(1-2*Cc)**2*(2+2*Cc*(Y-1)-Y)
        den=2*Cc*(6-3*Y+3*Cc*(5*Y-8))+4*Cc**3*(13-11*Y+Cc*(3*Y-2)+2*Cc**2*(1+Y))+3*(1-2*Cc)**2*(2-Y+2*Cc*(Y-1))*math.log1p(-2*Cc)
        k2=num/den; lam=(2/3)*k2/Cc**5
        return {"Mg_msun":m/MSUN_GEOM_M,"R_km":R/1000,"k2":k2,"Lambda":lam,
                "Mb_conditional_msun":mb/MSUN_GEOM_M,"central_cs2":csc,"Pc_geom_m2":pc,"ode_steps":len(sol.t)}

def run(table:Path,jester:Path|None):
    eos=NativeTable(table); data={"source_table":{"bytes":table.stat().st_size,"sha256":sha(table),"tag":"lalsuite-v7.26.4","tag_commit":"fc92814767cd01523d546a07d325b1dd6759a1a0","rows":len(eos.p),"official_source_url":"https://git.ligo.org/lscsoft/lalsuite/-/blob/lalsuite-v7.26.4/lalsimulation/lib/LALSimNeutronStarEOS_APR4_EPP.dat","tabular_code_path":"lalsimulation/lib/LALSimNeutronStarEOSTabular.c","tabular_code_bytes":23457,"tabular_code_sha256":LAL_TABULAR_C_SHA},
        "method":{"interpolation":"GSL-compatible natural cubic spline in log(e)-log(P); h from LALSuite linear-integrand quadrature then natural spline","Q_term":"-6/[r^2(1-2m/r)]","surface_pressure_geom_m2":SURFACE_P,"h_extension":"first-law exact integral for e=e0*(P/P0)^(3/5); h=2.5 ln(1+(P0/e0)*(P/P0)^(2/5)); shift table h by delta_h for continuity","delta_h":eos.delta_h,"low_pressure_enthalpy_interface":None},"solutions":[],"checks":{},"jester_replay":None}
    p0=float(eos.p[0]); e0=float(eos.e[0]); h0=float(eos.h0); dlnh=float(eos.h_spline(math.log(p0),1)); htab=float(math.exp(eos.h_spline(math.log(p0))))
    table_dh_ratio=float((htab/p0*dlnh)*(e0+p0)); native_extension_dh_ratio=float(.4*h0/p0*(e0+p0))
    data["method"]["low_pressure_enthalpy_interface"]={"native_LAL_extension_dh_dp_over_thermo":native_extension_dh_ratio,"tabular_right_dh_dp_over_thermo":table_dh_ratio,"native_derivative_jump_relative":native_extension_dh_ratio/table_dh_ratio-1,"firstlaw_matched_extension_dh_dp_over_thermo":1.0,"matched_extension_vs_table_right_relative":1/table_dh_ratio-1,"h0_firstlaw":float(2.5*np.log1p(eos.ratio)),"delta_h":eos.delta_h}
    lo_e=G*(1.5e15*1000)/C**2; hi_e=G*(2.1e15*1000)/C**2
    lo=float(np.interp(math.log(lo_e),eos.le,eos.lp)); hi=float(np.interp(math.log(hi_e),eos.le,eos.lp))
    for step in (400.,200.,100.):
        root=brentq(lambda z:eos.star(z,step)["Mg_msun"]-TARGET_M,lo,hi,xtol=2e-11,rtol=2e-12,maxiter=35)
        row=eos.star(root,step); row["max_step_m"]=step; row["mass_residual_msun"]=row["Mg_msun"]-TARGET_M
        data["solutions"].append(row)
    fine=data["solutions"][-1]; prev=data["solutions"][-2]
    data["mesh_deltas"]={"delta_R_km_100_vs_200":fine["R_km"]-prev["R_km"],"delta_Lambda_rel_100_vs_200":fine["Lambda"]/prev["Lambda"]-1,"delta_Mb_msun_100_vs_200":fine["Mb_conditional_msun"]-prev["Mb_conditional_msun"]}
    # Compare the exact LAL tabular h normalization with its first-law-consistent vacuum continuation at 200 m.
    root200=math.log(data["solutions"][1]["Pc_geom_m2"])
    native=eos.star(root200,200.,corrected=False)
    data["surface_h_normalization_ablation"]={"native_LAL_extension_Mb_msun":native["Mb_conditional_msun"],"firstlaw_matched_Mb_msun":data["solutions"][1]["Mb_conditional_msun"],"delta_Mb_msun":data["solutions"][1]["Mb_conditional_msun"]-native["Mb_conditional_msun"],"relative_delta_Mb":data["solutions"][1]["Mb_conditional_msun"]/native["Mb_conditional_msun"]-1}
    surface_scan=[]
    for floor in (1e-27,1e-33,1e-36):
        if floor==SURFACE_P: row=data["solutions"][1]
        else:
            root=brentq(lambda z:eos.star(z,200.,surface_p=floor)["Mg_msun"]-TARGET_M,lo,hi,xtol=2e-11,rtol=2e-12,maxiter=35)
            row=eos.star(root,200.,surface_p=floor)
        surface_scan.append({"P_surface_geom_m2":floor,**row})
    data["surface_floor_scan"]=surface_scan
    flo=surface_scan[1]; fhi=surface_scan[2]
    data["surface_floor_delta_1e-33_to_1e-36"]={"delta_R_km":fhi["R_km"]-flo["R_km"],"delta_Lambda_relative":fhi["Lambda"]/flo["Lambda"]-1}
    if jester:
        if sha(jester)!=JESTER_SHA: raise ValueError("JESTER APR4 NPZ SHA mismatch")
        z=np.load(jester,allow_pickle=False); p=z["p"]; e=z["e"]; h=z["h"]; d=z["dloge_dlogp"]; cs=z["cs2"]
        le=eos.e_spline(np.log(p)); slope=eos.e_spline(np.log(p),1); hp=np.exp(eos.h_spline(np.log(p)))
        data["jester_replay"]={"source_sha256":sha(jester),"rows":len(p),"e":relative_max(e,np.exp(le)),"h":relative_max(h,hp),"dloge":relative_max(d,slope),"cs2":relative_max(cs,p/(np.exp(le)*slope))}
    data["checks"]={"mass_root_all_below_1e-8":all(abs(x["mass_residual_msun"])<1e-8 for x in data["solutions"]),"causal_central_cs2_all":all(0<x["central_cs2"]<1 for x in data["solutions"]),"lambda_positive":all(x["Lambda"]>0 for x in data["solutions"]),"mesh_lambda_delta_below_1e-5":bool(abs(data["mesh_deltas"]["delta_Lambda_rel_100_vs_200"])<1e-5),"jester_native_replay_below_1e-9":data["jester_replay"] is not None and max(v["max_abs_relative"] for k,v in data["jester_replay"].items() if isinstance(v,dict))<1e-9,"surface_floor_tolerance_pass":bool(abs(data["surface_floor_delta_1e-33_to_1e-36"]["delta_R_km"])<1e-6 and abs(data["surface_floor_delta_1e-33_to_1e-36"]["delta_Lambda_relative"])<1e-5),"native_LAL_h_join_firstlaw_discontinuity_detected":abs(native_extension_dh_ratio/table_dh_ratio-1)>0.5,"corrected_h_join_residual_below_1percent":abs(1/table_dh_ratio-1)<0.01}
    data["status"]="PASS_CONDITIONAL_NATIVE_TABLE_TOV_LOVE; APR4_PHYSICAL_EOS_NOT_CERTIFIED; EOS_Bayes=NOT_RUN"
    if not all(data["checks"].values()): raise AssertionError(data["checks"])
    return data

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--table",type=Path,required=True);ap.add_argument("--jester-npz",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);args=ap.parse_args()
    doc=run(args.table,args.jester_npz);args.output.write_text(json.dumps(doc,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"output":str(args.output),"bytes":args.output.stat().st_size,"sha256":sha(args.output),"status":doc["status"],"checks":doc["checks"],"solutions":doc["solutions"],"mesh_deltas":doc["mesh_deltas"],"h_ablation":doc["surface_h_normalization_ablation"],"jester_replay":doc["jester_replay"]},indent=2))
if __name__=="__main__":main()
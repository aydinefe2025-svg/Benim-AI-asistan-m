#!/usr/bin/env python3
"""First-law surface completion of the separate F67 MPA1-PCHIP alternative.

The F67 table and original JESTER MPA1 source are SHA-pinned. The original
data are never edited. Below the F67 table floor, epsilon(P)=epsilon0*(P/P0)^a
is a phenomenological cold crust surrogate with a fixed slope a taken from the
PCHIP derivative at the join. Its surface chemical potential is 930.4 MeV per
baryon. The n(P) normalization follows the zero-temperature first law.

This does not make the result original MPA1 or a microphysical BPS crust.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
from numpy.polynomial import Polynomial
from scipy.integrate import solve_ivp
from scipy.interpolate import PchipInterpolator
from scipy.optimize import minimize_scalar

MODEL="MPA1_PCHIP_NATIVE_LAL_CORE_FIRSTLAW_POWERLAW_CRUST_MU930p4_V1"
F67_SHA="d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22"
JESTER_MPA1_SHA="0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22"
G=6.67430e-11; C=299792458.0; MEV_J=1.602176634e-13
MU0_MEV=930.4; MSUN_GEOM=G*1.988409870698051e30/C**2
DEFAULT_TABLE=Path(__file__).with_name("F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat")

def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class EOS:
    def __init__(self,path,subdivisions=2,quadrature=24):
        self.table_sha=sha256(path)
        if self.table_sha!=F67_SHA: raise ValueError("F67 source-table SHA mismatch")
        a=np.loadtxt(path,comments="#",dtype=float)
        if (a.shape!=(2425,4) or not np.isfinite(a).all() or np.any(a[:,:2]<=0)
                or np.any(a[:,2]<0) or np.any(a[:,3]<=0)):
            raise ValueError("F67 source-table shape/value check failed")
        self.p,self.e,self.h_relative,self.n_relative=a.T
        if not (np.all(np.diff(self.p)>0) and np.all(np.diff(self.e)>0) and
                np.all(np.diff(self.h_relative)>0) and np.all(np.diff(self.n_relative)>0)):
            raise ValueError("F67 table is not monotone")
        self.logp=np.log(self.p); self.loge=np.log(self.e)
        self.spline=PchipInterpolator(self.logp,self.loge,extrapolate=False)
        self.p0=float(self.p[0]); self.e0=float(self.e[0]); self.x0=float(self.logp[0])
        self.a=float(self.spline(self.x0,1))
        if not 0<self.a<1: raise ValueError(f"non-integrable crust slope: {self.a}")
        self.h0=math.log1p(self.p0/self.e0)/(1-self.a)
        self.mu0_geom=G*(MU0_MEV*MEV_J/C**2)/C**2
        self.n0=(self.e0+self.p0)/(self.mu0_geom*math.exp(self.h0))
        # Integrate the PCHIP enthalpy anew; compare with archived F67 H values.
        gx,gw=np.polynomial.legendre.leggauss(quadrature)
        xs=np.concatenate([np.linspace(x,y,subdivisions+1)[:-1]
                           for x,y in zip(self.logp[:-1],self.logp[1:])]+[self.logp[-1:]])
        hs=[self.h0]
        for x,y in zip(xs[:-1],xs[1:]):
            z=(x+y)/2+(y-x)*gx/2; p=np.exp(z); e=np.exp(self.spline(z))
            hs.append(hs[-1]+float((y-x)/2*np.sum(gw*p/(p+e))))
        self.xh=xs; self.hh=np.asarray(hs)
        if np.any(np.diff(self.hh)<=0): raise ValueError("nonmonotone enthalpy")
        self.inverse_h=PchipInterpolator(self.hh,self.xh,extrapolate=False)
        self.forward_h=PchipInterpolator(self.xh,self.hh,extrapolate=False)
        self.pt=float(self.p[-1]); self.et=float(self.e[-1]); self.ht=float(self.hh[-1])
        self.tail_pc_max=self.pt*1.0e4
        self.hmax=self.ht+0.5*math.log((self.et-self.pt+2*self.tail_pc_max)/(self.et+self.pt))
        self.source_H_at_p=np.interp(self.logp,self.xh,self.hh)-self.h0
        self.enthalpy_residual=self.source_H_at_p-self.h_relative
        self.n_formula=(self.e+self.p)/(self.mu0_geom*np.exp(self.h0+self.h_relative))
        self.n_formula_ratio=self.n_formula/self.n0
        # Original JESTER density is epsilon/m_avg, not a physical first-law n.
        self.causal=self.sound_speed_extrema()

    def crust_state_h(self,h):
        if h<=0: return 0.0,0.0
        x=(self.e0/self.p0)*math.expm1((1-self.a)*h)
        x=x**(1/(1-self.a))
        return self.p0*x,self.e0*x**self.a

    def state_h(self,h):
        h=float(np.clip(h,0,self.hmax))
        if h<=self.h0: return self.crust_state_h(h)
        if h>self.ht:
            p=0.5*((self.et+self.pt)*math.exp(2*(h-self.ht))-(self.et-self.pt))
            e=self.et+(p-self.pt)
            return p,e
        x=float(self.inverse_h(h)); p=math.exp(x); e=math.exp(float(self.spline(x)))
        return p,e

    def enthalpy_at_logp(self,x):
        if x<=self.logp[-1]: return float(self.forward_h(x))
        p=math.exp(x)
        return self.ht+0.5*math.log((self.et-self.pt+2*p)/(self.et+self.pt))

    def sound_speed_extrema(self):
        # Exact stationary points of c_s^2 on each cubic PCHIP segment.
        cmin=math.inf; cmax=0.0; roots=0
        for i in range(len(self.logp)-1):
            xi=float(self.logp[i]); dx=float(self.logp[i+1]-xi)
            c=self.spline.c[:,i]
            s=Polynomial([float(c[3]),float(c[2]),float(c[1]),float(c[0])])
            q=s.deriv(); stationary=(Polynomial([1.])-q)*q-q.deriv()
            pts=[0.0,dx]
            for r in stationary.roots():
                if abs(r.imag)<1e-9*max(1.,abs(r.real)) and 0<r.real<dx:
                    pts.append(float(r.real)); roots+=1
            for z in pts:
                slope=float(q(z))
                if slope<=0: raise ValueError("nonpositive dlogE/dlogP")
                cs2=math.exp(xi+z-float(s(z)))/slope
                cmin=min(cmin,cs2); cmax=max(cmax,cs2)
        crust_join=self.p0/(self.e0*self.a)
        # c_s^2 in the power-law crust is monotone increasing for 0<a<1.
        return {"core_intervals_checked":len(self.logp)-1,"core_stationary_roots_checked":roots,
                "core_cs2_min":cmin,"core_cs2_max":cmax,"crust_cs2_surface":0.0,
                "crust_cs2_join":crust_join,"crust_cs2_monotone":True,
                "high_density_tail":"epsilon=epsilon_t+(P-P_t), cs2=1, first-law consistent",
                "tail_cs2":1.0,
                "whole_defined_model_causal":bool(cmin>0 and cmax<=1 and crust_join<=1)}

def tov(eos,pc,method="rm",rtol=2e-9):
    if not eos.p0<pc<eos.tail_pc_max: raise ValueError("central pressure outside completed EOS")
    hc=eos.enthalpy_at_logp(math.log(pc))
    delta=min(1e-6,hc*1e-4); p_c,e_c=eos.state_h(hc)
    r0=math.sqrt(3*delta/(2*math.pi*(e_c+3*p_c))); m0=4*math.pi*e_c*r0**3/3
    if method=="rm":
        def f(h,y):
            r,m=y;p,e=eos.state_h(h);den=m+4*math.pi*r**3*p
            dr=-r*(r-2*m)/den; return [dr,4*math.pi*r*r*e*dr]
        y0=[r0,m0]
    elif method=="uv":
        def f(h,y):
            u,v=y;p,e=eos.state_h(h);den=v+4*math.pi*u*p
            return [-2*u*(1-2*v)/den,(v-4*math.pi*u*e)*(1-2*v)/den]
        y0=[r0*r0,m0/r0]
    else: raise ValueError("unknown TOV method")
    sol=solve_ivp(f,(hc-delta,0.),y0,method="DOP853",rtol=rtol,atol=2e-11,max_step=.008)
    if not sol.success or sol.t[-1]!=0.: raise RuntimeError(sol.message)
    if method=="rm": r,m=sol.y[:,-1]
    else: u,v=sol.y[:,-1];r=math.sqrt(u);m=v*r
    if not (0<2*m<r and r>0 and m>0 and math.isfinite(r) and math.isfinite(m)):
        raise ValueError("invalid TOV root")
    return {"M_msun":float(m/MSUN_GEOM),"R_km":float(r/1000),"central_pressure_geom":float(pc),"central_enthalpy":hc,"surface_pressure_geom":0.0,"method":method}

def max_mass(eos,nscan=48):
    pc=np.geomspace(eos.p0*1.000001,eos.tail_pc_max/1.001,nscan)
    seq=[(x,tov(eos,float(x))) for x in pc]
    mm=np.array([y["M_msun"] for _,y in seq]);j=int(np.argmax(mm))
    if j==0 or j==len(seq)-1: raise RuntimeError("turning point not bracketed")
    lo,hi=math.log(seq[j-1][0]),math.log(seq[j+1][0])
    opt=minimize_scalar(lambda x:-tov(eos,math.exp(x))["M_msun"],bounds=(lo,hi),method="bounded",options={"xatol":2e-12})
    result=tov(eos,math.exp(float(opt.x)));result["scan_count"]=len(seq);result["method_note"]="first stable-branch mass maximum bracketed by full Pc scan"
    return result

def run(path):
    coarse=EOS(path,subdivisions=1,quadrature=24); fine=EOS(path,subdivisions=2,quadrature=48)
    if not fine.causal["whole_defined_model_causal"]: raise ValueError("global continuous causality failed")
    mc=max_mass(coarse,40); mf=max_mass(fine,52); uv=tov(fine,mf["central_pressure_geom"],"uv")
    dm=mf["M_msun"]-mc["M_msun"]; dr=mf["R_km"]-mc["R_km"]
    mrel=abs(uv["M_msun"]-mf["M_msun"])/mf["M_msun"];rrel=abs(uv["R_km"]-mf["R_km"])/mf["R_km"]
    if max(mrel,rrel)>5e-5: raise ValueError("independent TOV formulations disagree")
    return {"schema":"J0740_MPA1_F67_HMATCH_CRUST_TOV_V1","status":"PASS_NUMERICAL_HYBRID_CANDIDATE_NOT_MICROPHYSICAL_ACCEPTANCE","model":MODEL,
      "provenance":{"F67_table_sha256":fine.table_sha,"F67_table_rows":len(fine.p),"JESTER_original_MPA1_npz_sha256":JESTER_MPA1_SHA,"original_data_modified":False},
      "crust_join":{"P0_geom_m-2":fine.p0,"epsilon0_geom_m-2":fine.e0,"log_slope_a":fine.a,"mu_surface_MeV_per_baryon":MU0_MEV,"mu0_source":"Baym, Pethick & Sutherland 1971, ApJ 170, 299, DOI 10.1086/151216; iron-ground-state approximation 930.4 MeV/baryon","h_surface_to_join":fine.h0,"h_surface_formula":"log1p(P0/epsilon0)/(1-a)","absolute_n0_at_join_m-3":fine.n0,"n_first_law_over_n0_max_relative_residual":float(np.max(np.abs(fine.n_formula_ratio/fine.n_relative-1))),"native_enthalpy_relative_max_abs_difference":float(np.max(np.abs(fine.enthalpy_residual))),"caveat":"The low-pressure power-law crust is thermodynamic and surface-normalized, but has no verified BPS composition table."},
      "causality":fine.causal,
      "tov":{"coarse_subdiv1_quad24_Mmax":mc,"fine_subdiv2_quad48_Mmax":mf,"independent_u_v_same_turning_point":uv,"relative_difference_independent_mass":mrel,"relative_difference_independent_radius":rrel,"fine_minus_coarse_mass_msun":dm,"fine_minus_coarse_radius_km":dr},
      "high_density_completion":{"type":"maximally stiff causal continuation c_s^2=1 above source Pmax","Pmax_source_geom_m-2":fine.pt,"epsilon_at_Pmax_geom_m-2":fine.et,"completion_is_separately_named":True},
      "limits":{"microphysical_crust_identity":"NOT_ESTABLISHED: low-pressure crust surrogate lacks BPS composition table","high_density_microphysical_identity":"NOT_ESTABLISHED: cs2=1 is an explicit causal bound completion, not a nuclear calculation","physical_EOS_acceptance":"NOT_ESTABLISHED","new_hybrid_model_RNS":"NOT_RUN","source_native_XPSI_nuisance_marginalization":"NOT_RUN","final_EOS_Bayes":"NOT_RUN"}}

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--table",type=Path,default=DEFAULT_TABLE);ap.add_argument("--output",type=Path,default=Path(__file__).with_name("MPA1_F67_hybrid_crust_TOV_20261119.json"));a=ap.parse_args()
    out=run(a.table);a.output.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8");print(json.dumps(out,indent=2,sort_keys=True))

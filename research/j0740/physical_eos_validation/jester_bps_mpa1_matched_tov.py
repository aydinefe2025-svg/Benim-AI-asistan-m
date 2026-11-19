#!/usr/bin/env python3
"""Construct and solve a named BPS–MPA1 matched cold EOS candidate.

Source EOS files are immutable exports. The low-pressure nonmonotone interval
of the LALSimulation MPA1 table is replaced by the pinned JESTER BPS crust.
The BPS and native MPA1 log-e(log-P) curves are joined at their highest-pressure
crossing, so P and epsilon are continuous without a fitted energy offset. The
remaining high-pressure tail is explicitly the maximally stiff causal bound.
This is a distinct hybrid model, not original MPA1 or a microphysical causal tail.
"""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np
from numpy.polynomial import Polynomial
from scipy.integrate import solve_ivp
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq, minimize_scalar

HERE=Path(__file__).resolve().parent
BPS_FILE=HERE/"JESTER_BPS_crust_e6768650.csv"
MPA_FILE=HERE/"JESTER_LALSuite_MPA1_source_e6768650.csv"
BPS_SHA="a4195d48ae98fd64d0a9676891ccab5a5c035e713780ad1187e85571a98a1787"
MPA_NPZ_SHA="0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22"
CORE_START=254                 # row 254 is the first row after the native cs2<0 glitch
CRUST_START=40                 # validated below as the BPS knot closest to μ_surface=930.4 MeV
MU0_MEV=930.4
G=6.67430e-11; C=299792458.0; MEV_J=1.602176634e-13
MSUN_GEOM=G*1.988409870698051e30/C**2
MEVFM3_GEOM=G*1.602176634e32/C**4
MU0_GEOM=G*(MU0_MEV*MEV_J/C**2)/C**2
MODEL="JESTER_BPS_CRUST_LAL_MPA1_HIGH_PRESSURE_CROSSING_CAUSAL_TAIL_V1"

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class Hybrid:
    def __init__(self, quadrature=32, subdivisions=2):
        if sha(BPS_FILE)!=BPS_SHA: raise ValueError("BPS CSV SHA mismatch")
        b=np.loadtxt(BPS_FILE,delimiter=",",skiprows=1)
        m=np.loadtxt(MPA_FILE,delimiter=",",skiprows=1)
        if b.shape!=(130,3) or m.shape!=(836,5) or not np.isfinite(b).all() or not np.isfinite(m).all():
            raise ValueError("source table dimensions/finite-value check failed")
        self.bn,self.bp,self.be=b[:,0],b[:,1]*MEVFM3_GEOM,b[:,2]*MEVFM3_GEOM
        self.mp,self.me,self.mn,self.mh,self.mcs=m[:,1],m[:,2],m[:,0],m[:,3],m[:,4]
        mu_bps_tab=(b[:,1]+b[:,2])/b[:,0]
        self.crust_start=int(1+np.argmin(np.abs(mu_bps_tab[1:]-MU0_MEV)))
        if self.crust_start!=CRUST_START: raise ValueError("BPS surface-anchor knot selection changed")
        self.bps_anchor_mu_mev=float(mu_bps_tab[self.crust_start])
        self.bx=np.log(self.bp[CRUST_START:]); self.by=np.log(self.be[CRUST_START:])
        self.mx=np.log(self.mp[CORE_START:]); self.my=np.log(self.me[CORE_START:])
        if not (np.all(np.diff(self.bx)>0) and np.all(np.diff(self.by)>0)
                and np.all(np.diff(self.mx)>0) and np.all(np.diff(self.my)>0)):
            raise ValueError("post-cut source logP/logE monotonicity failed")
        self.bs=PchipInterpolator(self.bx,self.by,extrapolate=False)
        self.ms=PchipInterpolator(self.mx,self.my,extrapolate=False)
        lo=max(self.bx[0],self.mx[0]); hi=min(self.bx[-1],self.mx[-1])
        grid=self.bx[(self.bx>lo)&(self.bx<hi)]
        grid=np.unique(np.r_[lo,grid,hi])
        d=np.array([float(self.ms(x)-self.bs(x)) for x in grid])
        roots=[]
        for i in range(len(grid)-1):
            if d[i]==0: roots.append(float(grid[i]))
            elif d[i]*d[i+1]<0:
                roots.append(float(brentq(lambda x: float(self.ms(x)-self.bs(x)),grid[i],grid[i+1],xtol=2e-14)))
        if not roots: raise ValueError("no BPS/MPA1 P-e crossing in stable source overlap")
        self.crossings=np.array(roots); self.xt=float(roots[-1]); self.pt=math.exp(self.xt)
        self.eb=math.exp(float(self.bs(self.xt))); self.em=math.exp(float(self.ms(self.xt)))
        self.join_energy_rel=self.em/self.eb-1
        if abs(self.join_energy_rel)>2e-10: raise ValueError("join crossing does not match energy")
        self.p0=float(self.bp[CRUST_START]); self.e0=float(self.be[CRUST_START]); self.x0=math.log(self.p0)
        self.a=float(self.bs(self.x0,1))
        if not 0<self.a<1: raise ValueError("surface power-law slope is not integrable/causal")
        self.h0=math.log1p(self.p0/self.e0)/(1-self.a)
        self.pmax=float(self.mp[-1]); self.emax=float(self.me[-1]); self.xtmax=math.log(self.pmax)
        self.tailpcmax=self.pmax*1e4
        # Enthalpy integral on each true interpolation interval, split at the join.
        xb=np.unique(np.r_[self.bx[self.bx<self.xt],self.xt])
        xm=np.unique(np.r_[self.xt,self.mx[self.mx>self.xt]])
        nodes=[]
        for arr in (xb,xm):
            for l,r in zip(arr[:-1],arr[1:]):
                nodes.extend(np.linspace(l,r,subdivisions+1)[:-1])
        nodes=np.unique(np.r_[self.x0,nodes,self.xt,self.xtmax])
        nodes=nodes[(nodes>=self.x0)&(nodes<=self.xtmax)]
        gx,gw=np.polynomial.legendre.leggauss(quadrature)
        hs=[self.h0]
        for l,r in zip(nodes[:-1],nodes[1:]):
            z=(l+r)/2+(r-l)*gx/2; p=np.exp(z); e=np.exp(self.loge(z))
            hs.append(hs[-1]+float((r-l)/2*np.sum(gw*p/(p+e))))
        self.hx=nodes; self.hh=np.asarray(hs)
        self.h_of_x=PchipInterpolator(self.hx,self.hh,extrapolate=False)
        self.x_of_h=PchipInterpolator(self.hh,self.hx,extrapolate=False)
        self.ht=float(self.h_of_x(self.xt)); self.hmax=self.ht+.5*math.log((self.emax-self.pmax+2*self.tailpcmax)/(self.emax+self.pmax))
        self.causality=self.continuous_cs2()
        # A tabulated n is only a cross-check; absolute n is reconstructed from μ0 and h.
        ib=int(np.argmin(abs(self.bn-self.bn_at_pressure(self.pt))))
        self.n_bps_at_join=float(self.bn_at_pressure(self.pt))
        self.n_join_firstlaw=(self.eb+self.pt)/(MU0_GEOM*math.exp(self.ht))
        self.n_join_rel=self.n_join_firstlaw/(self.n_bps_at_join*1e45)-1
        self.mu_bps=float(np.interp(self.xt,np.log(self.bp),np.log((self.be+self.bp)/(self.bn*1e45))))
        self.mu_bps_mev=math.exp(self.mu_bps)/MU0_GEOM*MU0_MEV
        self.mu_join_mev=MU0_MEV*math.exp(self.ht)
        # Source n is explicitly not used as the first-law normalization.
        self.n_mpa_at_join=float(np.interp(self.xt,self.mx,np.log(self.mn[CORE_START:])))
        self.n_mpa_at_join=math.exp(self.n_mpa_at_join)
        self.cs2_join_left=float(math.exp(self.xt-float(self.bs(self.xt)))/float(self.bs(self.xt,1)))
        self.cs2_join_right=float(math.exp(self.xt-float(self.ms(self.xt)))/float(self.ms(self.xt,1)))

    def bn_at_pressure(self,p): return float(np.interp(math.log(p),np.log(self.bp),self.bn))
    def loge(self,x):
        a=np.asarray(x)
        if a.ndim==0:return float(self.bs(float(a))) if float(a)<=self.xt else float(self.ms(float(a)))
        if np.max(a)<=self.xt:return np.asarray(self.bs(a))
        if np.min(a)>self.xt:return np.asarray(self.ms(a))
        raise ValueError("quadrature interval crossed the EOS match")
    def state_h(self,h):
        h=float(np.clip(h,0,self.hmax))
        if h<=self.h0:
            y=(self.e0/self.p0)*math.expm1((1-self.a)*h)
            z=y**(1/(1-self.a)); return self.p0*z,self.e0*z**self.a
        if h>self.hh[-1]:
            p=.5*((self.emax+self.pmax)*math.exp(2*(h-self.hh[-1]))-(self.emax-self.pmax))
            e=self.emax+(p-self.pmax); return p,e
        x=float(self.x_of_h(h)); p=math.exp(x); return p,math.exp(self.loge(x))

    def h_at_p(self,p):
        if p<=0:return 0.
        if p<self.p0:
            return math.log1p(p/(self.e0*(p/self.p0)**self.a))/(1-self.a)
        x=math.log(p)
        if x<=self.xtmax:return float(self.h_of_x(x))
        return float(self.hh[-1]+.5*math.log((self.emax-self.pmax+2*p)/(self.emax+self.pmax)))

    def continuous_cs2(self):
        ranges=[]
        for name,spline,left,right in [("BPS",self.bs,self.x0,self.xt),("MPA1",self.ms,self.xt,self.xtmax)]:
            cmin=math.inf;cmax=0.;checked=0
            for i,xi in enumerate(spline.x):
                if xi>=right:break
                dx=float(spline.x[i+1]-xi); c=spline.c[:,i]
                poly=Polynomial([float(c[3]),float(c[2]),float(c[1]),float(c[0])]);q=poly.deriv()
                pts=[0.,dx]
                for rt in ((Polynomial([1.])-q)*q-q.deriv()).roots():
                    if abs(rt.imag)<1e-9*max(1.,abs(rt.real)) and 0<rt.real<dx:
                        pts.append(float(rt.real))
                for z in pts:
                    x=float(xi+z)
                    if x<left-1e-12 or x>right+1e-12:continue
                    slope=float(q(z));cs=math.exp(x-float(poly(z)))/slope
                    if slope<=0:raise ValueError(f"{name} nonpositive dlogE/dlogP")
                    cmin=min(cmin,cs);cmax=max(cmax,cs);checked+=1
            ranges.append({"segment":name,"cs2_min":cmin,"cs2_max":cmax,"extrema_points_checked":checked})
        # Surface power-law c_s^2 rises monotonically to the BPS join value.
        pjoin=self.p0; ejoin=self.e0
        ccrust=float(pjoin/(self.a*ejoin))
        ranges.append({"segment":"surface_extension","cs2_min":0.,"cs2_max":ccrust,"slope_a":self.a})
        causal=all(x["cs2_min"]>=0 and x["cs2_max"]<=1 for x in ranges)
        return {"segments":ranges,"all_piecewise_segments_causal":causal,"causal_tail_cs2":1.}

def tov(eos,pc,method="rm",rtol=2e-9):
    hc=eos.h_at_p(pc); delta=min(1e-6,hc*1e-4); p_c,e_c=eos.state_h(hc)
    r0=math.sqrt(3*delta/(2*math.pi*(e_c+3*p_c))); m0=4*math.pi*e_c*r0**3/3
    if method=="rm":
        def f(h,y):
            r,m=y;p,e=eos.state_h(h);den=m+4*math.pi*r**3*p
            dr=-r*(r-2*m)/den;return [dr,4*math.pi*r*r*e*dr]
        y0=[r0,m0]
    else:
        def f(h,y):
            u,v=y;p,e=eos.state_h(h);den=v+4*math.pi*u*p
            return [-2*u*(1-2*v)/den,(v-4*math.pi*u*e)*(1-2*v)/den]
        y0=[r0*r0,m0/r0]
    sol=solve_ivp(f,(hc-delta,0.),y0,method="DOP853",rtol=rtol,atol=2e-11,max_step=.008)
    if not sol.success or sol.t[-1]!=0.:raise RuntimeError(sol.message)
    if method=="rm":r,m=sol.y[:,-1]
    else:u,v=sol.y[:,-1];r=math.sqrt(u);m=v*r
    return {"M_msun":float(m/MSUN_GEOM),"R_km":float(r/1000),"Pc_geom_m-2":pc,"Hc":hc,"method":method}

def sequence_max(eos,nscan,rtol):
    pcs=np.geomspace(eos.p0*1.01,eos.tailpcmax*.999,nscan)
    seq=[tov(eos,float(p),rtol=rtol) for p in pcs]
    masses=np.array([x["M_msun"] for x in seq]);j=int(np.argmax(masses))
    if j in (0,len(seq)-1):raise RuntimeError("TOV turning point not bracketed by pressure scan")
    lo,hi=math.log(pcs[j-1]),math.log(pcs[j+1])
    opt=minimize_scalar(lambda x:-tov(eos,math.exp(x),rtol=rtol)["M_msun"],bounds=(lo,hi),method="bounded",options={"xatol":1e-12})
    return tov(eos,math.exp(float(opt.x)),rtol=rtol),seq

def run():
    e=Hybrid()
    if not e.causality["all_piecewise_segments_causal"]:raise ValueError("continuous causality/stability failed")
    coarse,_=sequence_max(e,52,2e-8);fine,fine_seq=sequence_max(e,84,2e-10);uv=tov(e,fine["Pc_geom_m-2"],"uv",2e-10)
    source_end=tov(e,e.pmax,rtol=2e-10)
    post_pc=np.geomspace(e.pmax*1.000001,e.tailpcmax*.999,56)
    post_seq=[tov(e,float(pc),rtol=2e-10) for pc in post_pc]
    post_max=max(post_seq,key=lambda q:q["M_msun"])
    relm=abs(uv["M_msun"]/fine["M_msun"]-1);relr=abs(uv["R_km"]/fine["R_km"]-1)
    if max(relm,relr)>5e-5:raise ValueError("independent TOV formulations disagree")
    sample={"M_1p4":tov(e,find_pc_for_mass(e,1.4)),"M_2p073":tov(e,find_pc_for_mass(e,2.073))}
    return {"schema":"J0740_BPS_MPA1_MATCHED_TOV_V1","model":MODEL,
      "status":"PASS_NUMERICAL_HYBRID_EOS_CANDIDATE_PHYSICAL_ACCEPTANCE_NOT_ESTABLISHED",
      "source":{"jester_commit":"e6768650ce992abfd1153a6833857572fe5cd230","original_jester_mpa1_npz_sha256":MPA_NPZ_SHA,"bps_csv_sha256":sha(BPS_FILE),"mpa1_source_csv_sha256":sha(MPA_FILE),"original_sources_modified":False},
      "transition":{"selection":"highest-pressure zero of epsilon_BPS(P)-epsilon_LAL_MPA1(P) in common interval after the first native cs2<0 row; lower crossings retained as matching alternatives, not discarded evidence","crossing_count_in_stable_overlap":len(e.crossings),"crossing_pressures_geom_m-2":[float(math.exp(x)) for x in e.crossings],"selected_pressure_geom_m-2":e.pt,"selected_pressure_MeV_fm-3":e.pt/MEVFM3_GEOM,"epsilon_join_geom_m-2":e.eb,"energy_continuity_relative_residual":e.join_energy_rel,"absolute_baryon_density_surface_mu_MeV":MU0_MEV,"n_firstlaw_join_fm-3":e.n_join_firstlaw/1e45,"n_BPS_tabulated_at_join_fm-3":e.n_bps_at_join,"firstlaw_vs_BPS_n_relative_residual":e.n_join_rel,"mu_firstlaw_join_MeV":e.mu_join_mev,"mu_BPS_tabulated_join_MeV":e.mu_bps_mev,"source_MPA1_native_n_fm-3":e.n_mpa_at_join/1e45,"cs2_left_BPS":e.cs2_join_left,"cs2_right_MPA1":e.cs2_join_right,"cs2_jump_absolute":abs(e.cs2_join_right-e.cs2_join_left)},
      "surface_extension":{"type":"BPS-local-slope polytrope below the BPS knot whose tabulated mu=(e+p)/n is closest to the physical zero-pressure Fe anchor","BPS_start_row_zero_based":e.crust_start,"BPS_start_n_fm-3":float(e.bn[e.crust_start]),"BPS_start_p_geom_m-2":e.p0,"BPS_start_tabulated_mu_MeV":e.bps_anchor_mu_mev,"tabulated_mu_anchor_relative_residual":e.bps_anchor_mu_mev/MU0_MEV-1,"log_e_log_p_slope":e.a,"surface_mu0_MeV":MU0_MEV,"first_law_n":"n=(epsilon+P)/(mu0 exp(h)); h(0)=0"},
      "continuous_causality_and_stability":e.causality,
      "TOV":{"coarse_scan_52_rtol_2e-8_turning_point":coarse,"fine_scan_84_rtol_2e-10_turning_point":fine,"independent_uv_at_fine_turning_point":uv,"uv_relative_mass_difference":relm,"uv_relative_radius_difference":relr,"M1p4":sample["M_1p4"],"M2p073":sample["M_2p073"]},
      "source_table_endpoint_and_tail_audit":{"native_source_Pmax_geom_m-2":e.pmax,"native_source_enthalpy_max":float(e.hh[-1]),"M_R_at_source_table_endpoint":source_end,"source_table_endpoint_mass_minus_turning_point_msun":source_end["M_msun"]-fine["M_msun"],"post_source_tail_scan_count":len(post_seq),"post_source_tail_mass_max":post_max,"post_tail_max_minus_turning_point_msun":post_max["M_msun"]-fine["M_msun"],"turning_point_inside_native_source_pressure_range":bool(fine["Pc_geom_m-2"]<e.pmax),"causal_tail_controls_global_maximum":bool(post_max["M_msun"]>fine["M_msun"])},
      "high_density_completion":{"type":"cs2=1 causal-limit continuation above source MPA1 Pmax","explicit_new_model":True},
      "limits":{"original_MPA1_physical_Mmax":"NOT_ESTABLISHED; source table terminates without a demonstrated descending stable branch","hybrid_candidate_microphysical_acceptance":"NOT_ESTABLISHED","new_model_RNS":"NOT_RUN","source_native_XPSI_marginalization":"NOT_RUN","final_EOS_Bayes":"NOT_RUN"}}

def find_pc_for_mass(eos,target):
    # Use the stable branch and a bracketed root, never an extrapolated M-R curve.
    pcs=np.geomspace(eos.p0*1.01,eos.tailpcmax*.999,100)
    vals=[tov(eos,float(p))["M_msun"]-target for p in pcs]
    for i in range(len(pcs)-1):
        if vals[i]==0:return float(pcs[i])
        if vals[i]*vals[i+1]<0:
            root=brentq(lambda x:tov(eos,math.exp(x))["M_msun"]-target,math.log(pcs[i]),math.log(pcs[i+1]),xtol=1e-11)
            return math.exp(root)
    raise ValueError(f"mass {target} not bracketed on stable sequence")

if __name__=="__main__":
    out=run(); f=HERE/"JESTER_BPS_MPA1_matched_TOV_20261119.json"; f.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+"\n"); print(json.dumps(out,indent=2,sort_keys=True))


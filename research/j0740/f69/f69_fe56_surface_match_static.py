"""F69 conditional Fe-56 surface-matched, cold first-law EOS, and GR static baryon number.

NOT original MPA1 or a microphysically validated crust. Below a new, source-determined
matching pressure, replace the F67 low-P source data with a C1 monotone interpolant
that reaches a stipulated cold iron zero-pressure density and chemical potential.
Above the matching pressure F67 2425-row numerical table is unchanged; no X-PSI.

NIST: Fe-56 atomic mass 55.93493633 unified atomic mass units;
CODATA 2022: 1 u = 1.66053906892e-27 kg.
Potekhin et al. A&A 2013 ρ_surface=7.86 g/cm3 for cold Fe.
The physical boundary is CONDITIONAL, not a demonstrated stellar envelope.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq
from scipy.integrate import quad, solve_ivp

C=299792458.0;G=6.67430e-11;MSUN=1.988409870698051e30
MSUN_M=G*MSUN/C**2
AMU_KG=1.66053906892e-27
FE56_ATOMIC_U=55.93493633
FE56_BARYON_KG=FE56_ATOMIC_U/56.*AMU_KG
FE56_RHO_KG_M3=7.86e3
FE56_EGEO=FE56_RHO_KG_M3*G/C**2
PARENT_SHA='d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22'
LABEL='MPA1_PCHIP_COLD_FE56_SURFACE_V1_CONDITIONAL_NOT_ORIGINAL'
TARGETS=(2.073,2.175,2.200,2.250)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class ConditionallyFeMatched:
    def __init__(self, table):
        z=np.loadtxt(table)
        if sha(table)!=PARENT_SHA:raise ValueError('F69_PARENT_F67_SHA_DRIFT')
        if z.shape!=(2425,4) or not np.isfinite(z).all() or np.any(z[:,[0,1,3]]<=0) or np.any(z[:,2]<0) or np.any(np.diff(z,axis=0)<=0):
            raise ValueError('F69_BAD_F67_PARENT_TABLE')
        self.z=z
        self.lp=np.log(z[:,0]);self.le=np.log(z[:,1]);self.h=z[:,2]
        self.ep=PchipInterpolator(self.lp,self.le,extrapolate=False)
        self.hp=PchipInterpolator(self.lp,self.h,extrapolate=False)
        self.pinverse=PchipInterpolator(self.h,self.lp,extrapolate=False)
        self.p_parent0=float(z[0,0]);self.e_parent0=float(z[0,1]);self.rho_parent0=self.e_parent0*C*C/G
        self.rho_fe=FE56_RHO_KG_M3
        self.parent_Fe_surface_monotonicity_violation=bool(self.e_parent0<FE56_EGEO)
        # Choose first F67 tabulated node where boundary-corrected power-law index is
        # in the causal-at-surface class 0 < alpha < .95 and energy above Fe surface.
        candidates=[]
        for i in range(4,250):
            p,e=z[i,:2];s=float(self.ep(math.log(p),1))
            if e<=FE56_EGEO or s<=0:continue
            alpha=s*e/(e-FE56_EGEO)
            if 0.1<alpha<.95:candidates.append((i,alpha))
        if not candidates:raise ValueError('F69_NO_SURFACE_MATCH_C1_CAUSAL_POWER')
        self.index,self.alpha=candidates[0]
        self.pm=float(z[self.index,0]);self.em=float(z[self.index,1]);self.hm=float(z[self.index,2])
        self.em_diff=self.em-FE56_EGEO
        if not self.pm>self.p_parent0 or not self.em>FE56_EGEO:raise ValueError('F69_BAD_MATCH')
        self.houter=float(quad(lambda q: self.pm/(FE56_EGEO+self.em_diff*q**self.alpha+self.pm*q),0.,1.,epsabs=1e-19,epsrel=1e-10,limit=200)[0])
        self.surface_baryon_number_density_m3=FE56_RHO_KG_M3/FE56_BARYON_KG
        self.at_parent_pmin_baryon_density_m3=self.physical_n(self.p_parent0)

    def extension_e(self,p):
        p=float(p)
        if not 0<=p<=self.pm:raise ValueError('F69_OUTSIDE_EXTENSION')
        return FE56_EGEO+self.em_diff*(p/self.pm)**self.alpha
    def extension_dedp(self,p):
        if not 0<p<=self.pm:raise ValueError('F69_EXTENSION_DERIVATIVE_ENDPOINT')
        return self.alpha*self.em_diff/self.pm*(p/self.pm)**(self.alpha-1.)
    def extension_Habs(self,p):
        if p==0:return 0.
        if not 0<p<=self.pm:raise ValueError('F69_BAD_OUTER_P')
        x=p/self.pm
        return float(quad(lambda q:self.pm/(FE56_EGEO+self.em_diff*q**self.alpha+self.pm*q),0.,x,epsabs=1e-19,epsrel=1e-10,limit=200)[0])
    def e(self,p):
        if p<=self.pm:return self.extension_e(p)
        return math.exp(float(self.ep(math.log(p))))
    def Habs(self,p):
        if p<=self.pm:return self.extension_Habs(p)
        return self.houter+float(self.hp(math.log(p)))-self.hm
    def physical_n(self,p):
        # epsilon and p in geometric m^-2. n in physical number / m^3.
        return (self.e(p)+p)*C*C/G/FE56_BARYON_KG*math.exp(-self.Habs(p))
    def state_hparent(self,h):
        h=float(max(self.hm,min(float(self.h[-1]),h)))
        lp=float(self.pinverse(h))
        p=math.exp(lp);e=math.exp(float(self.ep(lp)))
        rho_b=(e+p)*(AMU_KG/FE56_BARYON_KG)*math.exp(-(self.houter+h-self.hm))
        return p,e,rho_b
    def first_law_relative_error(self,p):
        # 1st-law n=(epsilon+p)exp(-H)/mu0; check independent derivative by finite differences.
        d=2.0e-5
        p1=p*math.exp(-d);p2=p*math.exp(d)
        if p1<=self.pm:return float('nan')
        lhs=(math.log(self.physical_n(p2))-math.log(self.physical_n(p1)))/(2*d)
        lp=math.log(p)
        dloge=float(self.ep(lp,1))
        e=self.e(p)
        rhs=e/(e+p)*dloge  # dlnn/dlnp = (de/dlnp)/(e+p)
        return abs(lhs-rhs)/max(1.,abs(rhs))

def tov_to_match(c,hc,mode='rm',rtol=2.5e-9):
    """2 independent Einstein TOV forms with rest-baryon-number mass B integrated.
    Only reaches pressure pm; real Fe shell mass/radius bounded separately.
    """
    if mode not in ('rm','uv') or not .15<hc<.8:raise ValueError('F69_BAD_TOV_INPUT')
    p,e,rho_b=c.state_hparent(hc)
    dh=min(1e-6,hc*1e-4)
    r0=math.sqrt(3.*dh/(2*math.pi*(e+3*p)))
    m0=4*math.pi/3*e*r0**3
    b0=4*math.pi/3*rho_b*r0**3
    if mode=='rm':
        y0=[r0,m0,b0]
        def fun(h,y):
            r,m,b=y;pr,er,rhob=c.state_hparent(h)
            dr=-r*(r-2*m)/(m+4*math.pi*r**3*pr)
            return [dr,4*math.pi*r*r*er*dr,4*math.pi*r*r*rhob/math.sqrt(1-2*m/r)*dr]
    else:
        y0=[r0*r0,m0/r0,b0]
        def fun(h,y):
            u,v,b=y;pr,er,rhob=c.state_hparent(h)
            du=-2*u*(1-2*v)/(v+4*math.pi*u*pr)
            dv=(v-4*math.pi*u*er)*(1-2*v)/(v+4*math.pi*u*pr)
            r=math.sqrt(u);dr=du/(2*r)
            return [du,dv,4*math.pi*u*rhob/math.sqrt(1-2*v)*dr]
    sol=solve_ivp(fun,(hc-dh,c.hm),y0,method='DOP853',rtol=rtol,atol=2e-11,max_step=.009)
    if not sol.success or abs(sol.t[-1]-c.hm)>1e-11:raise RuntimeError('F69_TOV_FAILED '+sol.message)
    if mode=='rm':r,m,b=sol.y[:,-1]
    else:
        u,v,b=sol.y[:,-1];r=math.sqrt(u);m=v*r
    if not 0<2*m<r or not 7000<r<20000 or not 1<m/MSUN_M<3 or not b>m:
        raise ValueError('F69_UNPHYSICAL_TOV_RESULT')
    # TOV shell dr/dh is positive in the outward h decrease; bounding using e<=e_match.
    drdh=r*(r-2*m)/(m+4*math.pi*r**3*c.pm)
    delta_r=drdh*c.houter
    upper_dm=4*math.pi*(r+delta_r)**2*c.em*delta_r
    upper_db=4*math.pi*(r+delta_r)**2*(c.em+c.pm)*(AMU_KG/FE56_BARYON_KG)*delta_r/math.sqrt(1-2*m/r)
    return {'form':mode,'M_msun_to_match':m/MSUN_M,'R_km_to_match':r/1000,
            'Baryon_rest_mass_u_msun_to_match':b/MSUN_M,
            'binding_mass_u_minus_M_msun_to_match':(b-m)/MSUN_M,
            'shell_radius_linear_first_order_m':delta_r,
            'shell_gravitational_mass_conservative_first_order_estimate_msun':upper_dm/MSUN_M,
            'shell_baryonic_mass_conservative_first_order_estimate_msun':upper_db/MSUN_M,
            'center_enthalpy_relative_to_F67_pmin':hc}

def target(c,mass):
    def calc(h):return tov_to_match(c,h,'rm')['M_msun_to_match']-mass
    h=brentq(calc,.2,.60,xtol=4e-12)
    a=tov_to_match(c,h,'rm');b=tov_to_match(c,h,'uv')
    if abs(a['M_msun_to_match']-mass)>3e-7 or abs(a['R_km_to_match']-b['R_km_to_match'])>0.006 or abs(a['Baryon_rest_mass_u_msun_to_match']-b['Baryon_rest_mass_u_msun_to_match'])>.0005:
        raise ValueError('F69_INDEPENDENT_GR_BARYON_COUNT_DISAGREES')
    return {'rm':a,'uv':b,'independent_delta_R_m':(b['R_km_to_match']-a['R_km_to_match'])*1e3,
            'independent_delta_B_msun':b['Baryon_rest_mass_u_msun_to_match']-a['Baryon_rest_mass_u_msun_to_match']}

def write_conditional_eos(c,dst):
    """Export an explicit newly named EOS, including P=0, in physical n units."""
    dst=Path(dst);dst.parent.mkdir(parents=True,exist_ok=True)
    low=np.geomspace(c.pm*1e-12,c.pm,161)
    hi=c.z[c.index+1:,0]
    allp=np.r_[0.0,low,hi]
    with dst.open("w",encoding="ascii",newline="\n") as f:
        f.write("# MPA1_PCHIP_COLD_FE56_SURFACE_V1_CONDITIONAL_NOT_ORIGINAL\n")
        f.write("# p_geom_m-2 epsilon_geom_m-2 H_absolute n_baryon_m-3\n")
        for p in allp:
            f.write("%.16e %.16e %.16e %.16e\n"%(p,c.e(float(p)),c.Habs(float(p)),c.physical_n(float(p))))
    return dst

def run(table,out,eos_out=None):
    c=ConditionallyFeMatched(table)
    mismatch=(c.rho_parent0-c.rho_fe)/c.rho_fe
    if not c.parent_Fe_surface_monotonicity_violation or not -.03<mismatch<0:
        raise ValueError('F69_UNEXPECTED_PARENT_SURFACE_DENSITY_RELATION')
    for x in np.geomspace(c.pm*1e-12,c.pm,80):
        e=c.extension_e(x);d=c.extension_dedp(x)
        if not e>=FE56_EGEO or not d>1:raise ValueError('F69_BAD_SURFACE_EOS')
        if x!=c.pm and c.extension_Habs(x)<=0:raise ValueError('F69_NEGATIVE_FIRSTLAW_H')
    d_at_pm=float(c.ep(math.log(c.pm),1))*c.em/c.pm
    if abs(c.extension_dedp(c.pm)/d_at_pm-1)>2e-11:raise ValueError('F69_C1_DERIVATIVE_MISMATCH')
    # Cold identity test across new surface patch and unchanged upper PCHIP
    core_p=np.geomspace(c.pm*2.,1.0e-10,24)
    fl=max(c.first_law_relative_error(float(p)) for p in core_p)
    if fl>1e-5:raise ValueError('F69_FIRSTLAW_CORE_DERIVATIVE_FAIL')
    results={f'{m:.3f}':target(c,m) for m in TARGETS}
    for v in results.values():
        B=v['rm']['Baryon_rest_mass_u_msun_to_match']
        v['conditional_mu_surface_plus1pct_baryon_mass_msun']=B/1.01
        v['conditional_mu_surface_minus1pct_baryon_mass_msun']=B/.99
    limit=max(v['rm']['shell_radius_linear_first_order_m'] for v in results.values())
    if limit>=1e-6:raise ValueError('F69_LOW_P_SHELL_NONNEGLIGIBLE_NOT_SUPPORTED')
    report={'schema':'F69_CONDITIONAL_FE56_SURFACE_C1_FIRSTLAW_TOV_BARYON_v1',
      'model_label':LABEL,'parent_model':'MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL',
      'parent_F67_source_SHA256':sha(table),'original_MPA1_unmodified':True,
      'surface_assumption':'FE56_CRYSTAL_7.86_G_CM3_55.93493633_U_PER_ATOM_NOT_UNIQUE_MICROPHYSICS',
      'surface_Fe56_energy_per_baryon_MeV':FE56_BARYON_KG*C*C/1.602176634e-13,
      'surface_Fe56_density_g_cm3':FE56_RHO_KG_M3/1e3,
      'parent_F67_pmin_density_g_cm3':c.rho_parent0/1e3,
      'parent_minus_Fe56_density_fraction':mismatch,
      'Fe56_boundary_monotone_without_modifying_F67_source':'IMPOSSIBLE_E0_BELOW_FE56_SURFACE_DENSITY',
      'separately_modified_lowP_only_p_below_match':True,
      'match_index_in_F67_2425_row_grid':c.index,
      'match_p_geom_mminus2':c.pm,'match_energy_density_g_cm3':c.em*C*C/G/1e3,
      'match_alpha_C1':c.alpha,
      'C1_e_and_dedp_at_match':True,
      'surface_Habs':0.,'Habs_at_match':c.houter,
      'surface_baryon_number_density_mminus3':c.surface_baryon_number_density_m3,
      'at_original_F67_pmin_baryon_number_density_mminus3':c.at_parent_pmin_baryon_density_m3,
      'mu_Fe56_reference_NIST_CODATA_conditional':True,
      'baryon_mass_mu0_plus1pct_scaling':'Baryon rest mass / 1.01 at fixed epsilon(P), i.e. exactly degenerate with chosen surface mu0',
      'baryon_mass_mu0_minus1pct_scaling':'Baryon rest mass / 0.99 at fixed epsilon(P); illustrates unverified surface chemistry sensitivity',
      'n_absolute_conditional_not_original_MPA1':True,
      'rest_mass_per_baryon_convention':'atomic mass unit (u), not physical Fe56/56 mass',
      'first_law_core_derivative_max_relative_discretized':fl,
      'extension_positive_cs2_below_match':True,
      'target_static_GR':results,
      'maximum_first_order_missing_shell_radius_m':limit,
      'rotating_F68_uncertainty_not_recomputed':'NOT_RUN',
      'whole_original_seven_EOS_physically_accepted':'NOT_ESTABLISHED',
      'source_native_XPSI_photons':'NOT_RUN', 'seven_original_EOS_Bayes':'NOT_RUN',
      'unverified':['No independent crust microphysics table; Fe56 7.86g/cm3 surface is stipulated idealized boundary',
                    'C1 e(P) matching and cold first-law do not prove chemical or phase equilibrium at outer crust',
                    'F67 above match is numerical PCHIP interpolation, NOT original microphysical MPA1',
                    'Full GR RNS rotating F69 extension and baryon mass not recomputed; only STATIC Einstein TOV',
                    'First-order surface shell mass/radius is an estimate, not a mathematically rigorous upper bound',
                    'Finite precision integration and PCHIP inverse interpolation not independent observational evidence']}
    if eos_out is not None:
        path=write_conditional_eos(c,eos_out)
        report['new_conditionally_Fe56_matched_full_cold_table_name']=path.name
        report['new_conditionally_Fe56_matched_full_cold_table_sha256']=sha(path)
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'F69_CONDITIONAL_FE56_MATCH_COMPLETE_STATIC_GR_ONLY',
                      'monotonic_parent_impossible':True,'match_index':c.index,
                      'max_shell_m':limit,'mass2p073':results['2.073']['rm']},sort_keys=True))
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--table',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--eos-out',type=Path)
    a=p.parse_args();run(a.table,a.out,eos_out=a.eos_out)
if __name__=='__main__':main()

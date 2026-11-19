"""F67: separate MPA1_PCHIP_COLD_V1 exploratory EOS, never original MPA1.

Input: exact installed 7.26.4 source raw MPA1 .dat, SHA pinned from F66.
New alternate P(E) representation: PCHIP ln(P)->ln(epsilon), NOT LAL MPA1.
Cold first-law identity: h=integral dP/(epsilon+P), n(P)/n0 =
 (epsilon+P)/(epsilon0+P0)*exp(-h), with n0 unspecified.
Two independent formulations of nonrotating GR TOV, static only.
No claim that this is physically validated or original EOS, no RNS/XPSI.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
from scipy.integrate import cumulative_trapezoid, solve_ivp
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

SOURCE_SHA='bd1b0c1a0506f37649275bfe401cf985f78b31e7d5dc3023665c49b9e2d0c3ec'
JESTER_SHA='0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22'
EOS_LABEL='MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL'
MSUN_METERS=6.67430e-11*1.988409870698051e30/299792458.**2
F61_NATIVE_STATIC_2P073_R_KM=12.45154456013543


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_source(p,*,require_original=True):
    p=Path(p)
    if require_original and sha(p)!=SOURCE_SHA: raise ValueError('F67_RAW_MPA1_INSTALLED_7P26P4_SHA_DRIFT')
    tab=np.loadtxt(p,comments='#',dtype=np.float64)
    if tab.ndim!=2 or tab.shape[1]!=2 or tab.shape[0]!=102 or not np.isfinite(tab).all():
        raise ValueError('F67_INVALID_SOURCE_DIMENSIONS')
    if np.any(tab<=0) or np.any(np.diff(tab[:,0])<=0) or np.any(np.diff(tab[:,1])<=0):
        raise ValueError('F67_ORIGINAL_SOURCE_NOT_MONOTONE')
    return tab

class ColdEOS:
    def __init__(self,tab,*,subdivisions=12,quadrature=32):
        tab=np.asarray(tab,float)
        if tab.ndim!=2 or tab.shape[1]!=2 or len(tab)<20 or np.any(tab<=0) or not np.isfinite(tab).all() or np.any(np.diff(tab,axis=0)<=0):
            raise ValueError('F67_BAD_EOS_RAW')
        if subdivisions<5 or quadrature not in (24,32,48,64):raise ValueError('F67_BAD_NUMERIC_CONFIG')
        self.p0,self.pmax=float(tab[0,0]),float(tab[-1,0])
        self.e0=float(tab[0,1]);self.knots=len(tab)
        self.logp=np.log(tab[:,0]);self.loge=np.log(tab[:,1]);self.spline=PchipInterpolator(self.logp,self.loge,extrapolate=False)
        self.x=np.concatenate([np.linspace(x,y,subdivisions+1)[:-1] for x,y in zip(self.logp[:-1],self.logp[1:])]+[self.logp[-1:]])
        self.h=self._integrate_h(self.x,quadrature)
        if not np.all(np.diff(self.h)>0):raise ValueError('F67_NONMONOTONIC_ENTHALPY')
        self.inverse=PchipInterpolator(self.h,self.x,extrapolate=False)
        self.hmax=float(self.h[-1]);self.e0p0=self.e0+self.p0

    def _integrate_h(self,x,quadrature):
        xx,w=np.polynomial.legendre.leggauss(quadrature)
        lo=x[:-1,None];width=(x[1:]-x[:-1])[:,None]
        t=lo+width*(xx[None,:]+1)/2.
        e=np.exp(self.spline(t));p=np.exp(t)
        # dH/dlnP=P/(E+P), cold barotrope
        f=np.sum(w[None,:]*p/(e+p),axis=1)*width[:,0]/2.
        if not np.all(f>0):raise ValueError('F67_NEGATIVE_ENTHALPY_INTEGRAND')
        return np.r_[0.,np.cumsum(f)]

    def state_logp(self,x):
        y=self.spline(x);d=self.spline(x,1)
        p=np.exp(x);e=np.exp(y)
        cs2=p/(e*d)
        return p,e,cs2

    def state_h(self,h):
        h=float(np.clip(h,0.,self.hmax))
        x=float(self.inverse(h));p=float(np.exp(x));e=float(np.exp(self.spline(x)))
        return p,e

    def n_ratio(self,x,h=None):
        # Normalized at pmin to n0=1; n0 IS NOT a physical baryon density.
        x=np.asarray(x,float)
        if h is None:h=self.inverse_enthalpy_from_logp(x)
        e=np.exp(self.spline(x));p=np.exp(x)
        return (e+p)/self.e0p0*np.exp(-h)

    def inverse_enthalpy_from_logp(self,x):
        # Dense grid PCHIP approximation of the same Gauss integrated h(P)
        forward=PchipInterpolator(self.x,self.h,extrapolate=False)
        return forward(x)

    def sound_speed_screen(self,pc,*,per_knot=20):
        if not self.p0<pc<self.pmax:raise ValueError('F67_CENTER_OUTSIDE_SOURCE')
        x=np.concatenate([np.linspace(a,b,per_knot,endpoint=False) for a,b in zip(self.logp[:-1],self.logp[1:])]+[self.logp[-1:]])
        x=x[x<=math.log(pc)]
        x=np.r_[x,math.log(pc)]
        p,e,cs=self.state_logp(x)
        if not np.all(np.isfinite(cs)):raise ValueError('F67_NONFINITE_SOUND_SPEED')
        return {'sample_count':len(cs),'sampled_cs2_min':float(cs.min()),'sampled_cs2_max':float(cs.max()),
            'sampled_cs2_nonpositive_count':int(np.count_nonzero(cs<=0)),
            'sampled_cs2_superluminal_count':int(np.count_nonzero(cs>1)),
            'sampled_entire_star_eos_causal':bool((cs>0).all() and (cs<=1).all()),
            'continuous_causality_proof':'NOT_ESTABLISHED'}


def tov(eos,pc,*,rel_tol=3e-9,method='rm'):
    if not eos.p0*1.0001<pc<eos.pmax: raise ValueError('F67_INVALID_TOV_CENTER')
    x=math.log(pc)
    hc=float(eos.inverse_enthalpy_from_logp(x))
    pc,ec=eos.state_h(hc)
    delta=min(1e-6,hc*1e-4)
    r0=math.sqrt(3*delta/(2*math.pi*(ec+3*pc)))
    m0=4*math.pi/3*ec*r0**3
    if not 2*m0<r0:raise ValueError('F67_BAD_TOV_CENTER')
    if method=='rm':
        def fun(h,y):
            r,m=y;p,e=eos.state_h(h)
            denom=m+4*math.pi*r**3*p
            dr=-r*(r-2*m)/denom
            return [dr,4*math.pi*r*r*e*dr]
        y0=[r0,m0]
    elif method=='uv':
        def fun(h,y):
            u,v=y;p,e=eos.state_h(h)
            denom=v+4*math.pi*u*p
            du=-2*u*(1-2*v)/denom
            dv=(v-4*math.pi*u*e)*(1-2*v)/denom
            return [du,dv]
        y0=[r0*r0,m0/r0]
    else:raise ValueError('F67_UNKNOWN_TOV_METHOD')
    sol=solve_ivp(fun,(hc-delta,0),y0,method='DOP853',rtol=rel_tol,atol=2e-11,max_step=.012)
    if not sol.success or sol.t[-1]!=0:raise RuntimeError('F67_TOV_INTEGRATION_FAIL '+str(sol.message))
    if method=='uv':
        u,v=sol.y[:,-1];r=math.sqrt(u);m=v*r
    else:r,m=sol.y[:,-1]
    if not 0<2*m<r or not 7000<r<25000 or not 1<m/MSUN_METERS<4:
        raise ValueError('F67_NONPHYSICAL_TOV_ROOT')
    return {'M_msun':float(m/MSUN_METERS),'R_km':float(r/1000),'central_pressure_geom':float(pc),
      'central_enthalpy_from_source_min':float(hc),'integrator':method,'source_min_pressure_surface_not_zero':'APPROXIMATE'}


def root_at_mass(eos,target=2.073,*,nscan=15,method='rm'):
    # Search ascending branch around the independently known F61 original central P
    centers=np.geomspace(3.0e-11,5.1e-10,nscan)
    pts=[]
    for p in centers:
        try: pts.append((float(p),tov(eos,float(p),method=method)))
        except (RuntimeError,ValueError):continue
    for (pa,a),(pb,b) in zip(pts[:-1],pts[1:]):
        if a['M_msun']<target<b['M_msun']:
            calls=[]
            def fn(logp):
                o=tov(eos,math.exp(logp),method=method);calls.append(o['M_msun']);return o['M_msun']-target
            pc=math.exp(brentq(fn,math.log(pa),math.log(pb),xtol=3e-11))
            o=tov(eos,pc,method=method)
            if abs(o['M_msun']-target)>2e-6:raise ValueError('F67_MASS_ROOT_RESIDUAL')
            return dict(o,root_calls=len(calls),root_mass_residual=o['M_msun']-target,bracket=[pa,pb],sampled_scan_stars=len(pts))
    raise ValueError('F67_TARGET_MASS_NO_ASCENDING_BRANCH_ROOT')


def run(path,*,out,eos_out=None,rel_tol=3e-9):
    raw=load_source(path)
    coarse=ColdEOS(raw,subdivisions=12,quadrature=32)
    fine=ColdEOS(raw,subdivisions=24,quadrature=48)
    p_native=2.1122773348832598e-10
    coarse_approx=tov(coarse,p_native,rel_tol=rel_tol)
    fine_approx=tov(fine,p_native,rel_tol=rel_tol)
    root=root_at_mass(fine)
    independent=tov(fine,root['central_pressure_geom'],method='uv',rel_tol=rel_tol)
    screen=fine.sound_speed_screen(root['central_pressure_geom'])
    # Exact algebraic chemical-potential relation and numerical dH/dlnP integration test
    mids=(fine.x[2:-2:9]);H=fine.inverse_enthalpy_from_logp(mids)
    e=np.exp(fine.spline(mids));p=np.exp(mids)
    n=fine.n_ratio(mids,H)
    chem=((e+p)/(fine.e0p0*n))
    err=float(np.max(np.abs(chem/np.exp(H)-1)))
    if err>1e-11:raise ValueError('F67_FIRSTLAW_MU_OVER_MU0_IDENTITY_FAILED')
    comparison={'mass_relative':abs(independent['M_msun']-root['M_msun'])/root['M_msun'],
                'radius_relative':abs(independent['R_km']-root['R_km'])/root['R_km'],
                'coarse_fine_R_at_same_pc_km':fine_approx['R_km']-coarse_approx['R_km'],
                'coarse_fine_M_at_same_pc_msun':fine_approx['M_msun']-coarse_approx['M_msun']}
    if comparison['mass_relative']>3e-4 or comparison['radius_relative']>3e-4:
        raise ValueError('F67_INDEPENDENT_TOV_FORMULATIONS_DO_NOT_AGREE')
    d={'schema':'F67_MPA1_PCHIP_COLD_FIRSTLAW_STATIC_TOV_V1','model_label':EOS_LABEL,
       'science_status':'NEW_SEPARATELY_NAMED_ALTERNATIVE_NUMERIC_EOS_STATIC_TOV_ONLY',
       'not_original_MPA1':True,'not_F42_causal_lift':True,'installed_original_MPA1_raw_source_sha256':sha(path),
       'original_JESTER_MPA1_npz_sha256':JESTER_SHA,
       'original_LAL_F61_2p073_static_R_km':F61_NATIVE_STATIC_2P073_R_KM,
       'source_raw_rows':len(raw),'firstlaw_n0':'ARBITRARY_REFERENCE_NOT_PHYSICAL_MU0_OR_M0',
       'n_from_exact_cold_chemical_identity_max_relative':err,
       'cold_enthalpy_offset_at_source_min':'H(pmin)=0; physical surface h0 NOT independently established',
       'fixed_native_center_pc_control':{'original_LAL_central_pc':p_native,'coarse':coarse_approx,'fine':fine_approx},
       'new_M2p073_PCHIP_root':root,'independent_u_v_at_same_root':independent,'numerical_comparison':comparison,
       'sampled_sound_speed_in_star':screen,
       'physically_admissible_full_EOS':'NOT_ESTABLISHED',
       'rotating_RNS_equilibria_on_alternative':'NOT_RUN',
       'native_photon_XPSI_likelihood':'NOT_RUN','seven_original_EOS_Bayes':'NOT_RUN',
       'limitations':['PCHIP is NEW mathematical EOS representation NOT original LAL MPA1 or verified microscopic nuclear model',
         'Sampled c_s2 over model; not analytic global bounded continuous verification',
         'Thermo n0 chemical-potential normalization remains arbitrary',
         'No independent crust transition composition, baryon µ0, or high-density sound speed guarantee',
         'Static TOV not 346.536369Hz rotating GR; exact source-native X-PSI and 7 original nuclear EOS evidences remain NOT_RUN']}
    if eos_out is not None:
        target=Path(eos_out);target.parent.mkdir(parents=True,exist_ok=True)
        # Distinct numerical model: p,epsilon in geometric m^-2, H dimensionless, n/n0 arbitrary.
        with target.open('w') as f:
            f.write('# MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL\n')
            f.write('# p_geom_m^-2 epsilon_geom_m^-2 H_relative n_over_n0_ARBITRARY\n')
            for q,h in zip(fine.x,fine.h):
                ee=math.exp(float(fine.spline(q)));pp=math.exp(float(q))
                nn=(ee+pp)/fine.e0p0*math.exp(-float(h))
                f.write(f'{pp:.16e} {ee:.16e} {h:.16e} {nn:.16e}\n')
        d['alternate_firstlaw_table_path']=str(target)
        d['alternate_firstlaw_table_sha256']=sha(target)
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':d['science_status'],'root':root,'independent_comparison':comparison,
       'sampled_cs2':screen},sort_keys=True),flush=True)
    return d


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--eos-out',type=Path)
    a=p.parse_args()
    run(a.source,out=a.out,eos_out=a.eos_out)

if __name__=='__main__':main()
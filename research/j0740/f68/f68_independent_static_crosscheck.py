"""Independent static Einstein TOV check using the precomputed F67 alternative H(P) table.

These stars are STATIC and their PCHIP EOS is an exploratory interpolation,
NOT original nuclear MPA1 or a verified physical crust / XPSI evidence.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

SRC_SHA='d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22'
F67_R_STATIC_KM=12.40615558120446
MSUN_M=6.67430e-11*1.988409870698051e30/299792458.**2
TARGETS=(2.073,2.175,2.200,2.250)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def eos_lookup(path):
    if sha(path)!=SRC_SHA:raise ValueError('F68_PARENT_SHA_DRIFT')
    x=np.loadtxt(path)
    if x.shape!=(2425,4) or (np.diff(x[:,2])<=0).any():raise ValueError('F68_PARENT_TABLE_DRIFT')
    return PchipInterpolator(x[:,2],np.log(x[:,0])),PchipInterpolator(x[:,2],np.log(x[:,1]))

def integrate_tov(pc_of_h,ec_of_h,hc,*,method):
    if not .1<hc<.9 or method not in ('rm','uv'):raise ValueError('F68_INVALID_TOV_INPUT')
    e=math.exp(float(ec_of_h(hc)));p=math.exp(float(pc_of_h(hc)))
    dh=min(1e-6,hc*1e-4)
    r0=math.sqrt(3*dh/(2*math.pi*(e+3*p)))
    m0=4*math.pi/3*e*r0**3
    if method=='rm':
        def f(h,y):
            r,m=y;pr=math.exp(float(pc_of_h(max(0,h))));er=math.exp(float(ec_of_h(max(0,h))))
            dr=-r*(r-2*m)/(m+4*math.pi*r**3*pr)
            return [dr,4*math.pi*r*r*er*dr]
        y0=[r0,m0]
    else:
        def f(h,y):
            u,v=y;pr=math.exp(float(pc_of_h(max(0,h))));er=math.exp(float(ec_of_h(max(0,h))))
            denom=v+4*math.pi*u*pr
            return [-2*u*(1-2*v)/denom,(v-4*math.pi*u*er)*(1-2*v)/denom]
        y0=[r0*r0,m0/r0]
    ans=solve_ivp(f,(hc-dh,0),y0,method='DOP853',rtol=2e-9,atol=2e-11,max_step=.008)
    if not ans.success or abs(float(ans.t[-1]))>1e-12:raise RuntimeError('F68_TOV_SOLVER_DID_NOT_CONVERGE')
    a,b=ans.y[:,-1]
    if method=='rm':r,m=a,b
    else:r,m=math.sqrt(a),math.sqrt(a)*b
    if not 0.1<m/MSUN_M<4 or not 4<r/1000<30:raise ValueError('F68_TOV_UNPHYSICAL')
    return {'mass_msun':float(m/MSUN_M),'radius_km':float(r/1000),'central_enthalpy_h':float(hc),'method':method}

def run(source,out):
    p,e=eos_lookup(source)
    records={}
    for mass in TARGETS:
        hc=brentq(lambda h: integrate_tov(p,e,h,method='rm')['mass_msun']-mass,.20,.55,xtol=1e-11)
        a=integrate_tov(p,e,hc,method='rm');b=integrate_tov(p,e,hc,method='uv')
        dr=abs(a['radius_km']-b['radius_km']);dm=abs(a['mass_msun']-b['mass_msun'])
        if abs(a['mass_msun']-mass)>5e-5 or dr>0.008 or dm>.0003:raise ValueError('F68_TWO_STATIC_SOLVERS_DISAGREE')
        records[f'{mass:.3f}']={'rm':a,'uv':b,'independent_radius_difference_m':1000*dr,'independent_mass_difference_msun':dm}
    if abs(records['2.073']['rm']['radius_km']-F67_R_STATIC_KM)>.005:
        raise ValueError('F68_INDEPENDENT_F67_PREVIOUS_STATIC_NOT_REPRODUCED')
    summary={'schema':'F68_INDEPENDENT_F67_ALTERNATE_FOUR_MASS_STATIC_TOV_DIAGNOSTIC',
            'status':'TWO_INDEPENDENT_STATIC_TOV_FORMULATIONS_PASS_NOT_ROTATING',
            'F67_model':'MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL','original_F67_thermo_SHA256':sha(source),
            'target_masses_msun':list(TARGETS),'source_native_XPSI':'NOT_RUN','full_physical_EOS':'NOT_ESTABLISHED',
            'zero_pressure_surface':'NOT_ESTABLISHED',
            'warning':'This crosscheck is STATIC only and cannot substitute for real rotating RNS C.',
            'stars':records}
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    return summary
if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('f67_table',type=Path);cli.add_argument('out',type=Path)
    args=cli.parse_args();s=run(args.f67_table,args.out)
    for k,v in s['stars'].items():print(k,'M',v['rm']['mass_msun'],'R',v['rm']['radius_km'],'dr_m',v['independent_radius_difference_m'])

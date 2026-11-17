from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, sys
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

ROOT=Path(__file__).parent
TABLE=ROOT/'LALSimNeutronStarEOS_APR4_EPP_7.26.4.dat'
NPZ=Path(r'C:\Users\User\Documents\Codex\2026-11-06\n\work\sources\eos_npz\APR4_EPP.npz')
spec=importlib.util.spec_from_file_location('native_apr4',ROOT/'native_lalsuite_apr4_causal_model.py')
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)

def require(ok,msg):
    if not ok:raise AssertionError(msg)

def independent_pressure_tov(eos,pc,rtol=2e-10):
    L=10000.0;ec=eos.energy(pc);r0=1.0
    pstart=pc-2*math.pi*(ec+pc)*(ec/3+pc)*r0*r0
    mstart=4*math.pi*ec*r0**3/3
    y0=[r0/L,mstart/L,pstart/pc]
    def rhs(x,y):
        u=y[1];q=y[2];p=max(pc*q,pc*1e-300);e=eos.energy(p)
        den=x*(x-2*u)
        if den<=0:raise RuntimeError('TOV horizon reached')
        return [1.0,4*math.pi*L*L*x*x*e,-(e+p)/pc*(u+4*math.pi*L*L*x**3*p)/den]
    def surface(x,y):return y[2]
    surface.terminal=True;surface.direction=-1
    sol=solve_ivp(rhs,(r0/L,1000.),y0,method='DOP853',rtol=rtol,atol=[1e-12,1e-12,1e-12],events=surface,max_step=.02)
    require(sol.success and len(sol.t_events[0])==1,'independent pressure-coordinate TOV failed')
    R=sol.t_events[0][0]*L;M=sol.y_events[0][0,1]*L
    return M*mod.C**2/mod.G/mod.MSUN,R/1000,len(sol.t)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--table',type=Path,default=TABLE);ap.add_argument('--npz',type=Path,default=NPZ);ap.add_argument('--result',type=Path,default=ROOT/'APR4_native_LAL_causal_completion_TOV.json');a=ap.parse_args()
    require(mod.sha256(a.table)==mod.LAL_TABLE_SHA,'native table SHA mismatch')
    require(mod.sha256(a.npz)==mod.NPZ_SHA,'JESTER export SHA mismatch')
    report=json.loads(a.result.read_text(encoding='utf-8'))
    eos=mod.NativeAPR4CausalEOS(a.table)
    export=mod.reproduce_jester_export(a.table,a.npz)
    require(export['e_rel_max']<1e-11 and export['dloge_abs_max']<1e-10 and export['native_h_rel_max']<1e-10,'native API output reproduction failed')
    ext,ming,maxg=eos.interval_extrema();require(ming>0,'continuous thermodynamic stability failed')
    require(max(v for v,_ in ext)>1,'original native EOS is not globally causal, contradiction')
    require(abs(eos.cs2_native(eos.pcut)-1)<5e-10,'continuous causal cutoff failed')
    require(report['continuous_firstlaw_n_shape_max_abs_derivative_residual']<5e-6,'first-law density-shape residual too large')
    conv=report['tov_convergence'];fine=conv[-1]['turning_point'];mid=conv[-2]['turning_point']
    dm=abs(fine['M_msun']-mid['M_msun']);dr=abs(fine['R_km']-mid['R_km'])
    require(dm<1e-6 and dr<1e-3,'central-pressure resolution convergence failed')
    pc=float(fine['pc_geom_m-2']);M_h=float(fine['M_msun']);R_h=float(fine['R_km'])
    ml=eos.pcut*.03;lo=brentq(lambda lp:mod.tov(eos,math.exp(lp))['M_msun']-2.073,math.log(ml),math.log(pc))
    at2073=mod.tov(eos,math.exp(lo))
    with np.load(a.npz,allow_pickle=False) as z:
        lal_m=np.asarray(z['masses_EOS'],float);lal_r=np.asarray(z['radii_EOS'],float)
    crossings=np.where((lal_m[:-1]<2.073)&(lal_m[1:]>=2.073))[0]
    require(len(crossings)==1,'source LAL M-R has no unique 2.073-solar-mass crossing')
    ic=int(crossings[0]);require(np.all(np.diff(lal_m[ic-4:ic+5])>0),'source LAL branch is not locally stable at target')
    frac=(2.073-lal_m[ic])/(lal_m[ic+1]-lal_m[ic])
    lal_r2073=float(lal_r[ic]+frac*(lal_r[ic+1]-lal_r[ic]));delta_lal=float(at2073['R_km']-lal_r2073)
    require(abs(delta_lal)<0.002,f'independent LAL static M-R reference mismatch {delta_lal} km')
    # Confirm mass rises before and falls after the first turning point.
    require(mod.tov(eos,pc*.99)['M_msun']<M_h and mod.tov(eos,pc*1.01)['M_msun']<M_h,'turning point is not a local maximum')
    result={'status':'PASS_NATIVE_LAL_TABLE_REPRODUCTION_AND_CONDITIONAL_TOV; PHYSICAL_MU0_NOT_ESTABLISHED',
      'jester_npz_sha256':mod.sha256(a.npz),'native_lal_table_sha256':mod.sha256(a.table),
      'jester_export_max_relative_e_error':export['e_rel_max'],'jester_export_max_abs_dloge_error':export['dloge_abs_max'],
      'jester_export_max_relative_native_h_error':export['native_h_rel_max'],
      'continuous_native_min_dloge_dlogp':float(ming),'continuous_native_max_cs2':max(v for v,_ in ext),
      'first_continuous_causal_cut_p_geom_m-2':eos.pcut,
      'conditional_causal_completion_turning_point_M_msun':M_h,'conditional_causal_completion_turning_point_R_km':R_h,
      'turning_point_pc_geom_m-2':pc,'pressure_grid_delta_M_61_vs_121_msun':dm,'pressure_grid_delta_R_61_vs_121_km':dr,
      'conditional_stable_branch_at_M_2p073_Msun':at2073,
      'independent_JESTER_LAL_static_MR_reference_radius_at_2p073_Msun_km':lal_r2073,
      'independent_TOV_minus_native_LAL_radius_at_2p073_Msun_km':delta_lal,
      'firstlaw_n_shape_max_abs_derivative_residual':report['continuous_firstlaw_n_shape_max_abs_derivative_residual'],
      'native_n_vs_JESTER_e_over_mavg_ratio_at_first_and_last':[
         export['jester_n_proxy_to_native_firstlaw_ratio_first'],export['jester_n_proxy_to_native_firstlaw_ratio_last']],
      'absolute_physical_baryon_normalization':'NOT_ESTABLISHED: two-column native table does not provide physical zero-pressure chemical potential mu0; m_avg is only the JESTER conversion convention.',
      'physical_MTOV':'NOT_ESTABLISHED: turning point applies to new cs2=1 completion conditional on mu0 convention.',
      'rotating_GR_for_new_full_crust_model':'NOT_RUN','source_native_likelihood_and_final_EOS_Bayes':'NOT_RUN'}
    (ROOT/'APR4_native_LAL_causal_candidate_test_results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=='__main__':main()


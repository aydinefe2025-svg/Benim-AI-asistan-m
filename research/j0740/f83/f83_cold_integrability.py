#!/usr/bin/env python3
"""F83: Source-pinned first-law integrability of the F80/F82 hybrid RNS EOS.

Original P, epsilon nodes are retained byte-for-byte, but the resulting new
RNS table uses the EXPLICIT, SEPARATELY NAMED piecewise-linear epsilon(P)
interpolant and exact dh=dP/(epsilon+P) integral. n_b is then generated from
mu0 exp(h)=(epsilon+P)/n_b. This is not original microphysics, a global
phase-equilibrium solution, or a stellar-stability certificate.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np

EOS_SHA = 'f4a183661962acdddc7aebde3830116578feb6fba88a1a68c9fd57a993058675'
C = 2.99792458e10
MEV_TO_ERG = 1.602176634e-6
N = 1213
REL = 1e-8
ABS = 5e-15
SCHEMA='F83_REAL_F80_RNS_P_E_H_FIRSTLAW_PIECEWISE_CAUSAL_RECONSTRUCTION_V1'


def sha(data: bytes | Path) -> str:
    if isinstance(data,Path):data=data.read_bytes()
    return hashlib.sha256(data).hexdigest()


def locked_source(path:Path) -> tuple[bytes,np.ndarray,list[list[str]]]:
    raw=Path(path).read_bytes()
    # Historical GitHub text transport has appended *one* terminal empty CRLF.
    # Only undo that known transport if exact previous source digest restored.
    if sha(raw)!=EOS_SHA:
        if not (raw.endswith(b'\n\r\n') and sha(raw[:-2])==EOS_SHA):
            raise ValueError('F83_ORIGINAL_EOS_SHA_DRIFT')
        raw=raw[:-2]
    lines=raw.decode('ascii').splitlines()
    if lines[0] != str(N) or len(lines) != N+1:
        raise ValueError('F83_ORIGINAL_EOS_NUMBER_OF_SOURCE_ROWS_CHANGED')
    tokens=[line.split() for line in lines[1:]]
    if any(len(row)!=4 for row in tokens):raise ValueError('F83_ORIGINAL_EOS_FOUR_COLUMNS_REQUIRED')
    arr=np.array(tokens,dtype=float)
    if arr.shape!=(N,4):raise ValueError('F83_BAD_ORIGINAL_SHAPE')
    return raw,arr,tokens


def h_bounds(E:np.ndarray,P:np.ndarray)->tuple[np.ndarray,np.ndarray,np.ndarray,np.ndarray]:
    dp=np.diff(P);de=np.diff(E)
    if np.any(~np.isfinite(E)) or np.any(~np.isfinite(P)) or np.any(E<=0) or np.any(P<=0) or np.any(dp<=0) or np.any(de<=0):
        raise ValueError('F83_P_E_MONOTONICITY_OR_POSITIVITY')
    if np.any(de<dp*(1-2e-12)):
        raise ValueError('F83_P_E_SUPERLUMINAL_ORIGINAL_SECANT')
    lower=.5*np.log1p(2*dp/(E[1:]+P[:-1]-dp))
    upper=.5*np.log1p(2*dp/(E[:-1]+P[:-1]))
    mon_lower=np.log1p(dp/(E[1:]+P[:-1]))
    mon_upper=np.log1p(dp/(E[:-1]+P[:-1]))
    return lower,upper,mon_lower,mon_upper


def failures(dh:np.ndarray,lo:np.ndarray,hi:np.ndarray)->np.ndarray:
    return np.where((dh<lo-ABS-REL*np.abs(lo)) | (dh>hi+ABS+REL*np.abs(hi)))[0]


def audit_and_rebuild(arr:np.ndarray)->tuple[np.ndarray,dict]:
    src=np.asarray(arr,dtype=float)
    if src.ndim!=2 or src.shape[1]!=4 or len(src)<3 or not np.isfinite(src).all() or np.any(src<=0):
        raise ValueError('F83_INVALID_FOUR_COLUMN_SOURCE')
    E=src[:,0]*C**2; P=src[:,1]; H=src[:,2]/C**2; n=src[:,3]
    if not (np.diff(H)>0).all() or not (np.diff(n)>0).all():
        raise ValueError('F83_NONMONOTONE_H_OR_N_SOURCE')
    lo,hi,ml,mh=h_bounds(E,P)
    bad_h=failures(np.diff(H),lo,hi)
    bad_m=failures(np.diff(H),ml,mh)
    # A native row-by-row chemical-potential identity is NOT enough to ensure
    # source H(P) is integrable with source E(P); audit both independently.
    mu=(E+P)/n/MEV_TO_ERG
    mu0=mu*np.exp(-H)
    if np.max(abs(mu0/mu0[0]-1))>1e-10:
        raise ValueError('F83_SOURCE_ROW_MU0_IDENTITY_DRIFT')
    dE=np.diff(E); dP=np.diff(P)
    s=dE/dP                  # constant dE/dP >=1 in each OPEN interval
    dh=np.log1p((1+s)*dP/(E[:-1]+P[:-1]))/(1+s)
    newH=np.empty(len(H));newH[0]=H[0]
    newH[1:]=H[0]+np.cumsum(dh)
    # E=epsilon(P) piecewise linear preserves both exact input endpoint columns.
    newn=(E+P)/(mu0[0]*MEV_TO_ERG*np.exp(newH))
    new=np.column_stack([src[:,0],src[:,1],newH*C**2,newn])
    new_lo,new_hi,new_ml,new_mh=h_bounds(E,P)
    if failures(np.diff(newH),new_lo,new_hi).size or failures(np.diff(newH),new_ml,new_mh).size:
        raise ValueError('F83_REBUILT_ANALYTIC_COLD_FIRSTLAW_FAILED')
    if np.any(np.diff(newn)<=0) or not np.isfinite(new).all():
        raise ValueError('F83_REBUILT_N_NONMONOTONE')
    if np.max(abs(((E+P)/newn/MEV_TO_ERG)*np.exp(-newH)/mu0[0]-1))>3e-13:
        raise ValueError('F83_COLD_MU_IDENTITY_FAILED')
    if not np.array_equal(src[:,:2],new[:,:2]):
        raise ValueError('F83_CHANGED_P_OR_E')
    out={'schema':SCHEMA,'old_n_eos_points':len(src),'old_source_pressure_energy_byte_locked':True,
         'original_num_causal_enthalpy_interval_failures':int(len(bad_h)),
         'original_num_monotone_enthalpy_interval_failures':int(len(bad_m)),
         'original_causal_bad_interval_indices_zero_based':[int(i) for i in bad_h],
         'original_monotone_bad_interval_indices_zero_based':[int(i) for i in bad_m],
         'new_causal_bad_intervals':int(len(failures(np.diff(newH),new_lo,new_hi))),
         'new_monotone_bad_intervals':int(len(failures(np.diff(newH),new_ml,new_mh))),
         'piecewise_causal_secant_min':float(np.min(dP/dE)),
         'piecewise_causal_secant_max':float(np.max(dP/dE)),
         'max_absolute_h_change':float(np.max(np.abs(newH-H))),
         'max_relative_n_change':float(np.max(np.abs(newn/n-1))),
         'terminal_h_change':float(newH[-1]-H[-1]),
         'mu0_surface_anchor_MeV':float(mu0[0]),
         'cold_first_law_analytically_exact_on_open_piecewise_linear_intervals':True,
         'new_E_of_P_C1_differentiability_at_knots':'NOT_ESTABLISHED_PIECEWISE_DERIVATIVE_JUMPS',
         'actual_RNS_solver_interpolation_physical_validity':'NOT_ESTABLISHED',
         'BPS_core_Gibbs_phase_and_microphysics':'NOT_ESTABLISHED',
         'global_constant_J_and_mode_stability':'NOT_ESTABLISHED_FOR_NEW_EOS',
         'original_Salmi_photon_likelihood':'NOT_RUN',
         'seven_source_original_EOS_Bayes':'NOT_RUN'}
    return new,out


def main():
    pa=argparse.ArgumentParser();pa.add_argument('--source',type=Path,required=True)
    pa.add_argument('--out-eos',type=Path,required=True)
    pa.add_argument('--out-json',type=Path,required=True)
    a=pa.parse_args()
    orig,rows,tokens=locked_source(a.source)
    new,report=audit_and_rebuild(rows)
    if len(rows)!=N or report['original_num_causal_enthalpy_interval_failures']!=11 or report['original_num_monotone_enthalpy_interval_failures']!=8:
        raise ValueError('F83_EXPECTED_REAL_SOURCE_INTERVAL_COUNTS_CHANGED')
    newlines=[tokens[i][0]+' '+tokens[i][1]+' '+f'{new[i,2]:.15e} '+f'{new[i,3]:.15e}' for i in range(len(rows))]
    result=(str(N)+'\n'+'\n'.join(newlines)+'\n').encode('ascii')
    a.out_eos.parent.mkdir(parents=True,exist_ok=True)
    a.out_eos.write_bytes(result)
    chk=np.loadtxt(a.out_eos,skiprows=1)
    if chk.shape!=(N,4) or np.any(chk<=0) or not np.array_equal(chk[:,:2],rows[:,:2]):
        raise ValueError('F83_OUTPUT_RNS_E_OR_P_CHANGED')
    _,check=audit_and_rebuild(chk)
    if check['original_num_causal_enthalpy_interval_failures']!=0 or check['original_num_monotone_enthalpy_interval_failures']!=0:
        raise ValueError('F83_SERIALIZED_COLD_ENTHALPY_PHYSICAL_FAILURE')
    report.update({'original_EOS_sha256':sha(orig),'new_piecewise_cold_RNS_EOS_sha256':sha(result),
       'output_EOS_bytes':len(result),'source_EOS_bytes':len(orig),
       'real_original_source_native_N_P_E_H_test':'PASS_REAL_SOURCE_11_VIOLATIONS_CORRECTED_TO_ZERO',
       'status':'PIECEWISE_CAUSAL_FIRSTLAW_SOURCE_REBUILD_ACCEPTED_NUMERICALLY_NOT_MICROPHYSICS'})
    a.out_json.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'source':report['original_EOS_sha256'],'new':report['new_piecewise_cold_RNS_EOS_sha256'],
       'old_bad':report['original_num_causal_enthalpy_interval_failures'],
       'after_bad':report['new_causal_bad_intervals'],
       'max_abs_h_shift':report['max_absolute_h_change'],
       'max_relative_n_shift':report['max_relative_n_change']},sort_keys=True),flush=True)

if __name__=='__main__':main()

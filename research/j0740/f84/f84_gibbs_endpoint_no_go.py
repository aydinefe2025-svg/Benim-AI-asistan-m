#!/usr/bin/env python3
"""F84: Gibbs/Maxwell upper-pressure no-go for the explicitly *alternative* F83 EOS.

Checks immutable source bytes of JESTER BPS and F83 rebuilt RNS. Bounds the
BPS chemical potential at the selected F83 energy-continuous join WITHOUT
interpolating BPS E(P) or n(P). Tests the uppermost *native* BPS source knot.
Assumptions are explicit: monotone positive physical n_BPS(P), and
source-native mu_BPS=(epsilon+P)/n at BPS knots; F83 cold mu=mu0 exp(h).
This is a conditional numerical-source phase-selection obstruction,
NOT a proof about real nuclear MPA1 or a microphysically valid EOS.
"""
from __future__ import annotations
import argparse, hashlib,json,math
from pathlib import Path
import numpy as np

BPS_SHA='a4195d48ae98fd64d0a9676891ccab5a5c035e713780ad1187e85571a98a1787'
F83_SHA='99fc172310b06b2aa0a972320478853c84057c6d1e2810328f97e3c19c37309d'
OLD_SHA='f4a183661962acdddc7aebde3830116578feb6fba88a1a68c9fd57a993058675'
C=2.99792458e10;MEV_ERG=1.602176634e-6;MEVFM_DYNCM2=1.602176634e33
JOIN_P=0.07512275520519562
SCHEMA='J0740_F84_F83_BPS_NATIVE_GIBBS_NO_SINGLE_SWITCH_OVERLAP_V1'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def source_bps(path):
    if sha(path)!=BPS_SHA:raise ValueError('F84_PINNED_BPS_NATIVE_BYTES_DRIFT')
    bps=np.loadtxt(path,delimiter=',',skiprows=1,dtype=float)
    if bps.shape!=(130,3) or not np.isfinite(bps).all() or not (bps>0).all():raise ValueError('F84_BAD_NATIVE_BPS_DATA')
    n,p,e=bps.T
    if any(not np.all(np.diff(v)>0) for v in (n,p,e)):raise ValueError('F84_BPS_MONOTONIC_KNOTS_FAIL')
    return n,p,e

def source_f83(path):
    if sha(path)!=F83_SHA:raise ValueError('F84_REPAIRED_F83_EOS_BYTES_DRIFT')
    with Path(path).open() as f:
      count=int(f.readline().strip())
    a=np.loadtxt(path,skiprows=1)
    if a.shape!=(1213,4) or count!=1213 or not np.isfinite(a).all() or not (a>0).all():raise ValueError('F84_F83_RNS_SHAPE_DRIFT')
    E=a[:,0]*C*C;P=a[:,1];H=a[:,2]/C**2; n=a[:,3]
    if any(not np.all(np.diff(v)>0) for v in (P,E,H,n)):raise ValueError('F84_F83_RNS_MONOTONE_FAIL')
    mu0=(E[0]+P[0])/n[0]/MEV_ERG*math.exp(-H[0])
    if abs(mu0-930.4)>1e-7:raise ValueError('F84_F83_FE_ANCHOR_DRIFT')
    return E,P,H,n,float(mu0)

def cold_mu(Pwant_mev,E,P,H,mu0):
    q=Pwant_mev*MEVFM_DYNCM2
    if not (P[0] <=q<=P[-1]):raise ValueError('F84_PRESSURE_OUTSIDE_F83_SOURCE')
    i=int(np.searchsorted(P,q,side='right'))-1
    i=min(max(i,0),len(P)-2)
    s=(E[i+1]-E[i])/(P[i+1]-P[i])
    if not math.isfinite(s) or s<1-1e-9:raise ValueError('F84_NONCAUSAL_F83_SECANT')
    h=H[i]+math.log1p((1+s)*(q-P[i])/(E[i]+P[i]))/(1+s)
    return mu0*math.exp(h)

def match_bound(Pjoin,n,p,e):
    if len(n)!=len(p) or len(n)!=len(e) or len(n)<2 or any(not np.isfinite(v).all() for v in (n,p,e)) or any(not (v>0).all() for v in (n,p,e)) or any(not (np.diff(v)>0).all() for v in (n,p,e)):
        raise ValueError('F84_BPS_NONMONOTONIC_KNOTS')
    if not (p[0]<Pjoin<p[-1]):raise ValueError('F84_JOIN_OUTSIDE_BPS')
    i=int(np.searchsorted(p,Pjoin,side='right'))-1
    nl,nr=n[i:i+2];pl,pr=p[i:i+2];el,er=e[i:i+2]
    mu_l=(el+pl)/nl;mu_r=(er+pr)/nr
    # Gibbs Duhem d mu/d P = 1/n; monotone n yields rigorous interval bound.
    lo=mu_l+(Pjoin-pl)/nr
    hi=mu_l+(Pjoin-pl)/nl
    return {'lower_index_zero_based':int(i),'upper_index_zero_based':int(i+1),
      'BPS_left_n_fm3':float(nl),'BPS_right_n_fm3':float(nr),'BPS_left_p_mev_fm3':float(pl),
      'BPS_right_p_mev_fm3':float(pr),'BPS_left_mu_MeV':float(mu_l),'BPS_right_mu_MeV':float(mu_r),
      'mu_BPS_at_join_lower_bound_MeV':float(lo),'mu_BPS_at_join_upper_bound_MeV':float(hi),
      'conditional_assumptions':'n_BPS(P) nondecreasing, positive and within adjacent source n endpoints; dmu/dP=1/n; mu at left source knot physical',
      'endpoint_interval_firstlaw_residual_MeV':float(mu_r-(mu_l+(pr-pl)/nr))}

def analyse(bps,f83):
    n,p,e=bps;E,P,H,n83,mu0=f83
    bound=match_bound(JOIN_P,n,p,e)
    lo,hi=bound['mu_BPS_at_join_lower_bound_MeV'],bound['mu_BPS_at_join_upper_bound_MeV']
    muc_j=cold_mu(JOIN_P,E,P,H,mu0)
    if not (lo>muc_j and lo-muc_j>.05):raise ValueError('F84_JOIN_GIBBS_OBSTRUCTION_CHANGED')
    p_upper=float(p[-1]); mue=float((e[-1]+p[-1])/n[-1]);muc_u=cold_mu(p_upper,E,P,H,mu0)
    if not muc_u>mue+.05:raise ValueError('F84_UPPER_BPS_PHASE_PREFERENCE_CHANGED')
    # Change absolute core baryon normalization to force mu_core(Pjoin)==mu_bps(Pjoin).
    # Such a constant rescale cannot change *ratio* mu_core(Pupper)/mu_core(Pjoin).
    matched_at_upper=(muc_u*lo/muc_j-mue,muc_u*hi/muc_j-mue)
    if not matched_at_upper[0]>.15:raise ValueError('F84_CALIBRATION_INVARIANT_UPPER_NO_GO_CHANGED')
    # Source knot signs, no fabricated pressure interpolation.
    shared=[(float(q),float(cold_mu(float(q),E,P,H,mu0)-(ee+q)/nn)) for nn,q,ee in zip(n,p,e) if q>=JOIN_P]
    crossings=[]
    for (p0,d0),(p1,d1) in zip(shared,shared[1:]):
        if d0*d1<0:crossings.append([p0,p1])
    return {'schema':SCHEMA,'status':'SOURCE_NATIVE_GIBBS_MATCHED_AT_JOIN_GLOBAL_SINGLE_SWITCH_NO_GO',
      'source_original_BPS_csv_sha256':BPS_SHA,'repaired_hybrid_F83_EOS_sha256':F83_SHA,
      'BPS_native_rows':len(n),'F83_RNS_rows':len(P),'junction_pressure_mev_fm3':JOIN_P,
      'F83_fixed_Fe_mu0_MeV':mu0,'F83_mu_core_at_junction_MeV':muc_j,
      'source_native_BPS_adjacent_join_bounds':bound,
      'original_Fe_normalization_core_mu_minus_BPS_join_bounds_MeV':[muc_j-hi,muc_j-lo],
      'source_native_BPS_upper_endpoint':{'P_MeV_fm3':p_upper,'n_b_fm3':float(n[-1]),'epsilon_MeV_fm3':float(e[-1]),'mu_BPS_MeV':mue,'mu_core_F83_MeV':muc_u,'core_minus_BPS_MeV':muc_u-mue},
      'if_mu0_rescaled_to_force_equality_at_junction':{'required_Fe_mu0_interval_MeV':[mu0*lo/muc_j,mu0*hi/muc_j],
       'upper_core_minus_BPS_MeV_interval':list(matched_at_upper),
       'normalization_independent_obstruction_to_single_globally_preferred_core_over_full_BPS_overlap':matched_at_upper[0]>0},
      'BPS_native_shared_pressure_knots_with_F83_core':len(shared),
      'BPS_native_knot_delta_mu_sign_change_brackets':crossings,
      'all_BPS_source_rows_genuinely_tested':True,
      'physical_original_MPA1_Gibbs_or_complete_inner_crust_EOS':'NOT_ESTABLISHED',
      'new_microphysically_consistent_phase_selection':'NOT_CONSTRUCTED',
      'old_F82_constant_J_stars_apply_to_F83_EOS':False,
      'source_native_XPSI_photon_likelihood':'NOT_RUN','physical_seven_EOS_Bayes':'NOT_RUN',
      'scope':'This rejects a single globally preferred BPS→the exact F83 core branch switch at fixed junction P and any one multiplicative mu normalization on full BPS overlap under stated source BPS monotone-firstlaw assumptions; NOT original nuclear EOS or arbitrary other transition pressures/inner crust.'}

def main():
    pa=argparse.ArgumentParser();pa.add_argument('--bps',type=Path,required=True);pa.add_argument('--eos',type=Path,required=True);pa.add_argument('--out',type=Path,required=True)
    a=pa.parse_args();ans=analyse(source_bps(a.bps),source_f83(a.eos))
    a.out.parent.mkdir(exist_ok=True,parents=True)
    a.out.write_text(json.dumps(ans,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'status':ans['status'],'BPS_join':ans['source_native_BPS_adjacent_join_bounds'],
          'BPS_upper':ans['source_native_BPS_upper_endpoint'],'calibration_independent_gap':ans['if_mu0_rescaled_to_force_equality_at_junction']['upper_core_minus_BPS_MeV_interval'],
          'shared_native_BPS_knots':ans['BPS_native_shared_pressure_knots_with_F83_core']},sort_keys=True))

if __name__=='__main__':main()

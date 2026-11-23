"""Inductance-aware, passive source EIS circuit: out-of-sample falsifiability.

Z(f) = Rs + Rp / (1 + j*2*pi*f*tau) + j*2*pi*f*L
with Rs>=0, Rp>=0, L>=0, tau>0.

An effective series L that improves prediction is NOT an independent
laboratory measurement of wire inductance or evidence of cell damage.
"""
from __future__ import annotations

import math
import statistics
from itertools import combinations

from research.battery_curve_audit import graz_eis_rc_frequency_holdout as simple

GRID_COUNT=101

def _solve(a,b):
    n=len(b)
    m=[list(row)+[b[i]] for i,row in enumerate(a)]
    for k in range(n):
        p=max(range(k,n),key=lambda i:abs(m[i][k]))
        scale=max(max(abs(x) for x in m[i][:n]) for i in range(n))
        if abs(m[p][k]) <= 1e-12*max(scale,1e-30):
            return None
        m[k],m[p]=m[p],m[k]
        pivot=m[k][k]
        for j in range(k,n+1):m[k][j]/=pivot
        for i in range(n):
            if i==k:continue
            factor=m[i][k]
            for j in range(k,n+1):
                m[i][j]-=factor*m[k][j]
    return [m[i][n] for i in range(n)]

def model_z(f,rs,rp,tau,inductance_h):
    if f<=0 or any(not math.isfinite(x) or x<0 for x in (rs,rp,inductance_h)) or tau<=0:
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid source circuit parameters')
    return rs+rp/(1+1j*2*math.pi*f*tau)+1j*2*math.pi*f*inductance_h

def _candidate(train,tau):
    fmax=max(x[0] for x in train)
    design=[]
    for f,z,_ in train:
        k=1/(1+1j*2*math.pi*f*tau)
        design.append((z,(1+0j,k,1j*(f/fmax))))
    gram=[[sum((terms[i].conjugate()*terms[j]).real for _,terms in design)
           for j in range(3)] for i in range(3)]
    rhs=[sum((terms[i].conjugate()*z).real for z,terms in design) for i in range(3)]
    best=None
    for count in (0,1,2,3):
        for subset in combinations(range(3),count):
            parameters=[0.,0.,0.]
            if count:
                matrix=[[gram[i][j] for j in subset] for i in subset]
                vector=[rhs[i] for i in subset]
                sub=_solve(matrix,vector)
                if sub is None or any(not math.isfinite(x) or x< -1e-11 for x in sub):
                    continue
                for i,x in zip(subset,sub):parameters[i]=max(0.,x)
            err=sum(abs(z-sum(parameters[i]*terms[i] for i in range(3)))**2
                    for z,terms in design)
            if best is None or err<best[0]:best=(err,*parameters)
    if best is None:raise ValueError('SOURCE_REVIEW_REQUIRED: nonnegative fit failed')
    return best

def _fit(train):
    frequencies=[x[0] for x in train]
    low=math.log(1/(2*math.pi*max(frequencies)*100))
    high=math.log(100/(2*math.pi*min(frequencies)))
    grid=[]
    for i in range(GRID_COUNT):
        u=low+(high-low)*i/(GRID_COUNT-1)
        candidates=_candidate(train,math.exp(u))
        grid.append((candidates[0],u,*candidates[1:]))
    idx=min(range(GRID_COUNT),key=lambda i:grid[i][0])
    a=grid[max(idx-1,0)][1];b=grid[min(idx+1,GRID_COUNT-1)][1]
    phi=(math.sqrt(5)-1)/2
    c=b-phi*(b-a);d=a+phi*(b-a)
    for _ in range(18):
        if _candidate(train,math.exp(c))[0]<_candidate(train,math.exp(d))[0]:
            b=d;d=c;c=b-phi*(b-a)
        else:
            a=c;c=d;d=a+phi*(b-a)
    tau=math.exp((a+b)/2)
    best=_candidate(train,tau)
    if grid[idx][0]<best[0]:
        best=grid[idx][:1]+grid[idx][2:]
        tau=math.exp(grid[idx][1])
    _,rs,rp,q=best
    L=q/(2*math.pi*max(frequencies))
    return rs,rp,tau,L

def cross_validate_rlc(spectrum):
    originals=simple._validated(spectrum)
    folds=[];total_error=total_norm=0.
    pct_error=[]
    for parity in (0,1):
        train=[p for j,p in enumerate(originals) if j%2==parity]
        holdout=[p for j,p in enumerate(originals) if j%2!=parity]
        rs,rp,tau,L=_fit(train)
        errors=[abs(z-model_z(f,rs,rp,tau,L)) for f,z,_ in holdout]
        numerator=sum(e*e for e in errors)
        denominator=sum(abs(z)**2 for _,z,_ in holdout)
        if denominator<=0:raise ValueError('SOURCE_REVIEW_REQUIRED: zero physical measurement signal')
        total_error+=numerator;total_norm+=denominator
        pct_error.extend(100*e/abs(p[1]) for e,p in zip(errors,holdout))
        folds.append({
            'fit_train_parity':parity,'training_frequencies':len(train),
            'heldout_frequencies':len(holdout),
            'Rs_ohm':rs,'Rp_ohm':rp,'tau_s':tau,
            'series_inductance_h':L,
            'heldout_complex_relative_rmse_pct':round(100*math.sqrt(numerator/denominator),8)
        })
    return {
        'observed_frequency_count':len(originals),
        'fold_train_counts':[q['training_frequencies'] for q in folds],
        'fold_test_counts':[q['heldout_frequencies'] for q in folds],
        'heldout_relative_complex_rmse_pct':round(100*math.sqrt(total_error/total_norm),8),
        'heldout_median_point_relative_complex_error_pct':round(statistics.median(pct_error),8),
        'heldout_max_point_relative_complex_error_pct':round(max(pct_error),8),
        'positive_phase_frequency_count':sum(p[2]>0 for p in originals),
        'folds':folds,
        'inductance_term_effective_not_physical_measurement':True,
        'series_inductance_independently_calibrated':False,
        'independent_lab_clock_or_force_calibrated':False,
        'capacity_Ah_or_mechanical_damage_measured':False,
        'production_release_allowed':False
    }

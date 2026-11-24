#!/usr/bin/env python3
"""9-source lithium-ion experimental-design/thermal settling model.

Publication source-derived measured-summary observations are kept distinct from
hypothetical thermal model and proposed Latin-square test order. No field/lab
or device calibration is implied.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

SOURCE_SHA='424e1cf66146d3cd3477297f6c315c0ef18d794c0b7dffc05d374964131eb5da'
TEMPS=(10,23,45)
TAUS=(15,30,60)  # minutes, illustrative NOT estimated from source cells
HOLDS=(30,60,120,240) # minutes, illustrative
BETAS=(0.01,0.03,0.05) # percentage points per degree C, illustrative not measured
DELTA_T_MAX=35.0
TEMP_TOL_C=0.5
SEED=20261122
BOOTSTRAP_REPS=10000

def read_pinned(path):
    raw=Path(path).read_bytes()
    actual=hashlib.sha256(raw).hexdigest()
    # Git clients can change checkout LF to CRLF on Windows; require canonical hash.
    if actual!=SOURCE_SHA:
        normalized=raw.replace(b'\r\n',b'\n')
        if normalized.replace(b'\n',b'\r\n') != raw or hashlib.sha256(normalized).hexdigest()!=SOURCE_SHA:
            raise ValueError('SOURCE_SHA256_MISMATCH')
        raw=normalized
    return json.loads(raw)

def validate(data):
    if data.get('source_file_records')!=9 or data.get('source_temperature_pairs')!=27:
        raise ValueError('wrong source summary grain')
    rows=data.get('source_results')
    if not isinstance(rows,list) or len(rows)!=27:
        raise ValueError('wrong number of source rows')
    groups=defaultdict(dict)
    for row in rows:
        k=row.get('source_file_id'); t=row.get('temperature_C')
        if type(k) is not int or type(t) is not int or t not in TEMPS or t in groups[k]:
            raise ValueError('invalid, repeated or misaligned physical source/temperature key')
        c=row.get('charge_change_percent'); d=row.get('discharge_change_percent')
        if type(c) not in (int,float) or type(d) not in (int,float) or not math.isfinite(c) or not math.isfinite(d):
            raise ValueError('nonfinite or invalid measured-summary number')
        both=(c<0 and d<0)
        mixed=not both
        if row.get('both_channels_decline') is not both or row.get('mixed_or_zero_channel_sign') is not mixed:
            raise ValueError('source-derived channel flags conflict with values')
        groups[k][t]=row
    if len(groups)!=9 or any(set(v)!=set(TEMPS) for v in groups.values()):
        raise ValueError('expected 9 distinct physical source labels each at three temperatures')
    if sum(r['mixed_or_zero_channel_sign'] for r in rows)!=4:
        raise ValueError('expected the source-ledger sign count')
    return dict(sorted(groups.items()))

def rank(matrix,tol=1e-10):
    a=[list(map(float,row)) for row in matrix]
    if not a:return 0
    m=len(a);n=len(a[0]);rr=0
    for j in range(n):
        pivot=max(range(rr,m),key=lambda i:abs(a[i][j]),default=rr)
        if rr>=m or abs(a[pivot][j])<tol:continue
        a[rr],a[pivot]=a[pivot],a[rr]
        p=a[rr][j]
        for k in range(j,n): a[rr][k]/=p
        for i in range(rr+1,m):
            f=a[i][j]
            for k in range(j,n):a[i][k]-=f*a[rr][k]
        rr+=1
        if rr==m:break
    return rr

def make_design_matrix(permutations):
    """27x13; cell FE 8 + intercept + temp FE 2 + period FE 2."""
    if len(permutations)!=9 or any(sorted(p)!=list(TEMPS) for p in permutations):
        raise ValueError('bad repeat/temperature assignment')
    out=[]
    for cell, seq in enumerate(permutations):
        for period,temp in enumerate(seq):
            out.append([1]+[int(cell==i) for i in range(1,9)] +
                       [int(temp==23),int(temp==45),int(period==1),int(period==2)])
    return out

def fixed_order():return [TEMPS for _ in range(9)]
def balanced_order():
    cycles=((10,23,45),(23,45,10),(45,10,23))
    return [cycles[i%3] for i in range(9)]

def thermal_residual(max_step,hold,tau):
    if max_step<0 or hold<0 or tau<=0:raise ValueError('bad model parameters')
    return max_step*math.exp(-hold/tau)

def model_source(data, repetitions=BOOTSTRAP_REPS, seed=SEED):
    groups=validate(data)
    diffs=[];by_temp={t:[] for t in TEMPS}
    positive_discharge=[]
    for src,v in groups.items():
        gaps={t:abs(v[t]['charge_change_percent']-v[t]['discharge_change_percent']) for t in TEMPS}
        diffs.append({'source_file_id':src,'cohort':v[10]['cohort'],'t10_minus_t23t45_abs_gap_pp':round(gaps[10]-(gaps[23]+gaps[45])/2,7),
                      't10_abs_gap_pp':round(gaps[10],7)})
        for t in TEMPS:by_temp[t].append(gaps[t])
        if v[10]['discharge_change_percent']>0:positive_discharge.append(v[10]['discharge_change_percent'])
    values=[x['t10_minus_t23t45_abs_gap_pp'] for x in diffs]
    rng=random.Random(seed)
    bmeans=sorted(sum(values[rng.randrange(len(values))] for _ in values)/len(values) for _ in range(repetitions))
    sample_intervals=[bmeans[int(.025*repetitions)],bmeans[min(repetitions-1,int(.975*repetitions))]]
    thermal=[]
    for tau in TAUS:
        for hold in HOLDS:
            err=thermal_residual(DELTA_T_MAX,hold,tau)
            thermal.append({'tau_min_hypothetical':tau,'hold_min':hold,'residual_degC_max_step':round(err,6),
                            'max_change_pp_if_beta_0p03_and_ET_AT_residual_diff_equals_err':round(err*.03,6)})
    worst_min=min(positive_discharge)
    return {
      'schema':'cano.battery.nine-source.thermal-order-model.v1',
      'source_summary_sha256':SOURCE_SHA,
      'provenance':'measured-summary derived from 9 publisher physical-source labels, not new raw data',
      'observed_source_derived':{
        'physical_source_count':len(groups),'temperature_pairs':27,'source_gap_comparisons':diffs,
        'mean_absolute_channel_gap_pp_by_temp':{str(t):round(statistics.mean(by_temp[t]),7) for t in TEMPS},
        't10_greater_than_mean_t23_t45_source_count':sum(v>0 for v in values),
        'paired_source_level_excess_abs_gap_pp_mean':round(statistics.mean(values),7),
        'bootstrap_source_resample_percentile_2p5_97p5_pp':list(map(lambda x:round(x,7),sample_intervals)),
        'bootstrap_assumption':'repeated-source cluster bootstrap assumes 9 source labels exchangeable, ignoring potential within-cohort correlation; descriptive sensitivity only, not causal inference',
        't10_discharge_positive_count':len(positive_discharge),'smallest_t10_positive_discharge_change_pp':worst_min,
      },
      'hypothetical_thermal_RC_model':{
        'equation':'absolute_temperature_residual = abs(T_previous - T_target)*exp(-hold_min/tau_min)',
        'max_step_C_assumed':DELTA_T_MAX,'illustrative_tau_min':list(TAUS),
        'temperature_residual_target_C_assumed':TEMP_TOL_C,
        'minimum_hold_min_for_0p5_C_criterion_by_tau':{str(tau):round(tau*math.log(DELTA_T_MAX/TEMP_TOL_C),4) for tau in TAUS},
        'illustrative_beta_pp_per_C':list(BETAS),
        'conditional_bias_bound_pp_at_hold_tau_grid':thermal,
        'bias_bound_definition':'ONE ET/AT pass has thermal residual, comparison pass is equilibrated; abs(BETA)*(thermal residual). Not a predicted error or actual thermal history',
        'sample_threshold_hold_min_for_0p03_pp_per_C_to_be_below_smallest_positive_discharge':{str(tau):round(max(0,tau*math.log(DELTA_T_MAX*.03/worst_min)),4) for tau in TAUS},
        'limits':'single lumped RC cooling, no internal gradients, no Joule heating, no electrochemical hysteresis or CC/CV dynamics, no parameter calibration; this cannot verify any original cell temperature or device bias'
      },
      'hypothetical_trial_order_design':{
         'current_protocol_is_not_assumed_fixed_order':'source original experimental order unverified; fixed order is counterfactual only',
         'fixed_order_rank':rank(make_design_matrix(fixed_order())),
         'balanced_latin_order_rank':rank(make_design_matrix(balanced_order())),
         'design_columns':13,
         'fixed_order_counterfactual':[list(x) for x in fixed_order()],
         'balanced_3x3_latin_sequences':[list(x) for x in balanced_order()],
         'balanced_order_note':'3 orders repeated for 9 hypothetical cells; balances temp by visit period but NOT all first-order carryover, run timing, cell heterogeneity, or chamber effects',
         'estimability':'If temperature always occurs at one fixed period, temperature and period effects are confounded (rank 11 < 13). Balanced order makes main temp and main period effects separately estimable in this simplified linear model (rank 13).',
      },
      'actual_physical_calibration':False,'independent_laboratory_replication':False,
      'real_thermal_time_constant_measured':False,'causal_temperature_effect_established':False,
      'product_field_release_allowed':False
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    d=read_pinned(a.source); result=model_source(d)
    a.out.write_bytes((json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode('utf8'))
    print('PASS source pin, 9 source clusters, 27 comparisons; 10 C source-level matched, thermal RC scenario, 27x13 design-rank tests')
if __name__=='__main__':main()
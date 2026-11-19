#!/usr/bin/env python3
"""Reproducible, synthetic-only adversarial simulation of CANO battery preflight.

NEVER interpret a controlled synthetic label as a physical independent-cell ground truth.
No datasets, user identifiers, external APIs, dependencies or secrets required.

In scope: currently supported time/voltage 2-column single-run CSV format, numerical
aliasing, exact and close clones, time-grid and time-origin shifts, short/flat
trace coverage, mismatched units, damaged monotonicity, and atomic split checks.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
if (HERE / 'customer_pipeline.py').exists():
    sys.path.insert(0,str(HERE))
else:
    sys.path.insert(0,str(HERE / 'research' / 'battery_curve_audit'))
import customer_pipeline
import near_duplicate_guard as near

SCHEMA='cano.battery.virtual-lab.v1'
FAMILIES=(
    'independent_clear', 'exact_clone', 'numeric_format_clone',
    'near_clone_1mv', 'resampled_clone', 'time_origin_shift_clone',
    'noisy_clone_3mv', 'independent_alike_1mv', 'independent_bias_3mv',
    'short_unscreened', 'flat_unscreened',
    'mixed_declared_units', 'invalid_time', 'all_clones_no_holdout',
)
TAG={
    'independent_clear':'independent_template',
    'exact_clone':'controlled_clone',
    'numeric_format_clone':'controlled_clone',
    'near_clone_1mv':'controlled_clone',
    'resampled_clone':'controlled_clone',
    'time_origin_shift_clone':'controlled_clone',
    'noisy_clone_3mv':'controlled_clone',
    'independent_alike_1mv':'independent_template',
    'independent_bias_3mv':'independent_template',
    'short_unscreened':'unscannable_template',
    'flat_unscreened':'unscannable_template',
    'mixed_declared_units':'invalid_template',
    'invalid_time':'invalid_template',
    'all_clones_no_holdout':'blocked_template',
}
# Expected CURRENT acceptance results are intentionally not the ground-truth labels.
# These assert baseline behavior so a change cannot silently rewrite the evidence.
BASELINE_EXPECTED={
    'independent_clear':'SCREEN_ONLY_NO_CROSS_CELL_CANDIDATES',
    'exact_clone':'REVIEW_REQUIRED',
    'numeric_format_clone':'REVIEW_REQUIRED',
    'near_clone_1mv':'REVIEW_REQUIRED',
    'resampled_clone':'REVIEW_REQUIRED',
    'time_origin_shift_clone':'REVIEW_REQUIRED',
    'noisy_clone_3mv':'REVIEW_REQUIRED',
    'independent_alike_1mv':'REVIEW_REQUIRED',
    'independent_bias_3mv':'REVIEW_REQUIRED',
    'short_unscreened':'REVIEW_REQUIRED',
    'flat_unscreened':'REVIEW_REQUIRED',
    'mixed_declared_units':'REJECTED_INPUT',
    'invalid_time':'REJECTED_INPUT',
    'all_clones_no_holdout':'BLOCK_INSUFFICIENT_GROUPS',
}


def waveform(x, base, wiggle, phase):
    # Smooth voltage/time template with non-linear end-of-discharge knee.
    return base - 0.64*x - 0.08*x*x - 0.09/(1+math.exp(-25*(x-0.89))) + wiggle*math.sin(4*math.pi*x+phase)


def curve_points(base, noise, phase, *, n=128, t_offset=0.0, v_offset=0.0, flat=False,
                 alias=False, rng=None, t_end=127.0, noise_jitter=0.0):
    data=[]
    for i in range(n):
        x=i/(n-1)
        t=t_offset+t_end*x
        v=(base-0.010*x if flat else waveform(x,base,noise,phase))+v_offset
        if rng is not None and noise_jitter:
            v+=rng.uniform(-noise_jitter,noise_jitter)
        ts=(f'{t:.9f}' if alias else f'{t:.9f}'.rstrip('0').rstrip('.'))
        vs=(f'{v:.8e}' if alias else f'{v:.8f}'.rstrip('0').rstrip('.'))
        data.append((ts,vs))
    return data


def write_csv(root, cell, points, *, unit='V'):
    p=root/(cell+'.csv')
    rows=[f'Timestamp_1 [h],DC1 [{unit}]']
    rows.extend(f'{t},{v}' for t,v in points)
    p.write_text('\n'.join(rows)+'\n',encoding='utf-8')
    return p


def run_case(family, trial, *, seed, max_traces=120):
    rng=random.Random(seed*100003 + trial*271 + FAMILIES.index(family)*911)
    base=4.05 + rng.uniform(-0.025,0.025)
    phase=rng.uniform(-0.15,0.15)
    wiggle=0.014 + rng.uniform(-0.002,0.002)
    original=curve_points(base,wiggle,phase)
    other={
        'A':original,
        'B':curve_points(base-0.16,wiggle,phase+0.05),
        'C':curve_points(base-0.31,wiggle,phase+0.12),
        'D':curve_points(base-0.47,wiggle,phase+0.2),
    }
    modes={name:'dchg' for name in other}
    units={name:'V' for name in other}
    if family=='exact_clone':
        other['B']=list(original)
    elif family=='numeric_format_clone':
        other['B']=curve_points(base,wiggle,phase,alias=True)
    elif family=='near_clone_1mv':
        other['B']=curve_points(base,wiggle,phase,v_offset=0.001)
    elif family=='resampled_clone':
        other['B']=curve_points(base,wiggle,phase,n=160)
    elif family=='time_origin_shift_clone':
        other['B']=curve_points(base,wiggle,phase,t_offset=3.0)
    elif family=='noisy_clone_3mv':
        other['B']=curve_points(base,wiggle,phase,v_offset=0.0035)
    elif family=='independent_alike_1mv':
        # Different synthetic object/lab template but deliberately observationally
        # indistinguishable within 2mV. Review is not proof of a copying event.
        other['B']=curve_points(base,wiggle,phase,v_offset=0.001)
    elif family=='independent_bias_3mv':
        # Deliberately an INDEPENDENT declared origin with the exact same
        # observable A/B values as noisy_clone_3mv. Waveforms alone cannot
        # distinguish it: review NOT physical-copy proof.
        other['B']=curve_points(base,wiggle,phase,v_offset=0.0035)
    elif family=='short_unscreened':
        other['B']=curve_points(base-0.2,wiggle,phase,n=64)
    elif family=='flat_unscreened':
        other['B']=curve_points(base-0.2,wiggle,phase,flat=True)
    elif family=='mixed_declared_units':
        units['B']='mV'  # Deliberately false label; must reject.
    elif family=='invalid_time':
        t=list(other['B']);t[60]=(t[59][0],t[60][1]);other['B']=t
    elif family=='all_clones_no_holdout':
        for name in other:
            other[name]=list(original)
    elif family!='independent_clear':
        raise ValueError('unknown family')

    # Counterfactual screens are *not* shipped customer policy; test whether
    # normalizing the time origin or subtracting an unknown voltage bias could
    # safely increase recall without also flagging clean independent templates.
    aligned = None
    bias_removed = None
    if family not in ('mixed_declared_units', 'invalid_time'):
        def trace_to_near(cell, pts, *, subtract_time_origin=False, bias=0.0):
            tt=[float(t) for t,_ in pts]
            vv=[float(v)+bias for _,v in pts]
            if subtract_time_origin:
                tt=[t-tt[0] for t in tt]
            return {'cell':cell,'mode':'dchg','run':1,'n':len(tt),
                    'times':tt,'volts':vv,'trace_sha256':cell*64}
        base_a=trace_to_near('A',other['A'],subtract_time_origin=True)
        base_b=trace_to_near('B',other['B'],subtract_time_origin=True)
        aligned = near.compare_near(base_a,base_b) is not None
        corrected_b=trace_to_near('B',other['B'],subtract_time_origin=True,
                     bias=float(other['A'][0][1])-float(other['B'][0][1]))
        bias_removed = near.compare_near(base_a,corrected_b) is not None

    with tempfile.TemporaryDirectory(prefix='cano_synthetic_') as tmp:
        root=Path(tmp)
        manifest={'schema':'cano.battery.customer-files.v1','files':[]}
        for cell,pts in other.items():
            write_csv(root,cell,pts,unit=units[cell])
            manifest['files'].append({'path':cell+'.csv','cell':cell,'mode':modes[cell]})
        begin=time.perf_counter()
        try:
            summary,private=customer_pipeline.audit_offline(manifest,root,max_traces=max_traces)
            decision=summary['decision']
            linked=bool(private is not None and private['by_cell']['A']==private['by_cell']['B'])
            same_group=bool(private is not None and any({'A','B'} <= set(g['cells']) for g in private['split']['groups']))
            result={'family':family,'trial':trial,'tag':TAG[family],'decision':decision,
                    'near_candidates':summary['near_candidates'],
                    'numeric_clone_groups':summary['cross_cell_numeric_duplicate_groups'],
                    'unscreened':summary['unscreened_traces'],
                    'group_count':summary['independent_groups'],
                    'A_B_same_partition':linked,
                    'A_B_same_connected_group':same_group,
                    'had_private_proposal':private is not None}
        except (ValueError,TypeError,OSError,RuntimeError) as exc:
            result={'family':family,'trial':trial,'tag':TAG[family],
                    'decision':'REJECTED_INPUT', 'error_category': type(exc).__name__,
                    'error_first_line': str(exc).split('\n',1)[0][:130]}
        result['elapsed_ms']=round((time.perf_counter()-begin)*1000,3)
        if aligned is not None:
            result['counterfactual_aligned_AB_candidate']=aligned
            result['counterfactual_voltage_bias_removed_AB_candidate']=bias_removed
    return result


def run_all(trials=20, seed=20261119, *, with_raw=False):
    if not isinstance(trials,int) or not 1<=trials<=1000:
        raise ValueError('trials must be in [1,1000]')
    start=time.perf_counter()
    rows=[run_case(f,i,seed=seed) for f in FAMILIES for i in range(trials)]
    groups={}
    for family in FAMILIES:
        fam=[r for r in rows if r['family']==family]
        observed=dict(sorted(Counter(r['decision'] for r in fam).items()))
        unexpected=[r['trial'] for r in fam if r['decision']!=BASELINE_EXPECTED[family]]
        groups[family]={'tag':TAG[family],'trials':len(fam),'observed_decisions':observed,
                        'baseline_expected':BASELINE_EXPECTED[family],
                        'deviation_count':len(unexpected),
                        'deviation_trial_indices':unexpected[:20],
                        'median_elapsed_ms':round(statistics.median(r['elapsed_ms'] for r in fam),3)}
        if any('A_B_same_partition' in r for r in fam):
            groups[family]['linked_A_B_same_partition_count']=sum(bool(r.get('A_B_same_partition')) for r in fam)
            groups[family]['linked_A_B_same_atomic_group_count']=sum(bool(r.get('A_B_same_connected_group')) for r in fam)
        if any('counterfactual_aligned_AB_candidate' in r for r in fam):
            groups[family]['counterfactual_aligned_AB_candidates']=sum(bool(r.get('counterfactual_aligned_AB_candidate')) for r in fam)
            groups[family]['counterfactual_bias_removed_AB_candidates']=sum(bool(r.get('counterfactual_voltage_bias_removed_AB_candidate')) for r in fam)
        if any('near_candidates' in r for r in fam):
            groups[family]['detected_near_candidates_total']=sum(r.get('near_candidates',0) for r in fam)
    clones=[r for r in rows if r['tag']=='controlled_clone']
    negatives=[r for r in rows if r['tag']=='independent_template']
    # This is a test-design label, not measured ground-truth lab correspondence.
    # 'Review' means caught/flagged; no scientific true-positive claim.
    flagged=lambda r:r['decision'] in ('REVIEW_REQUIRED','BLOCK_INSUFFICIENT_GROUPS','REJECTED_INPUT')
    controlled_detected=sum(flagged(r) for r in clones)
    controlled_missed=len(clones)-controlled_detected
    negative_flagged=sum(flagged(r) for r in negatives)
    summary={
        'schema':SCHEMA,'source':'synthetic math templates only; no original/customer lab curves',
        'program':'customer_pipeline.audit_offline with time-origin and bias-ambiguity review guards',
        'seed':seed,'trials_per_family':trials,'total_simulated_batches':len(rows),
        'total_generated_curves':sum(4 for _ in rows),
        'controlled_clone_batches':len(clones),
        'controlled_clone_review_or_block':controlled_detected,
        'controlled_clone_screen_only_misses':controlled_missed,
        'controlled_clone_screen_only_miss_rate':round(controlled_missed/len(clones),6),
        'independent_template_batches':len(negatives),
        'independent_templates_flagged_for_review':negative_flagged,
        'independent_templates_flag_rate':round(negative_flagged/len(negatives),6),
        'input_error_batches':sum(r['decision']=='REJECTED_INPUT' for r in rows),
        'experimental_second_stage': {
            'NOT_DEPLOYED_OR_CERTIFIED':True,
            'note':'A/B synthetic pair only; time-origin alignment or voltage-bias correction. Observe false review alarms before any release.',
            'time_aligned_controlled_clone_candidates':sum(bool(r.get('counterfactual_aligned_AB_candidate')) for r in clones),
            'time_aligned_independent_template_candidates':sum(bool(r.get('counterfactual_aligned_AB_candidate')) for r in negatives),
            'bias_removed_controlled_clone_candidates':sum(bool(r.get('counterfactual_voltage_bias_removed_AB_candidate')) for r in clones),
            'bias_removed_independent_template_candidates':sum(bool(r.get('counterfactual_voltage_bias_removed_AB_candidate')) for r in negatives),
        },
        'baseline_deviations':sum(v['deviation_count'] for v in groups.values()),
        'elapsed_wall_seconds':round(time.perf_counter()-start,3),
        'categories':groups,
        'interpretation':[
            'Controlled clone = synthetic transform applied to the same formula. Not an independent physical duplicate label.',
            'Independent template = separate declared synthetic source; nearby values can legitimately trigger review.',
            'Metrics are CONDITIONAL on constructed cases and are not field FPR/FNR, sensitivity, specificity or calibration.',
            'Constant time-origin shifts and small 2–5 mV voltage offsets are REVIEW-ONLY; input waveforms cannot distinguish synthetic clone from declared independent twin.',
            'SCREEN_ONLY says no candidate under this screen; it is not certification, release approval, or proof of sample independence.',
            'No physical materials tested; no model deployed; no paid customer data accessed.'
        ]
    }
    if with_raw:
        summary['all_trials']=rows
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trials',type=int,default=20)
    p.add_argument('--seed',type=int,default=20261119)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--include-trials',action='store_true')
    args=p.parse_args(argv)
    result=run_all(args.trials,args.seed,with_raw=args.include_trials)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists():
        raise ValueError('Refuse overwriting existing simulation evidence file')
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('SIMULATED',result['total_simulated_batches'],'batches in',result['elapsed_wall_seconds'],'s')
    print('KNOWN_SYNTHETIC_CLONE_MISSES',result['controlled_clone_screen_only_misses'],'/',result['controlled_clone_batches'])
    print('SYNTHETIC_INDEPENDENT_TEMPLATE_REVIEW',result['independent_templates_flagged_for_review'],'/',result['independent_template_batches'])
    print('BASELINE_DEVIATIONS',result['baseline_deviations'])
    print('OUTPUT',args.output)

if __name__=='__main__':
    main()
